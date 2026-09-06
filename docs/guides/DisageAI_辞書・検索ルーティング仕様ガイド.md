# DisageAI 辞書・検索ルーティング仕様ガイド

| 項目 | 内容 |
| --- | --- |
| 対象 | DisageAI Lab 現行実装 |
| 文書版 | 1.0 |
| 作成日 | 2026-09-06 |

## 1. 結論

`query_dictionary.json` と `off_topic_dictionary.json` は検索対象の許可リストではない。辞書にない質問でも、ChromaDBに関連資料があればベクトル検索できる。

```text
質問 → 正規化 → Collection Router → 教材外判定
     → Query Rewrite → Query Expansion → ChromaDB検索
     → 距離フィルター → Reranker → Answerability Gate → 回答生成
```

## 2. 辞書・ルーター一覧

| ファイル | 用途 | 一致しない場合 |
| --- | --- | --- |
| `config/query_dictionary.json` | 略称・同義語による検索語展開 | 元の質問だけで検索 |
| `config/off_topic_dictionary.json` | Java研修の主要範囲内か判定 | `is_off_topic=true`。検索は継続 |
| `config/collection_router_dictionary.json` | 検索先コレクション選択 | `java_training` と `instructor_ops` の両方を検索 |

現行リポジトリでは、`rag.env` に `collection_router_dictionary.json` の指定がある一方、ファイル本体が見当たらない。この場合は安全側のフォールバックとして両コレクションを検索する。

## 3. query_dictionary.json

略称や表記揺れから追加の検索文を作る。

```json
{
  "js": ["javascript", "java script"],
  "db": ["database"],
  "ai": ["artificial intelligence", "生成ai"]
}
```

`config/rag.env` の現行設定は次のため、この辞書は現在無効である。

```env
ENABLE_QUERY_EXPANSION=false
EXPANSION_LIMIT=3
QUERY_DICTIONARY=/app/config/query_dictionary.json
```

有効化する場合：

```env
ENABLE_QUERY_EXPANSION=true
```

辞書に一致しなくても検索は中止されず、元質問がそのままChromaDB検索へ渡る。

### 現行実装の制約

質問を空白で分割し、分割後の単語を辞書キーへ完全一致させる。

```python
words = question.split()
synonyms = self.dictionary.get(word)
```

日本語は単語間に空白を入れないことが多いため、部分一致や形態素解析を使う実装より展開されにくい。

## 4. off_topic_dictionary.json

`in_scope` の語が質問に部分一致するかで教材内外を判定する。

```json
{
  "in_scope": ["java", "クラス", "継承", "メソッド", "override"]
}
```

| 状態 | 判定 |
| --- | --- |
| いずれかに一致 | `is_off_topic=false` |
| 一つも一致しない | `is_off_topic=true` |
| 辞書なし／空 | 誤判定防止のため `false` |

`is_off_topic=true` でもChromaDB検索は実行される。RAGに関連情報があれば、Java研修範囲外という理由だけで拒否しないよう最終Promptにも指示されている。

SAPデモを継続利用する場合は、分類精度向上のため `sap`、`移送`、`変更管理`、`本番作業`、`緊急変更`、`インシデント` などを既存の `in_scope` へ追加する。ただし、追加は検索可能にする必須条件ではない。

## 5. Collection Router

推奨する `config/collection_router_dictionary.json` の例：

```json
{
  "_comment": "質問から検索対象コレクションを選択する辞書",
  "java_training": [
    "java", "クラス", "継承", "メソッド", "override", "例外処理"
  ],
  "instructor_ops": [
    "sap", "社内規程", "移送", "変更管理", "本番作業",
    "緊急変更", "障害", "インシデント", "権限", "生成ai"
  ]
}
```

| 命中状態 | 検索先 |
| --- | --- |
| Javaだけ | `java_training` |
| 社内業務だけ | `instructor_ops` |
| 両方 | 両コレクション |
| どちらもなし | 取りこぼし防止のため両コレクション |

関連設定：

```env
COLLECTION_JAVA_TRAINING=java_training
COLLECTION_INSTRUCTOR_OPS=instructor_ops
COLLECTION_ROUTER_DICTIONARY=/app/config/collection_router_dictionary.json
```

## 6. 検索可否を決める主な要素

1. 対象コレクションにチャンクが登録されているか
2. 質問とチャンクのベクトル距離
3. `MAX_DISTANCE` の距離フィルター
4. Rerankerの結果
5. Answerability Gateの判定

| 状態 | 結果 |
| --- | --- |
| 辞書に語がなく、ChromaDBに関連資料あり | 検索可能 |
| 辞書に語があり、ChromaDBが空 | 検索結果0件 |
| Query Expansion無効 | 元質問で検索 |
| off-topic判定true | 検索継続 |
| Collection Router辞書なし | 両コレクションを検索 |

## 7. 変更反映

辞書は初回利用時に読み込まれ、プロセス内に保持される。変更後はEmbedding APIを再作成する。

```powershell
docker compose `
  -f compose/docker-compose-noauth.yml `
  up -d --force-recreate embedding-api
```

ログ確認：

```powershell
docker compose `
  -f compose/docker-compose-noauth.yml `
  logs --since=5m embedding-api
```

確認対象：

```text
Query dictionary loaded
Off-topic dictionary loaded
Collection router dictionary loaded
Collection Router
Off-topic Router
Expanded Query Count
Candidate Count
Distance Filter
Answerability Status
```

## 8. 運用方針

- 辞書を検索許可リストとして扱わない。
- SAP社内規程は `instructor_ops` へ登録する。
- Java教材は `java_training` へ登録する。
- 辞書変更時は検証質問と変更理由を記録する。
- 辞書だけで判断せず、コレクション件数と検索結果を確認する。
- Query Expansion有効化前に、日本語質問での展開結果を検証する。

