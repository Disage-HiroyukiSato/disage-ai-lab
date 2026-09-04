# DisageAI API仕様書

| 項目 | 内容 |
| --- | --- |
| 文書名 | DisageAI API仕様書 |
| 対象システム | DisageAI Lab |
| 対象リポジトリ | `Disage-HiroyukiSato/disage-ai-lab` |
| 対象基準 | `main` および UI分離PR #6で変更されないAPI実装 |
| API実装 | FastAPI (`services/embedding_api`) |
| 文書版 | 1.0 |
| 作成日 | 2026-09-04 |
| 文字コード | UTF-8 |

## 1. 目的

本書は、DisageAIのWeb UIをバックエンドから分離して独立管理するために、UIとAPIの間で必要となるインターフェースを明文化するものである。

本書では、現行コードから確認できる事実を「現行仕様」として記載する。READMEに記載された将来方針と、コードに実装済みの動作は区別する。

## 2. 適用範囲

対象は、`services/embedding_api/app/main.py` に登録される次のHTTP APIである。

- ヘルスチェック
- Readinessチェック
- Embedding生成
- RAG文書登録
- RAG検索
- 質問・回答生成
- 会話セッション一覧
- 会話セッション詳細

llama.cpp、ChromaDB、PostgreSQL、Redisなどの内部サービスAPIは、ブラウザや外部クライアントへ公開するAPIではないため、本書の対象外とする。

## 3. システム境界

```text
ブラウザ／APIクライアント
        ↓ HTTPS
Gateway (Nginx + oauth2-proxy)
        ↓ HTTP（Docker内部ネットワーク）
Embedding API (FastAPI)
        ↓
LLM／ChromaDB／PostgreSQL／Redis
```

### 3.1 公開入口

- 公開入口はGatewayのみとする。
- `embedding-api:8010` はDocker内部ネットワークだけに公開する。
- UIおよび外部クライアントは、原則としてGatewayのオリジンへアクセスする。
- UIからAPIを呼び出す場合は、同一オリジンの相対URLを使用する。

### 3.2 ベースURL

環境ごとに異なるため、本書では次の記号を使用する。

```text
{BASE_URL}
```

ローカルの既定例：

```text
http://127.0.0.1:8088
```

本番例：

```text
https://ai.example.com
```

## 4. 共通通信仕様

| 項目 | 仕様 |
| --- | --- |
| プロトコル | 本番はHTTPSを使用する |
| データ形式 | JSON |
| リクエストContent-Type | `application/json` |
| レスポンス文字コード | UTF-8 |
| 日時 | PostgreSQLから返る日時はJSONへシリアライズ可能な形式で返す想定。ただし現行コードではレスポンスモデル未定義 |
| APIバージョン | 現行APIには `/api/v1` などのパスバージョンがない |
| タイムアウト | GatewayのAPI向け `proxy_read_timeout` は600秒 |
| CORS | 同一オリジン利用を前提とし、FastAPI側のCORS設定は現行実装にない |

## 5. 認証・認可

### 5.1 認証方式

Gatewayでoauth2-proxyを使用し、Authentik OIDCによる認証を行う。

未認証で保護対象へアクセスした場合、Gatewayはoauth2-proxyのサインイン処理へ遷移させる。ブラウザではログイン画面へのリダイレクトが発生し得るため、常にJSONの401レスポンスになるとは限らない。

### 5.2 GatewayからAPIへ渡すヘッダー

現行Gatewayは、認証結果から次のヘッダーをAPIへ渡す。

| ヘッダー | 内容 |
| --- | --- |
| `X-Authenticated-User` | 認証済みユーザー識別子 |
| `X-Authenticated-Email` | 認証済みメールアドレス |
| `X-Access-Token` | oauth2-proxyが返したアクセストークン |
| `Authorization` | 上流から取得したAuthorizationヘッダー |
| `X-Request-ID` | Gatewayが付与するリクエストID |
| `X-Forwarded-Proto` | 元の通信スキーム |
| `Host` | クライアントが指定したHost |

### 5.3 現行認可実装上の注意

- FastAPIルーター内では、認証ヘッダーを使用したユーザー識別・ロール検証を行っていない。
- `student_id` は `POST /query` のリクエスト本文、または履歴APIのクエリパラメータから受け取る。
- 現行コードでは、認証ユーザーと `student_id` の所有関係を検証していない。
- READMEには「文書登録・削除は管理ロールに限定する」とあるが、`POST /documents` の管理ロール検査は未実装である。
- 文書削除APIは現行ルーターには存在しない。

以上は現行仕様として固定すべき内容ではなく、別途修正すべきセキュリティ課題である。

## 6. 共通HTTPステータス

| ステータス | 意味 | 主な発生条件 |
| --- | --- | --- |
| `200 OK` | 正常終了 | 各APIの正常処理 |
| `401 Unauthorized`／ログイン遷移 | 未認証 | Gatewayの認証要求 |
| `404 Not Found` | 対象なし | 会話セッション詳細、未定義パス |
| `422 Unprocessable Entity` | 入力検証エラー | Pydantic／FastAPIの型・必須・長さ・範囲違反 |
| `500 Internal Server Error` | サーバー内部エラー | Embedding、文書登録、未処理例外など |
| `503 Service Unavailable` | 依存サービス準備未完了 | `/ready` でChromaDB確認に失敗 |

## 7. エラーレスポンス

現行実装ではエラー生成元によって形式が統一されていない。

### 7.1 アプリケーション共通例外

`DisageException` および未処理例外は、原則として次の形式になる。

```json
{
  "success": false,
  "message": "Internal Server Error"
}
```

### 7.2 FastAPI `HTTPException`

ルーターが `HTTPException` を送出した場合は、FastAPI標準の `detail` が付く。

```json
{
  "detail": {
    "success": false,
    "message": "エラー内容"
  }
}
```

### 7.3 入力検証エラー

Pydanticの入力検証に失敗した場合は、FastAPI標準の422形式になる。

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "question"],
      "msg": "String should have at least 1 character",
      "input": "",
      "ctx": {
        "min_length": 1
      }
    }
  ]
}
```

UIはエラー本文が単一形式であると仮定せず、`message`、`detail.message`、`detail[]` の順に解釈し、解釈できない場合はHTTPステータスを表示する必要がある。

## 8. API一覧

| No. | メソッド | パス | 用途 | 主な利用者 |
| ---: | --- | --- | --- | --- |
| 1 | GET | `/health` | APIプロセス生存確認 | Gateway、運用監視 |
| 2 | GET | `/ready` | ChromaDBを含む準備完了確認 | 運用監視 |
| 3 | POST | `/embedding` | テキストのEmbedding生成 | 開発・内部検証 |
| 4 | POST | `/documents` | RAG文書登録 | 文書登録UI、管理処理 |
| 5 | POST | `/retrieval` | RAG検索のみ実行 | 開発・評価処理 |
| 6 | POST | `/query` | RAG検索とLLM回答生成 | 質問UI |
| 7 | GET | `/history/sessions` | 受講生の会話セッション一覧 | 履歴UI |
| 8 | GET | `/history/sessions/{session_id}` | セッション内の会話詳細 | 履歴UI |

## 9. GET `/health`

### 9.1 概要

FastAPIプロセスが応答可能か確認する。依存サービスの接続確認は行わない。

### 9.2 リクエスト

パスパラメータ、クエリパラメータ、リクエスト本文はない。

```bash
curl "{BASE_URL}/health"
```

### 9.3 正常レスポンス

```json
{
  "success": true,
  "status": "alive"
}
```

## 10. GET `/ready`

### 10.1 概要

ChromaDBのコレクション件数を取得し、APIがRAG検索を受け付けられる状態か確認する。

### 10.2 正常レスポンス

```json
{
  "success": true,
  "status": "ready",
  "documents": 125
}
```

| 項目 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `success` | boolean | ○ | 成功時は `true` |
| `status` | string | ○ | 正常時は `ready` |
| `documents` | integer | ○ | ChromaDBコレクション内のレコード数。文書ファイル数ではなくチャンク数となる可能性がある |

### 10.3 依存サービス異常

HTTPステータス：`503`

```json
{
  "detail": {
    "success": false,
    "message": "ChromaDBへの接続エラー内容"
  }
}
```

## 11. POST `/embedding`

### 11.1 概要

指定されたテキストをEmbeddingモデルへ渡し、ベクトルを返す。

### 11.2 リクエスト

```json
{
  "text": "Javaの継承について説明してください。"
}
```

| 項目 | 型 | 必須 | 制約・既定値 | 説明 |
| --- | --- | --- | --- | --- |
| `text` | string | ○ | 現行モデルでは最小長・最大長未指定 | ベクトル化する文字列 |

### 11.3 正常レスポンス

```json
{
  "success": true,
  "dimension": 1024,
  "embedding": [0.0123, -0.0456, 0.0789]
}
```

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `success` | boolean | 成功時は `true` |
| `dimension` | integer | ベクトルの次元数 |
| `embedding` | array&lt;number&gt; | Embeddingベクトル |

`dimension` は使用モデルに依存するため、クライアント側で固定値として扱わない。

### 11.4 エラー

内部処理に失敗した場合はHTTP `500` となり、FastAPI `HTTPException` 形式で返る。

## 12. POST `/documents`

### 12.1 概要

テキストをチャンク分割し、Embeddingを生成して指定ChromaDBコレクションへ登録する。登録成功後、検索キャッシュが有効なら検索キャッシュ全体を無効化する。

### 12.2 リクエスト

```json
{
  "document_id": "java-basic-01",
  "title": "Java基礎 第1章",
  "category": "Java",
  "keywords": "Java,クラス,継承",
  "chapter": "第1章",
  "section": "1.3 継承",
  "language": "ja",
  "page_reference": "p.12-13",
  "collection": "java_training",
  "text": "継承とは、既存クラスのフィールドやメソッドを引き継いで新しいクラスを定義する仕組みです。"
}
```

| 項目 | 型 | 必須 | 制約・既定値 | 説明 |
| --- | --- | --- | --- | --- |
| `document_id` | string | ○ | 長さ制約未指定 | 文書識別子 |
| `title` | string | 省略可 | `""` | 文書タイトル |
| `category` | string | 省略可 | `"General"` | 文書カテゴリ |
| `keywords` | string | 省略可 | `""` | キーワード。現行型は文字列 |
| `chapter` | string | 省略可 | `""` | 章情報 |
| `section` | string | 省略可 | `""` | 節情報 |
| `language` | string | 省略可 | `""` | 言語情報 |
| `page_reference` | string / null | 省略可 | `null` | 原資料のページ表記。例：`p.12`、`12-13` |
| `collection` | string | 省略可 | `""` | 登録先コレクション。空の場合は環境設定 `CHROMA_COLLECTION` |
| `text` | string | ○ | 1文字以上 | RAGへ登録する本文 |

### 12.3 登録メタデータ

各チャンクには少なくとも、登録処理を通じて次のメタデータが使用される。

- `document_id`
- `chunk_no`
- `title`
- `category`
- `keywords`
- `chapter`
- `section`
- `language`
- `page_reference`（指定された場合）

### 12.4 正常レスポンス

```json
{
  "success": true,
  "document_id": "java-basic-01",
  "collection": "java_training",
  "chunks": 3,
  "page_reference": "p.12-13"
}
```

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `success` | boolean | 成功時は `true` |
| `document_id` | string | 登録対象の文書ID |
| `collection` | string | 実際に使用したコレクション名 |
| `chunks` | integer | 登録されたチャンク数 |
| `page_reference` | string / null | リクエストで指定されたページ情報 |

### 12.5 冪等性・重複登録

現行ルーターからは、同一 `document_id` を再登録した場合に置換、追加、重複排除のどれになるかを契約として保証できない。UIは再送を自動的に繰り返さないこと。冪等性は将来APIで明示する必要がある。

### 12.6 認可上の注意

本APIは管理機能として扱うべきだが、現行FastAPIコードには管理ロール検査がない。

## 13. POST `/retrieval`

### 13.1 概要

LLMによる回答生成を行わず、RAG検索結果のみ返す。

### 13.2 リクエスト

```json
{
  "question": "Javaの継承とは何ですか。",
  "limit": 5,
  "document_id": null,
  "category": "Java",
  "title": null,
  "keywords": null
}
```

| 項目 | 型 | 必須 | 既定値 | 説明 |
| --- | --- | --- | --- | --- |
| `question` | string | ○ | なし | 検索質問。現行モデルでは長さ制約未指定 |
| `limit` | integer | 省略可 | `5` | 取得件数。現行モデルでは上下限未指定 |
| `document_id` | string / null | 省略可 | `null` | 文書IDフィルター |
| `category` | string / null | 省略可 | `null` | カテゴリフィルター |
| `title` | string / null | 省略可 | `null` | タイトルフィルター |
| `keywords` | string / null | 省略可 | `null` | キーワードフィルター |

### 13.3 正常レスポンス

```json
{
  "query": "Javaの継承とは何ですか。",
  "total": 1,
  "elapsed_ms": 42,
  "items": [
    {
      "document": "継承とは、既存クラスの機能を引き継ぐ仕組みです。",
      "score": 0.91,
      "distance": 0.09,
      "metadata": {
        "document_id": "java-basic-01",
        "chunk_no": 2,
        "title": "Java基礎 第1章",
        "page_reference": "p.12"
      }
    }
  ]
}
```

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `query` | string | 検索に使用したクエリ |
| `total` | integer | 返却件数 |
| `elapsed_ms` | integer | 検索処理時間（ミリ秒） |
| `items` | array | 検索結果 |
| `items[].document` | string | チャンク本文 |
| `items[].score` | number | 検索／Rerank後スコア |
| `items[].distance` | number | ベクトル距離。小さいほど近い想定 |
| `items[].metadata` | object | 文書メタデータ。拡張可能な可変オブジェクト |

`metadata` の未知項目をクライアントが拒否しないこと。

## 14. POST `/query`

### 14.1 概要

質問を受け付け、クエリ解析、RAG検索、Answerability判定、LLM回答生成、根拠資料整形、必要に応じた会話履歴保存を行う。

### 14.2 リクエスト

```json
{
  "question": "Javaの継承について、初学者向けに説明してください。",
  "limit": 5,
  "student_id": "student-001",
  "session_id": "session-20260904-001"
}
```

| 項目 | 型 | 必須 | 制約・既定値 | 説明 |
| --- | --- | --- | --- | --- |
| `question` | string | ○ | 1～4000文字 | 質問本文 |
| `limit` | integer | 省略可 | 環境変数 `DEFAULT_LIMIT`、1～20 | 取得候補数 |
| `student_id` | string / null | 省略可 | 最大128文字、`null` | 受講生ID。学習章の検索補正などに使用 |
| `session_id` | string / null | 省略可 | 最大128文字、`null` | 会話セッションID。履歴取得・保存に使用 |

`session_id` を指定しない場合、会話履歴は取得・保存されない。APIは現行実装上、セッションIDを自動発行しないため、UI側でUUIDなど衝突しにくい識別子を生成する必要がある。

### 14.3 正常レスポンス

```json
{
  "answer": "継承は、既存のクラスが持つ機能を新しいクラスへ引き継ぐ仕組みです。",
  "sources": [
    {
      "document_id": "java-basic-01",
      "chunk_no": "2",
      "title": "Java基礎 第1章",
      "page_reference": "p.12"
    }
  ],
  "source_pages": ["p.12"],
  "elapsed_ms": 3150,
  "retrieved_count": 5,
  "documents": [
    {
      "document": "継承とは、既存クラスの機能を引き継ぐ仕組みです。",
      "score": 0.91,
      "distance": 0.09,
      "page": "p.12",
      "metadata": {
        "document_id": "java-basic-01",
        "chunk_no": 2,
        "title": "Java基礎 第1章",
        "page_reference": "p.12"
      }
    }
  ],
  "answerability_status": "FULL",
  "answerability_reason": "質問に回答するための根拠が資料内に確認できます。",
  "follow_ups": [
    {
      "question": "オーバーライドとは何ですか。",
      "reason": "継承したメソッドを変更する仕組みを理解するためです。"
    }
  ],
  "metadata": {
    "query_analysis_elapsed_ms": 50,
    "retrieval_elapsed_ms": 300,
    "answerability_elapsed_ms": 100,
    "llm_elapsed_ms": 2700,
    "total_elapsed_ms": 3150,
    "cache_hit": false,
    "fallback_used": false,
    "retrieved_count": 5,
    "gate_candidate_count": 5,
    "final_context_count": 3
  }
}
```

### 14.4 レスポンス項目

| 項目 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `answer` | string | ○ | LLMが生成した最終回答。既定値は空文字 |
| `sources` | array | ○ | 回答根拠としてUI表示する資料情報 |
| `source_pages` | array&lt;string&gt; | ○ | RAGメタデータから取得した根拠ページ。APIやLLMで推測しない |
| `elapsed_ms` | integer | ○ | 後方互換項目。`metadata.total_elapsed_ms` と同値 |
| `retrieved_count` | integer | ○ | 後方互換項目。`metadata.retrieved_count` と同値 |
| `documents` | array | ○ | 最終回答生成に使用した検索結果詳細 |
| `answerability_status` | string / null | ○ | `FULL`、`PARTIAL`、`NONE` または `null` |
| `answerability_reason` | string | ○ | Answerability判定理由 |
| `follow_ups` | array | ○ | 関連質問。回答不能時などは空配列 |
| `metadata` | object | ○ | 処理時間・検索件数などのシステム情報 |

### 14.5 `sources[]`

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `document_id` | string | 根拠文書ID |
| `chunk_no` | string | 根拠チャンク番号。APIレスポンスでは文字列 |
| `title` | string | 根拠資料タイトル |
| `page_reference` | string / null | 正式なページ参照項目 |

### 14.6 `documents[]`

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `document` | string | 検索チャンク本文 |
| `score` | number | Rerankなどを反映したスコア |
| `distance` | number | ベクトル距離 |
| `page` | string / null | 後方互換項目。`metadata.page_reference`、`page`、`page_number` の順に取得 |
| `metadata` | object | 可変メタデータ |

ページ情報の正式名称は `page_reference` である。`documents[].page` は後方互換項目としてのみ使用する。

### 14.7 `follow_ups[]`

| 項目 | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| `question` | string | 1文字以上 | 次に学ぶ質問 |
| `reason` | string | 1文字以上 | 質問を提示する理由 |

### 14.8 `metadata`

| 項目 | 型 | 説明 |
| --- | --- | --- |
| `query_analysis_elapsed_ms` | integer | 質問正規化・解析・書き換え時間 |
| `retrieval_elapsed_ms` | integer | RAG検索時間 |
| `answerability_elapsed_ms` | integer | Answerability判定時間 |
| `llm_elapsed_ms` | integer | LLM回答生成時間 |
| `total_elapsed_ms` | integer | 全体処理時間 |
| `cache_hit` | boolean | 検索キャッシュヒット有無 |
| `fallback_used` | boolean | フォールバック検索実行有無 |
| `retrieved_count` | integer | 検索候補数 |
| `gate_candidate_count` | integer | Answerability Gate判定候補数 |
| `final_context_count` | integer | 最終的にLLMへ渡したコンテキスト数 |

時間項目の単位はミリ秒である。

### 14.9 Answerability

| 値 | 意味 | UIの推奨動作 |
| --- | --- | --- |
| `FULL` | 資料に十分な根拠がある | 通常回答として表示 |
| `PARTIAL` | 一部の根拠のみ確認できる | 不足があることを明示して表示 |
| `NONE` | 関連資料を確認できない | 「資料からは確認できません。」を基本表示 |
| `null` | 判定値なし | 不明状態として扱い、FULLとみなさない |

### 14.10 処理時間

LLM回答生成には時間がかかる。Gatewayの読み取りタイムアウトは600秒である。UIは送信中の二重送信を防止し、処理中表示を行うこと。

現行APIはストリーミングレスポンスではなく、回答完成後にJSONを一括返却する。

## 15. GET `/history/sessions`

### 15.1 概要

指定した受講生IDに紐づく会話セッション一覧を返すことを意図したAPIである。

### 15.2 クエリパラメータ

| 項目 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `student_id` | string | ○ | 受講生ID |

```bash
curl "{BASE_URL}/history/sessions?student_id=student-001"
```

### 15.3 意図されているレスポンス外形

```json
{
  "success": true,
  "student_id": "student-001",
  "total": 1,
  "sessions": [
    {
      "session_id": "session-20260904-001"
    }
  ]
}
```

`sessions[]` の完全な項目定義は、現行コードにレスポンスモデルが存在しないため確定できない。

### 15.4 現行実装の既知不整合

ルーターは `conversation_service.get_sessions(student_id)` を呼び出すが、現行の `ConversationService` に `get_sessions` メソッドが存在しない。このため、現行コードのまま呼び出すと未処理例外となり、HTTP `500` になる可能性が高い。

本APIはサービス実装とレスポンスモデルを追加してから正式契約とする必要がある。

## 16. GET `/history/sessions/{session_id}`

### 16.1 概要

指定したセッションの全会話を時系列で返すことを意図したAPIである。

### 16.2 パスパラメータ

| 項目 | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_id` | string | ○ | 会話セッションID |

### 16.3 意図されているレスポンス外形

```json
{
  "success": true,
  "session_id": "session-20260904-001",
  "total": 2,
  "messages": [
    {
      "role": "user",
      "content": "継承とは何ですか。",
      "is_off_topic": false
    },
    {
      "role": "assistant",
      "content": "継承は既存クラスの機能を引き継ぐ仕組みです。",
      "is_off_topic": false
    }
  ]
}
```

`messages[]` の完全な項目定義は、現行コードにレスポンスモデルが存在しないため確定できない。

### 16.4 対象なし

意図上は、メッセージが存在しない場合にHTTP `404` を返す。

```json
{
  "detail": {
    "success": false,
    "message": "指定されたセッションが見つかりません、または会話履歴が存在しません。"
  }
}
```

### 16.5 現行実装の既知不整合

ルーターは `conversation_service.get_session_detail(session_id)` を呼び出すが、現行の `ConversationService` に `get_session_detail` メソッドが存在しない。このため、現行コードのままでは404判定へ到達せず、HTTP `500` になる可能性が高い。

## 17. UIが現在使用するAPI

| UI機能 | API | UI側呼び出し |
| --- | --- | --- |
| 文書登録 | `POST /documents` | `static/js/documents.js` |
| 質問・回答 | `POST /query` | `static/js/query.js` |
| セッション一覧 | `GET /history/sessions?student_id=...` | `static/js/history.js` |
| セッション詳細 | `GET /history/sessions/{session_id}` | `static/js/history.js` |

UIは `/embedding`、`/retrieval`、`/health`、`/ready` を通常画面から直接呼び出していない。

## 18. Gatewayルーティング

UI分離PR #6適用後の主なルーティングは次のとおりである。

| パス | 転送先 |
| --- | --- |
| `/oauth2/*` | oauth2-proxy |
| `/embedding` | embedding-api |
| `/documents` および `/documents/*` | embedding-api |
| `/query` および `/query/*` | embedding-api |
| `/history` および `/history/*` | embedding-api |
| `/retrieval` および `/retrieval/*` | embedding-api |
| `/health` | embedding-api |
| `/ready` | embedding-api |
| `/docs` | embedding-api |
| `/redoc` | embedding-api |
| `/openapi.json` | embedding-api |
| その他の画面・静的ファイル | ui |

Gateway自身の生存確認は `/gateway/health` であり、FastAPIの `/health` とは異なる。

## 19. OpenAPIと対話型ドキュメント

FastAPIにより次が自動提供される。

| パス | 内容 |
| --- | --- |
| `/openapi.json` | OpenAPI JSON |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |

これらもGateway認証の対象である。

現行OpenAPIはコードから動的生成されるだけで、リポジトリ内にスナップショットとして保存されていない。そのため、API変更差分をGit上で直接レビューできない。

## 20. クライアント実装規約

UIまたは外部クライアントは次を守る。

1. API URLをコンテナ名へ固定せず、Gatewayの同一オリジン相対URLを使用する。
2. `Content-Type: application/json` を指定する。
3. HTTPステータスを確認してからレスポンスを描画する。
4. エラーレスポンスが複数形式あることを考慮する。
5. `metadata` の未知項目を許容する。
6. `/query` の処理中は二重送信を防止する。
7. `answer`、資料本文などをHTMLとして直接挿入せず、サニタイズする。
8. `answerability_status` が `null` の場合に `FULL` とみなさない。
9. `source_pages` や `page_reference` が空の場合、ページを推測しない。
10. `student_id` と `session_id` に個人情報を直接埋め込まない。

## 21. 互換性と変更管理

### 21.1 破壊的変更に該当するもの

- APIパスまたはHTTPメソッドの変更
- 必須リクエスト項目の追加
- 項目型の変更
- 列挙値の削除・名称変更
- レスポンス項目の削除
- `null` 許容から非許容への変更
- エラーHTTPステータスの変更
- 認証方式や必須ヘッダーの変更

### 21.2 原則として後方互換な変更

- 省略可能なリクエスト項目の追加
- レスポンス項目の追加
- `metadata` 内の項目追加
- 説明文の修正

ただし、クライアントが未知項目を拒否する実装の場合は互換性が失われるため、UI側でも契約テストを行う。

### 21.3 推奨バージョニング

現行URLを直ちに変更せず、破壊的変更が必要になった時点で `/api/v1` を導入する。導入時は旧パスを一定期間残し、非推奨化と削除予定を明示する。

## 22. API仕様管理方法

次を推奨する。

1. PydanticモデルとFastAPIルーターを実装上の正とする。
2. CIで `openapi.json` を生成する。
3. `docs/api/openapi.json` と生成結果を比較する。
4. 差分がある場合は、仕様変更を伴うPRとしてレビューする。
5. 本書 `docs/api/API仕様書.md` も意味上の変更に合わせて更新する。
6. UI側はOpenAPIからTypeScript型を生成するか、契約テストへ利用する。

推奨配置：

```text
docs/
└─ api/
   ├─ API仕様書.md
   └─ openapi.json
```

## 23. 現行実装の既知課題

| No. | 重要度 | 課題 | 影響 | 推奨対応 |
| ---: | --- | --- | --- | --- |
| 1 | 高 | `ConversationService.get_sessions` が存在しない | 履歴一覧が500になる可能性 | サービス実装とレスポンスモデルを追加 |
| 2 | 高 | `ConversationService.get_session_detail` が存在しない | 履歴詳細が500になる可能性 | サービス実装とレスポンスモデルを追加 |
| 3 | 高 | 認証ユーザーと `student_id` の関連検証がない | 他受講生履歴へアクセスできる可能性 | 認証ヘッダーを基準にサーバー側で識別 |
| 4 | 高 | 文書登録の管理ロール検査がない | 一般ユーザーが文書登録できる可能性 | Authentikグループ／ロール検証を実装 |
| 5 | 中 | エラーレスポンス形式が不統一 | UIのエラー処理が複雑 | 共通エラーモデルとハンドラーを導入 |
| 6 | 中 | APIパスバージョンがない | 将来の破壊的変更が困難 | `/api/v1` の導入方針を決定 |
| 7 | 中 | OpenAPIスナップショットがGit管理されていない | 意図しない仕様変更を検出しにくい | CIで生成・差分検査 |
| 8 | 中 | `/documents` の冪等性が契約化されていない | 再送時に重複登録の可能性 | PUTまたは冪等キーを検討 |
| 9 | 低 | `/embedding` の入力長制約がない | 過大入力による負荷 | 最大長を定義 |
| 10 | 低 | `/retrieval.limit` の範囲制約がない | 過大件数指定による負荷 | 1～20などの範囲を定義 |

## 24. 疎通確認例

以下は、認証済みCookieなどが利用可能な環境を前提とする。実際の認証情報をコマンド履歴やリポジトリへ保存しないこと。

### 24.1 Gateway

```bash
curl "{BASE_URL}/gateway/health"
```

### 24.2 API生存確認

```bash
curl "{BASE_URL}/health"
```

### 24.3 文書登録

```bash
curl -X POST "{BASE_URL}/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "java-basic-01",
    "title": "Java基礎",
    "category": "Java",
    "page_reference": "p.12",
    "collection": "java_training",
    "text": "継承とは、既存クラスの機能を引き継ぐ仕組みです。"
  }'
```

### 24.4 質問

```bash
curl -X POST "{BASE_URL}/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Javaの継承とは何ですか。",
    "limit": 5,
    "student_id": "student-001",
    "session_id": "session-001"
  }'
```

## 25. 実装参照先

| 仕様領域 | 主な参照ファイル |
| --- | --- |
| アプリケーション登録 | `services/embedding_api/app/main.py` |
| Health／Ready | `services/embedding_api/app/routers/health.py` |
| Embedding | `services/embedding_api/app/routers/embedding.py` |
| 文書登録 | `services/embedding_api/app/routers/document.py` |
| RAG検索 | `services/embedding_api/app/routers/retrieval.py` |
| 質問・回答 | `services/embedding_api/app/routers/query.py` |
| 履歴 | `services/embedding_api/app/routers/history.py` |
| Queryレスポンス | `services/embedding_api/app/models/query_response.py` |
| Queryメタデータ | `services/embedding_api/app/models/query_metadata_response.py` |
| 根拠資料 | `services/embedding_api/app/models/query_source_response.py` |
| 検索結果 | `services/embedding_api/app/models/query_document_response.py` |
| Retrievalリクエスト | `services/embedding_api/app/models/retrieval_request.py` |
| 会話処理 | `services/embedding_api/app/services/conversation/conversation_service.py` |
| 共通例外 | `services/embedding_api/app/core/handlers.py` |
| Gateway | `gateway/nginx.conf` |

## 26. 文書更新ルール

- APIコードを変更するPRでは、本書とOpenAPIスナップショットへの影響を確認する。
- 項目追加・変更・削除時は、型、必須性、既定値、制約、`null` 許容を更新する。
- 正常系だけでなく、HTTPステータスとエラー形式も更新する。
- 現行実装と将来予定を混在させず、未実装項目は明示する。
- UI側の変更が必要な場合は、対象UI機能と最低対応バージョンを記録する。

