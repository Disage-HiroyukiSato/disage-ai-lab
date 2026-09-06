# DisageAI 既存文書一括登録手順書

| 項目 | 内容 |
| --- | --- |
| 対象 | DisageAI Lab 現行実装 |
| 文書版 | 1.0 |
| 作成日 | 2026-09-06 |

## 1. 概要

`data/documents` にファイルを置くだけではChromaDBへ登録されない。配置後、既存の一括登録スクリプトを手動実行する。

```text
ファイル配置 → スクリプト実行 → 文字抽出 → POST /documents
              → チャンク分割 → Embedding生成 → ChromaDB登録
```

## 2. 既存スクリプト

| 用途 | スクリプト | 形式 | 登録先 |
| --- | --- | --- | --- |
| Java教材 | `services/embedding_api/tests/eval/register_java_documents.py` | PDF | `java_training` |
| 社内業務資料 | `services/embedding_api/tests/eval/register_instructor_docs.py` | PDF、TXT、MD | `instructor_ops` |
| 評価用JSON | `services/embedding_api/tests/eval/setup_documents.py` | `dataset.json` | API既定値 |

SAPデモ資料には `register_instructor_docs.py` を使用する。

## 3. 配置先

Java教材：

```text
data/documents/java/
├─ java-basic.pdf
└─ documents_meta.json
```

SAPデモ・社内業務資料：

```text
data/documents/instructor_ops/
├─ sap-demo-company-rules.pdf
├─ operation-faq.md
└─ documents_meta.json
```

RAG登録だけが目的なら、PDFよりMarkdownまたはUTF-8テキストを推奨する。PDFの段組み、ヘッダー、改行、コードインデント崩れを避けられる。

## 4. PDFの制約

PDFは `pdfplumber` で文字抽出する。画像だけのスキャンPDFに対するOCR機能はない。次の警告が出る場合はOCR済みPDFまたはテキストへ変換する。

```text
テキスト抽出結果が空です（スキャンPDFの可能性）
```

## 5. メタデータ

`documents_meta.json` のキーには拡張子を除いたファイル名を使用する。

```text
sap-demo-company-rules.pdf → sap-demo-company-rules
```

SAPデモ用の例：

```json
{
  "_comment": "SAPデモ用資料",
  "sap-demo-company-rules": {
    "title": "SAP開発会社 デモ用社内業務ルール",
    "category": "SAP開発社内ルール",
    "keywords": "SAP 社内規程 移送 変更管理 テスト 障害 セキュリティ 生成AI",
    "chapter": "SAPプロジェクト運用",
    "section": "社内業務ルール",
    "language": "ja"
  }
}
```

定義がないファイルも既定メタデータで登録できる。

## 6. 事前準備

認証なし構成を起動する。

```powershell
docker compose `
  -f compose/docker-compose-noauth.yml `
  up -d
```

状態確認：

```powershell
docker compose `
  -f compose/docker-compose-noauth.yml `
  ps
```

ホストPCへ必要ライブラリをインストールする。

```powershell
py -m pip install requests==2.32.5 pdfplumber==0.11.4
```

## 7. 社内業務・SAPデモ資料の一括登録

`disage-ai-lab` ルートで実行する。

```powershell
py services/embedding_api/tests/eval/register_instructor_docs.py `
  --dir data/documents/instructor_ops `
  --url http://localhost:8088
```

対象はPDF、TXT、Markdownで、登録先は `instructor_ops` に固定されている。

特定ファイルだけ登録：

```powershell
py services/embedding_api/tests/eval/register_instructor_docs.py `
  --dir data/documents/instructor_ops `
  --file sap-demo-company-rules.pdf `
  --url http://localhost:8088
```

## 8. Java教材の一括登録

```powershell
py services/embedding_api/tests/eval/register_java_documents.py `
  --dir data/documents/java `
  --url http://localhost:8088
```

対象はPDFで、登録先は `java_training` に固定されている。

特定ファイルだけ登録：

```powershell
py services/embedding_api/tests/eval/register_java_documents.py `
  --dir data/documents/java `
  --file java-basic.pdf `
  --url http://localhost:8088
```

## 9. URLと認証の注意

既存スクリプトの既定URLは `http://localhost:8010` だが、現行ComposeではEmbedding APIの8010番をホストへ公開していない。必ず次を指定する。

```text
--url http://localhost:8088
```

既存スクリプトはAuthentik/OIDCログインに対応していない。ローカル初期登録は認証なし構成で行う。本番では管理者トークン、サービスアカウント、登録専用バッチなどを別途設計する。

## 10. 再登録

拡張子を除いたファイル名が `document_id` になる。同じDocument IDで再登録すると、既存チャンクを削除してから新しいチャンクを登録するため更新として扱われる。ファイル名を変更すると別文書になる。

## 11. 件数確認

```powershell
docker compose `
  -f compose/docker-compose-noauth.yml `
  exec embedding-api `
  python -c "from app.services.infra.chroma_service import chroma_service; print([(c.name, c.count()) for c in chroma_service.client.list_collections()])"
```

例：

```text
[('instructor_ops', 20), ('java_training', 145)]
```

件数はファイル数ではなくチャンク数である。

## 12. 検索確認

```powershell
$body = @{
  question = "本番移送の前に何を記録する必要がありますか。"
  limit = 5
} | ConvertTo-Json -Compress

$response = Invoke-RestMethod `
  -Uri "http://localhost:8088/retrieval" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))

$response | ConvertTo-Json -Depth 10
```

`total` が1以上で、`items` に対象資料が含まれることを確認する。

## 13. 回答生成確認

```powershell
$body = @{
  question = "本番移送の前に何を記録する必要がありますか。"
  limit = 5
  student_id = $null
  session_id = $null
} | ConvertTo-Json -Compress

$response = Invoke-RestMethod `
  -Uri "http://localhost:8088/query" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))

$response | ConvertTo-Json -Depth 10
```

確認値：

```text
retrieved_count > 0
gate_candidate_count > 0
final_context_count > 0
llm_elapsed_ms > 0
```

## 14. トラブルシューティング

| 症状 | 確認内容 |
| --- | --- |
| 対象ファイルなし | `--dir`、拡張子、配置場所 |
| PDF抽出結果が空 | スキャンPDF。OCRが必要 |
| 接続拒否 | `--url http://localhost:8088` を指定 |
| 403／ログインHTML | 認証ありGatewayへ未認証で送信 |
| 登録後も検索0件 | コレクション、件数、`MAX_DISTANCE`、Embeddingモデル |

ログ：

```powershell
docker compose `
  -f compose/docker-compose-noauth.yml `
  logs --since=10m embedding-api
```

## 15. 運用上の推奨

- 原本資料とChromaDBのベクトルデータを区別する。
- 原本から再登録できる状態を維持する。
- 顧客機密情報をデモ環境へ登録しない。
- `documents_meta.json` を原本と一緒に管理する。
- 同じ内容を異なるファイル名で重複登録しない。
- 登録後は件数と代表質問を確認する。
- 将来は実運用スクリプトを `tests/eval` から `scripts/ingestion` などへ移す。
- `--dry-run`、登録結果レポート、管理者認証、OCR、文書一覧・削除APIを追加すると運用しやすい。

