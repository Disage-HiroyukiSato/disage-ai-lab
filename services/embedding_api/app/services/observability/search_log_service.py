import json
import logging
import threading
import time

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from app.models.retrieval_item import RetrievalItem

logger = logging.getLogger(__name__)


class SearchLogService:

    #
    # ------------------------------------------------------
    # 保存先
    # ------------------------------------------------------
    #
    # 1日1ファイルにローテーションする。
    #
    # 例 : /app/data/search_log/2026-08-10.jsonl
    #

    LOG_DIR = Path(
        "/app/data/search_log"
    )

    #
    # Rerank分析・Hybrid内訳として記録する上位件数
    #
    # 全件記録するとログが肥大化するため、
    # 上位N件のみ詳細を残す。
    #

    TOP_N_DETAIL = 10

    def __init__(self):

        self.lock = threading.Lock()

    def _log_path(self) -> Path:

        today = datetime.now(

            timezone.utc

        ).strftime(

            "%Y-%m-%d"

        )

        return self.LOG_DIR / f"{today}.jsonl"

    #
    # ------------------------------------------------------
    # Rerank前後のitem比較用インデックス作成
    # ------------------------------------------------------
    #
    # RetrievalItemはpydanticモデルでハッシュ化できないため、
    # document文字列をキーとして同一チャンクを紐付ける。
    #
    # multi_query_retrieval_serviceの重複除去と同様に、
    # metadataのdocument_id + chunk_noがあればそちらを
    # 優先的にキーとする。
    #

    def _item_key(
        self,
        item: RetrievalItem
    ) -> str:

        metadata = item.metadata or {}

        document_id = metadata.get(
            "document_id"
        )

        chunk_no = metadata.get(
            "chunk_no"
        )

        if document_id is not None and chunk_no is not None:

            return f"{document_id}:{chunk_no}"

        return item.document

    #
    # ------------------------------------------------------
    # ログ記録
    # ------------------------------------------------------
    #
    # question             : 質問文（正規化前）
    # normalized_question   : 正規化後の質問文
    # retrieved_items       : Rerank前のRetrievalItemリスト
    #                          （Hybrid内訳・distanceを含む）
    # reranked_items         : Rerank後のRetrievalItemリスト
    #                          （score = CrossEncoderスコア）
    # answer                 : LLM回答
    # retrieval_elapsed_ms   : 検索処理時間
    # rerank_elapsed_ms      : Rerank処理時間
    # llm_elapsed_ms         : LLM処理時間
    # total_elapsed_ms       : 全体処理時間
    # cache_hit               : Retrieval Cacheがヒットしたか
    #                            （retrieval_result.elapsed_msでは
    #                            判定できないため、query_service側
    #                            から明示的に渡す）
    #

    def log(

        self,

        question: str,

        normalized_question: str,

        retrieved_items: list[RetrievalItem],

        reranked_items: list[RetrievalItem],

        answer: str,

        retrieval_elapsed_ms: int,

        rerank_elapsed_ms: int,

        llm_elapsed_ms: int,

        total_elapsed_ms: int,

        cache_hit: bool = False

    ) -> None:

        try:

            self._write(

                question=question,

                normalized_question=normalized_question,

                retrieved_items=retrieved_items,

                reranked_items=reranked_items,

                answer=answer,

                retrieval_elapsed_ms=retrieval_elapsed_ms,

                rerank_elapsed_ms=rerank_elapsed_ms,

                llm_elapsed_ms=llm_elapsed_ms,

                total_elapsed_ms=total_elapsed_ms,

                cache_hit=cache_hit

            )

        except Exception:

            #
            # 検索ログの記録失敗はRAG本体の応答を
            # 妨げてはならないため、例外は握りつぶし
            # ログにのみ記録する。
            #

            logger.exception(

                "Search log write failed."

            )

    def _write(

        self,

        question: str,

        normalized_question: str,

        retrieved_items: list[RetrievalItem],

        reranked_items: list[RetrievalItem],

        answer: str,

        retrieval_elapsed_ms: int,

        rerank_elapsed_ms: int,

        llm_elapsed_ms: int,

        total_elapsed_ms: int,

        cache_hit: bool

    ) -> None:

        #
        # 基本情報
        #

        retrieved_count = len(
            retrieved_items
        )

        reranked_count = len(
            reranked_items
        )

        #
        # Hit有無
        #
        # 検索結果があり、かつRerank後も1件以上残った場合を
        # Hitとする（＝LLMへ資料を渡せた場合）。
        #

        hit = (

            retrieved_count > 0

            and reranked_count > 0

        )

        #
        # 検索失敗分析用の失敗理由
        #
        # no_retrieval        : Vector/Hybrid検索で0件
        # rerank_filtered      : 検索はヒットしたがRerankerの
        #                        min_rerank_score未満で全滅
        # ok                  : 正常にLLMへ渡せた
        #

        if retrieved_count == 0:

            failure_reason = "no_retrieval"

        elif reranked_count == 0:

            failure_reason = "rerank_filtered"

        else:

            failure_reason = "ok"

        #
        # Rerank分析
        #
        # Rerank前後で同一チャンクのスコア・順位変化を
        # 上位N件について記録する。
        #

        retrieved_rank: dict[str, int] = {}

        retrieved_score: dict[str, float] = {}

        for index, item in enumerate(

            retrieved_items,

            start=1

        ):

            key = self._item_key(

                item

            )

            retrieved_rank[key] = index

            retrieved_score[key] = item.score

        rerank_detail: list[dict[str, Any]] = []

        for index, item in enumerate(

            reranked_items[:self.TOP_N_DETAIL],

            start=1

        ):

            key = self._item_key(

                item

            )

            before_rank = retrieved_rank.get(
                key
            )

            rerank_detail.append({

                "after_rank": index,

                "before_rank": before_rank,

                "rank_delta": (

                    before_rank - index

                    if before_rank is not None

                    else None

                ),

                "rerank_score": round(
                    item.score,
                    4
                ),

                "distance": round(
                    item.distance,
                    4
                ),

                "document_id": (

                    item.metadata or {}

                ).get(

                    "document_id"

                ),

                "chunk_no": (

                    item.metadata or {}

                ).get(

                    "chunk_no"

                )

            })

        #
        # Hybrid内訳（上位N件）
        #
        # ENABLE_HYBRID_SEARCH=false の場合は
        # 全て0.0のまま記録される。
        #

        hybrid_detail: list[dict[str, Any]] = []

        for index, item in enumerate(

            retrieved_items[:self.TOP_N_DETAIL],

            start=1

        ):

            hybrid_detail.append({

                "rank": index,

                "hybrid_score": round(
                    item.hybrid_score,
                    4
                ),

                "vector_similarity": round(
                    item.vector_similarity,
                    4
                ),

                "bm25_raw_score": round(
                    item.bm25_raw_score,
                    4
                ),

                "distance": round(
                    item.distance,
                    4
                ),

                "document_id": (

                    item.metadata or {}

                ).get(

                    "document_id"

                ),

                "chunk_no": (

                    item.metadata or {}

                ).get(

                    "chunk_no"

                )

            })

        #
        # ログレコード
        #

        record = {

            "timestamp": datetime.now(

                timezone.utc

            ).isoformat(),

            "question": question,

            "normalized_question": normalized_question,

            "retrieved_count": retrieved_count,

            "reranked_count": reranked_count,

            "hit": hit,

            "failure_reason": failure_reason,

            "cache_hit": cache_hit,

            "elapsed_ms": {

                "retrieval": retrieval_elapsed_ms,

                "rerank": rerank_elapsed_ms,

                "llm": llm_elapsed_ms,

                "total": total_elapsed_ms

            },

            "rerank_detail": rerank_detail,

            "hybrid_detail": hybrid_detail,

            "answer_preview": answer[:200]

        }

        #
        # JSON Lines追記
        #

        self.LOG_DIR.mkdir(

            parents=True,

            exist_ok=True

        )

        line = json.dumps(

            record,

            ensure_ascii=False

        )

        with self.lock:

            with self._log_path().open(

                "a",

                encoding="utf-8"

            ) as file:

                file.write(

                    line

                    + "\n"

                )

        logger.info(

            "Search log written : hit=%s "
            "failure_reason=%s "
            "retrieved=%d reranked=%d",

            hit,

            failure_reason,

            retrieved_count,

            reranked_count

        )


search_log_service = SearchLogService()