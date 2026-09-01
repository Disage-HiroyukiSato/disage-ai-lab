# DisageAI ローカルLLM + RAG 開発ガイド

更新日: 2026-09-01

## 1. 目的

DisageAIは、研修教材を根拠に回答するローカルRAG基盤です。初期PoCで使用したOpen WebUIは採用せず、独自UI・Authentik・専用APIを前提とします。

## 2. 構成

| コンポーネント | 役割 |
|---|---|
| Gateway | 外部からの唯一の入口 |
| oauth2-proxy | Authentik OIDC認証 |
| embedding-api | 現在のRAGオーケストレーションAPI |
| llama.cpp | 回答生成 |
| llama-rewriter | 会話を考慮したQuery Rewrite |
| BGE-M3 | Embedding |
| BGE Reranker | Cross Encoder Rerank |
| ChromaDB | ベクトル索引 |
| PostgreSQL | 会話、進捗、文書管理 |
| Redis | 検索キャッシュ |

`rag-api` は透過プロキシであり責務が重複していたため削除しました。

## 3. 初期設定

```bash
cp .env.example .env
cp config/database.env.example config/database.env
cp config/auth.env.example config/auth.env
```

実際のパスワード、OIDC Client Secret、Cookie SecretはGitへ登録しません。

## 4. モデル

標準構成:

- LLM: Qwen2.5 7B Instruct GGUF
- Embedding: BAAI/bge-m3
- Reranker: BAAI/bge-reranker-base
- Query Rewriter: 小型Instructモデル

モデルは `models/` 配下へ配置します。モデルファイルはGit管理外です。

## 5. 起動

```bash
docker compose -f compose/docker-compose.yml config
docker compose -f compose/docker-compose.yml up -d --build
docker compose -f compose/docker-compose.yml ps
```

既定ではGatewayのみ `127.0.0.1:8088` へ公開されます。PostgreSQL、Redis、ChromaDB、LLMへホストから直接接続しません。

## 6. Authentik

AuthentikでOAuth2/OpenID ProviderとApplicationを作成し、Redirect URIを次に設定します。

```text
https://<公開ホスト>/oauth2/callback
```

Issuer URL、Client ID、Client Secretを `config/auth.env` に設定します。TLS終端はTraefik等のリバースプロキシで行い、Gatewayへ転送します。

## 7. テスト

```bash
docker compose -f compose/docker-compose-test.yml up --build \
  --abort-on-container-exit \
  --exit-code-from embedding-api-test

docker compose -f compose/docker-compose-test.yml down -v
```

テスト用ChromaDBは匿名volumeを使い、開発・本番データを参照しません。

## 8. 開発ルール

- APIルーターへ検索・業務ロジックを書かない
- 同期的なモデル推論やDB処理を `async def` から直接呼ばない
- リクエストの `student_id` を認証済み利用者情報として信用しない
- 文書更新は新バージョンを作り、完了後に公開版を切り替える
- 検索は公開済みの文書バージョンだけを対象とする
- RAGパラメータ変更には品質評価結果を添付する

## 9. 旧ガイドからの主な変更

- Open WebUIを削除
- Tailscaleを製品認証として使用しない
- Authentik OIDC Gatewayを追加
- ChromaDB、PostgreSQL、Redisを内部ネットワーク化
- Reranker、BM25、Query Rewrite、Answerability Gateを追加
- テストデータを本番データから分離
