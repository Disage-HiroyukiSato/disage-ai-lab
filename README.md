# DisageAI Lab

ローカルLLM、検索拡張生成（RAG）、研修向け応答制御を検証・製品化するためのバックエンドリポジトリです。

Web UIは別リポジトリ `disage-ai-ui` で管理します。本リポジトリにはUIのHTML、CSS、JavaScript、UI用Dockerfileを配置しません。

## 現在の構成

- llama.cpp: 回答生成
- llama.cpp rewriter: 会話を考慮した検索クエリ生成
- FastAPI: 文書登録、検索、Rerank、回答生成
- BGE-M3 / BGE Reranker
- ChromaDB: ベクトル索引
- PostgreSQL: 会話・進捗・文書管理
- Redis: 検索キャッシュ
- Nginx Gateway: UI/APIの同一オリジン入口
- oauth2-proxy: Authentik OIDC認証（通常構成のみ）

旧 `rag-api` はRAG処理を持たない透過プロキシだったため廃止しています。

## UIとAPIの分離

- `services/embedding_api`: JSON API専用。HTMLや静的ファイルを配信しません。
- `disage-ai-ui`: Web UI専用の別リポジトリ。バックエンド処理やデータストアへ直接接続しません。
- `gateway`: 画面を外部UIコンテナ `ui:8080`、APIを `embedding-api:8010` へ振り分けます。

ブラウザはGatewayだけへアクセスし、UIからAPIへのリクエストは同一オリジンの相対URLを使用します。

通常構成ではGatewayがoauth2-proxyを介してAuthentik認証を行います。認証なし構成では同じルーティングを維持したまま認証処理だけを外します。

## UIリポジトリとのDocker接続契約

本リポジトリのGatewayは、Dockerネットワーク上の `ui:8080` へ画面リクエストを転送します。

`disage-ai-ui` 側のComposeでは、本リポジトリと同じedgeネットワークへ参加し、`ui` というネットワークエイリアスを設定してください。

```yaml
services:
  ui:
    # build または image は disage-ai-ui 側で定義
    networks:
      edge:
        aliases:
          - ui

networks:
  edge:
    external: true
    name: ${DOCKER_EDGE_NETWORK:-disage-ai-edge}
```

`disage-ai-lab` 側を先に起動すると `disage-ai-edge` が作成されます。その後 `disage-ai-ui` を起動してください。

## 主なルーティング

| パス | 転送先 |
| --- | --- |
| `/`, `/documents-ui`, `/query-ui`, `/history-ui`, `/static/*` | `ui:8080`（別リポジトリ） |
| `/embedding`, `/documents/*`, `/query`, `/history/*`, `/retrieval` | `embedding-api:8010` |
| `/health`, `/ready`, `/docs`, `/redoc`, `/openapi.json` | `embedding-api:8010` |
| `/oauth2/*` | `oauth2-proxy`（通常構成のみ） |
| `/gateway/health` | Gateway自身 |

## 必要条件

共通:

- Docker Engine 26以降またはDocker Desktop
- Docker Compose v2
- NVIDIA Container Toolkit（GPU利用時）
- GGUFモデル、Embeddingモデル、Rerankerモデル
- `disage-ai-ui` リポジトリ

通常構成のみ:

- AuthentikのOIDC Provider/Application

## 初期設定

共通設定:

```bash
cp config/database.env.example config/database.env
cp .env.example .env
```

通常構成では認証設定も作成します。

```bash
cp config/auth.env.example config/auth.env
```

各ファイルのプレースホルダーを実環境の値へ変更してください。実ファイルはGit管理されません。

cookie secretは32バイトのランダム値をbase64で作成します。

```bash
openssl rand -base64 32
```

## 通常起動（Authentik認証あり）

```bash
docker compose -f compose/docker-compose.yml config
docker compose -f compose/docker-compose.yml up -d --build
```

その後、別リポジトリ `disage-ai-ui` を同じ `disage-ai-edge` ネットワークへ接続して起動します。

外部へ公開されるのは既定で `127.0.0.1:8088` のGatewayだけです。TraefikなどのリバースプロキシからGatewayへ接続してください。

## デモ・開発起動（認証なし）

Authentikとoauth2-proxyを使わずに、UIとRAGバックエンドの疎通を確認できます。

```bash
docker compose -f compose/docker-compose-noauth.yml config
docker compose -f compose/docker-compose-noauth.yml up -d --build
```

次に `disage-ai-ui` を `disage-ai-edge` ネットワークへ接続して起動し、ブラウザから次へアクセスします。

```text
http://127.0.0.1:8088/
```

認証なし構成でも、`embedding-api`、PostgreSQL、Redis、ChromaDB、llama.cppはホストへ直接公開されません。ブラウザからの入口はGatewayのみです。

認証なし構成は開発・デモ専用です。既定の `GATEWAY_BIND_ADDRESS=127.0.0.1` を維持し、LANやインターネットへ公開しないでください。

疎通確認:

```bash
curl http://127.0.0.1:8088/gateway/health
curl http://127.0.0.1:8088/health
curl http://127.0.0.1:8088/ready
```

## 停止

通常構成:

```bash
docker compose -f compose/docker-compose.yml down
```

認証なし構成:

```bash
docker compose -f compose/docker-compose-noauth.yml down
```

永続データを削除したい場合だけ `-v` を付けてください。

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

CIでは通常Compose、認証なしCompose、テストComposeの検証、Ruff、pytest、依存関係監査、Dockerfile検査、秘密情報検査を実行します。

## セキュリティ原則

- 本番・通常運用ではAuthentikを経由しないAPIアクセスを許可しない
- 認証なし構成はlocalhost限定の開発・デモ用途に限定する
- PostgreSQL、Redis、ChromaDB、llama.cpp、embedding-apiをホスト公開しない
- DBパスワードやOIDC SecretをGitへ保存しない
- `student_id` や権限をリクエスト本文だけで信用しない
- 文書登録・削除は管理ロールに限定する

## ロードマップ

1. Phase A: 本番化基盤、秘密情報、Gateway、CI、テスト分離
2. Phase B: QueryServiceのモジュール分割、依存性注入、認可
3. Phase C: 文書バージョン管理とIngestion Worker
4. Phase D: OpenTelemetry、監視、バックアップ、品質評価
