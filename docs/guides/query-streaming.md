# 質問APIのトークンストリーミング

## 互換性

- POST /query: 従来のJSON一括応答を維持。
- POST /query/stream: 同じ入力を受け取り、application/x-ndjsonを返す。
- 検索、再検索、Reranker、Gate、Prompt、関連質問、履歴処理は共通。
- llama.cppの既存 /completion、ChatML、生成条件を維持し、stream=trueでSSEを逐次受信する。完成した回答を後から分割する疑似ストリーミングではない。
- 登録API、ChromaDBボリューム、辞書は変更しない。

## イベント

各イベントはUTF-8の1行JSON。改行まで受信してからJSON解析する。

| type | 内容 |
| --- | --- |
| status | stage: analysis / retrieval / answerability / generation |
| token | text: 回答の追加文字列 |
| heartbeat | 検索等で出力が止まっている間、約10秒間隔。UIは無視してよい |
| complete | /queryと同じ回答フィールドをトップレベルに格納。成功時1回 |
| error | message: 利用者向けエラー。内部詳細はサーバーログのみ |

検索0件やGate NONEではtokenを送らず、定型回答を含むcompleteで終了する。
token連結が回答本文となる。関連質問の生成があるため、最後のtokenからcompleteまで間が空くことがある。
HTTP開始後の例外はHTTP 500ではなくerrorイベント。error後はcompleteを送らない。
入力検証エラーはストリーム開始前に従来どおり422。

## 切断・負荷制御

- ワーカースレッドで同期RAGを実行し、HTTPイベントループを塞がない。
- 接続切断時にキャンセルフラグを設定。次の段階・token処理で終了し、上流レスポンスを閉じる。
- 同期のEmbedding、検索、Gate、関連質問生成は即時強制中断できない。処理完了または各通信のタイムアウト後に終了する。
- 生成SSEの接続タイムアウト10秒、読み取り無通信タイムアウト60秒。
- ストリーム専用ワーカーはAPIプロセスごと最大4、送信待ちは32イベントまで。切断後の終了待ちワーカーも枠を保持する。
- 上限超過はerrorイベント。既存 /query を含むシステム全体の同時実行制限ではない。
- 生成途中の切断・異常では未完成回答を履歴に保存しない。回答生成と関連質問処理の後、履歴保存直前にもキャンセルを確認する。
- 既存のuser/assistant履歴は2回の保存であり、DBトランザクションの一体化や、completeのクライアント受領保証は今回の範囲外。

## 適用

変更を取得したdisage-ai-labルートで、普段使っている環境変数指定を維持して実行する。

```powershell
docker compose -f compose/docker-compose-noauth.yml up -d --build embedding-api
docker compose -f compose/docker-compose-noauth.yml up -d --force-recreate gateway
```

認証ありはdocker-compose.ymlを使用する。認証設定は維持される。
両Gatewayでproxy_bufferingとproxy_cacheを無効化する。
既存UIが /query/stream と status/token/complete/error に対応していればUI変更は不要。

## 検証

GPU、DBを使わないモックテスト：

```powershell
py -m unittest discover -s services/embedding_api/tests -p test_stream_offline.py -v
```

実機ではGatewayの /docs でPOST /query/streamを確認する。
ブラウザは http://localhost:8088/query-ui を開き、DevTools Networkで
Content-Type、status、token、completeを確認する。
回答完了より前に本文が追記されること、検索0件でも終了すること、
ページを閉じた後にワーカーと上流接続が解放されることを確認する。
通常のPOST /queryも同じ代表質問で確認する。

この実装のオフラインテストはモックによるもので、実GPU、実ChromaDB、
Authentik、nginx経由の逐次転送は利用環境での結合確認が必要。
