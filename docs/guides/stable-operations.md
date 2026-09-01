# DisageAI 安定運用ガイド

更新日: 2026-09-01

## 1. 運用原則

- 外部公開はTLS終端済みGatewayだけに限定する
- Authentikを迂回できる経路を作らない
- シークレットをGit、Composeファイル、ログへ記録しない
- 文書登録中の未完成索引を検索へ公開しない
- バックアップは取得だけでなく定期的に復元試験する

## 2. 推論設定の考え方

llama.cppの `-b`、`-ub`、Flash Attention、GPU layerは、モデル、コンテキスト長、VRAMに依存します。固定の万能値として扱わず、次を計測して決めます。

- prompt evaluation tokens/sec
- generation tokens/sec
- VRAM最大使用量
- 初回応答時間
- 同時実行時の待ち時間
- OOMと再起動の有無

現在の標準値はComposeを正とし、変更時は測定結果を残します。

## 3. 起動確認

```bash
docker compose -f compose/docker-compose.yml config
docker compose -f compose/docker-compose.yml up -d
docker compose -f compose/docker-compose.yml ps
docker compose -f compose/docker-compose.yml logs --tail=200 gateway oauth2-proxy embedding-api
```

Gatewayのローカルヘルス確認:

```bash
curl http://127.0.0.1:8088/gateway/health
```

RAG APIは認証なしではアクセスできないことも確認します。

## 4. 文書更新

文書更新は次の状態遷移で管理します。

```text
PENDING -> PROCESSING -> READY -> ACTIVE
                     \-> FAILED
```

- PROCESSING中の版は検索対象外
- 新版がREADYになるまで旧ACTIVE版を提供
- 検証成功後、単一トランザクションでACTIVE版を切替
- 失敗した新版はFAILEDとして保持し、再実行可能にする
- 旧版削除は公開切替後の非同期処理にする

## 5. バックアップ対象

- PostgreSQL
- ChromaDB volume
- BM25 index
- 登録前の原本
- 設定テンプレートと実環境のSecret管理台帳
- 使用モデル名、ハッシュ、llama.cppイメージ識別子

Redis検索キャッシュは原則として復元対象外です。

## 6. 障害時の縮退

| 障害 | 動作 |
|---|---|
| Redis停止 | キャッシュなしで検索 |
| Query Rewriter停止 | 元質問で検索 |
| PostgreSQL停止 | 会話・進捗機能を停止。監視通知 |
| ChromaDB停止 | RAG回答を停止し、根拠なし生成へフォールバックしない |
| llama.cpp停止 | 503を返し再試行可能であることを示す |
| Authentik停止 | fail closed。未認証アクセスを許可しない |

## 7. ログと個人情報

質問・回答・会話履歴は個人情報または顧客機密を含む可能性があります。

- 本文ログは既定で無効
- request ID、処理時間、件数、状態を構造化ログへ記録
- アクセストークン、Cookie、Authorizationヘッダーは記録禁止
- 保存期間と削除手続きを定める
- テナントを跨いだログ閲覧を禁止する

## 8. 更新手順

1. バックアップ確認
2. CI成功確認
3. ステージングでマイグレーション
4. RAG品質回帰テスト
5. 本番デプロイ
6. health/readiness確認
7. 代表質問によるスモークテスト
8. 監視確認
9. ロールバック可能期間を経て旧データ削除
