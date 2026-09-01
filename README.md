# DisageAI Lab

ローカルLLM、検索拡張生成（RAG）、研修向け応答制御を検証・製品化するためのリポジトリです。

## 現在の構成

- llama.cpp: 回答生成
- llama.cpp rewriter: 会話を考慮した検索クエリ生成
- FastAPI: 文書登録、検索、Rerank、回答生成
- BGE-M3 / BGE Reranker
- ChromaDB: ベクトル索引
- PostgreSQL: 会話・進捗・文書管理
- Redis: 検索キャッシュ
- Nginx + oauth2-proxy: Authentik OIDC Gateway

旧 `rag-api` はRAG処理を持たない透過プロキシだったため廃止しています。公開入口はGatewayだけです。

## 必要条件

- Docker Engine 26以降またはDocker Desktop
- Docker Compose v2
- NVIDIA Container Toolkit（GPU利用時）
- GGUFモデル、Embeddingモデル、Rerankerモデル
- AuthentikのOIDC Provider/Application

## 初期設定

```bash
cp config/database.env.example config/database.env
cp config/auth.env.example config/auth.env
cp .env.example .env
```

各ファイルのプレースホルダーを実環境の値へ変更してください。実ファイルはGit管理されません。

cookie secretは32バイトのランダム値をbase64で作成します。

```bash
openssl rand -base64 32
```

## 起動

```bash
docker compose -f compose/docker-compose.yml config
docker compose -f compose/docker-compose.yml up -d --build
```

外部へ公開されるのは既定で `127.0.0.1:8088` のGatewayだけです。TraefikなどのリバースプロキシからGatewayへ接続してください。直接LANへ公開する場合は、リスクを確認したうえで `GATEWAY_BIND_ADDRESS` を変更します。

## テスト

テスト環境は本番・開発用ChromaDBを参照しません。

```bash
docker compose -f compose/docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from embedding-api-test
docker compose -f compose/docker-compose-test.yml down -v
```

## 開発品質

```bash
python -m pip install -r services/embedding_api/requirements-test.txt
ruff check services/embedding_api
pytest services/embedding_api/tests
```

CIではCompose検証、Ruff、pytest、依存関係監査、Dockerfile検査、秘密情報検査を実行します。

## セキュリティ原則

- Authentikを経由しないAPIアクセスを許可しない
- PostgreSQL、Redis、ChromaDB、llama.cppをホスト公開しない
- DBパスワードやOIDC SecretをGitへ保存しない
- `student_id` や権限をリクエスト本文だけで信用しない
- 文書登録・削除は管理ロールに限定する

## ロードマップ

1. Phase A: 本番化基盤、秘密情報、Gateway、CI、テスト分離
2. Phase B: QueryServiceのモジュール分割、依存性注入、認可
3. Phase C: 文書バージョン管理とIngestion Worker
4. Phase D: OpenTelemetry、監視、バックアップ、品質評価
