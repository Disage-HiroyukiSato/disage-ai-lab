import logging
import time

from app.config import settings

from app.services.llm_service import llm_service
from app.services.multi_query_retrieval_service import (
    multi_query_retrieval_service
)
from app.services.prompt_builder import prompt_builder
from app.services.query_normalizer import query_normalizer
from app.services.reranker_service import reranker_service
from app.services.search_log_service import search_log_service

logger = logging.getLogger(__name__)


class QueryService:

    def ask(
        self,
        question: str,
        limit: int = 5
    ):

        overall_start = time.perf_counter()

        logger.info("")
        logger.info("========================================")
        logger.info("RAG Query Start")
        logger.info("========================================")
        logger.info(
            "Question : %s",
            question
        )
        logger.info("")

        #
        # Query Normalize
        #

        normalized_question = query_normalizer.normalize(
            question
        )

        logger.info(
            "Normalized : %s",
            normalized_question
        )

        #
        # Queryが空になった場合
        #

        if not normalized_question:

            total_elapsed = int(
                (
                    time.perf_counter() - overall_start
                ) * 1000
            )

            logger.warning(
                "Normalized question is empty."
            )

            logger.info("========================================")
            logger.info("RAG Query End")
            logger.info("========================================")

            #
            # 検索ログ
            #
            # 正規化後に空になったケースも
            # 検索失敗分析の対象として記録する。
            #

            search_log_service.log(

                question=question,

                normalized_question=normalized_question,

                retrieved_items=[],

                reranked_items=[],

                answer="質問内容を確認できませんでした。",

                retrieval_elapsed_ms=0,

                rerank_elapsed_ms=0,

                llm_elapsed_ms=0,

                total_elapsed_ms=total_elapsed,

                cache_hit=False

            )

            return {
                "answer": "質問内容を確認できませんでした。",
                "elapsed_ms": total_elapsed,
                "retrieved_count": 0,
                "documents": []
            }

        #
        # Multi Query Retrieval
        #
        # Query Expansionされた複数Queryを使用して
        # Vector Retrievalを実行する。
        #
        # Reranker実行前の候補数を確保するため、
        # 最終回答件数ではなく、
        # retrieval_candidate_sizeを渡す。
        #

        retrieval_start = time.perf_counter()

        retrieval_result = multi_query_retrieval_service.search(
            question=normalized_question,
            limit=settings.retrieval_candidate_size
        )

        retrieval_elapsed = int(
            (
                time.perf_counter() - retrieval_start
            ) * 1000
        )

        logger.info(
            "Multi Query Retrieval Time : %d ms",
            retrieval_elapsed
        )

        logger.info(
            "Retrieved : %d",
            retrieval_result.total
        )

        #
        # Retrieval結果なし
        #
        # 資料が存在しない場合はLLMへ問い合わせない。
        #

        if retrieval_result.total == 0:

            total_elapsed = int(
                (
                    time.perf_counter() - overall_start
                ) * 1000
            )

            logger.info(
                "No documents retrieved."
            )

            logger.info(
                "========================================"
            )
            logger.info(
                "RAG Query End"
            )
            logger.info(
                "========================================"
            )

            #
            # 検索ログ
            #
            # failure_reason=no_retrieval として記録される。
            #

            search_log_service.log(

                question=question,

                normalized_question=normalized_question,

                retrieved_items=[],

                reranked_items=[],

                answer="資料から回答できませんでした。",

                retrieval_elapsed_ms=retrieval_elapsed,

                rerank_elapsed_ms=0,

                llm_elapsed_ms=0,

                total_elapsed_ms=total_elapsed,

                cache_hit=retrieval_result.cache_hit

            )

            return {
                "answer": "資料から回答できませんでした。",
                "elapsed_ms": total_elapsed,
                "retrieved_count": 0,
                "documents": []
            }

        #
        # Retrieval結果ログ
        #

        logger.info("----------------------------------------")
        logger.info("Retrieved Documents")
        logger.info("----------------------------------------")

        for index, item in enumerate(
            retrieval_result.items,
            start=1
        ):

            logger.info(
                "[%d] distance=%.4f",
                index,
                item.distance
            )

            logger.info(
                "Metadata : %s",
                item.metadata
            )

        #
        # Reranker
        #
        # 複数Queryの検索結果を統合した後、
        # Rerankerは1回だけ実行する。
        #

        rerank_start = time.perf_counter()

        reranked_items = reranker_service.rerank(
            question=normalized_question,
            items=retrieval_result.items,
            limit=limit
        )

        rerank_elapsed = int(
            (
                time.perf_counter() - rerank_start
            ) * 1000
        )

        logger.info(
            "Reranker Time : %d ms",
            rerank_elapsed
        )

        #
        # Reranker後に0件になった場合
        #

        if not reranked_items:

            total_elapsed = int(
                (
                    time.perf_counter() - overall_start
                ) * 1000
            )

            logger.info(
                "No documents passed reranker threshold."
            )

            logger.info(
                "========================================"
            )
            logger.info(
                "RAG Query End"
            )
            logger.info(
                "========================================"
            )

            #
            # 検索ログ
            #
            # failure_reason=rerank_filtered として記録される。
            #
            # retrieval_result.items（Rerank前）は
            # min_rerank_scoreでの足切り分析に必要なため、
            # retrieved_itemsとして渡す。
            #

            search_log_service.log(

                question=question,

                normalized_question=normalized_question,

                retrieved_items=retrieval_result.items,

                reranked_items=[],

                answer="資料から回答できませんでした。",

                retrieval_elapsed_ms=retrieval_elapsed,

                rerank_elapsed_ms=rerank_elapsed,

                llm_elapsed_ms=0,

                total_elapsed_ms=total_elapsed,

                cache_hit=retrieval_result.cache_hit

            )

            return {
                "answer": "資料から回答できませんでした。",
                "elapsed_ms": total_elapsed,
                "retrieved_count": 0,
                "documents": []
            }

        #
        # Context生成
        #

        contexts = [

            item.document

            for item in reranked_items

        ]

        #
        # Prompt生成
        #

        prompt = prompt_builder.build(
            question,
            contexts
        )

        #
        # Promptログ
        #

        if settings.log_prompt:

            logger.debug(
                "Prompt\n%s",
                prompt
            )

        #
        # LLM問い合わせ
        #

        llm_start = time.perf_counter()

        answer = llm_service.ask(
            prompt
        )

        llm_elapsed = int(
            (
                time.perf_counter() - llm_start
            ) * 1000
        )

        #
        # Total Time
        #

        total_elapsed = int(
            (
                time.perf_counter() - overall_start
            ) * 1000
        )

        #
        # Answer Log
        #

        logger.info("----------------------------------------")
        logger.info("RAG Query Result")
        logger.info("----------------------------------------")

        logger.info(
            "Answer Preview : %s",
            answer[:300]
        )

        logger.info(
            "Retrieved Count : %d",
            retrieval_result.total
        )

        logger.info(
            "Reranked Count : %d",
            len(reranked_items)
        )

        logger.info(
            "Retrieval Time : %d ms",
            retrieval_elapsed
        )

        logger.info(
            "Reranker Time : %d ms",
            rerank_elapsed
        )

        logger.info(
            "LLM Time : %d ms",
            llm_elapsed
        )

        logger.info(
            "Total Time : %d ms",
            total_elapsed
        )

        logger.info("========================================")
        logger.info("RAG Query End")
        logger.info("========================================")
        logger.info("")

        #
        # 検索ログ
        #
        # failure_reason=ok として記録される。
        #
        # retrieval_result.items（Rerank前、Hybrid内訳を含む）と
        # reranked_items（Rerank後）の両方を渡すことで、
        # Rerankによる順位変化・Hybridスコア内訳の両方を
        # 1レコードで分析できるようにする。
        #

        search_log_service.log(

            question=question,

            normalized_question=normalized_question,

            retrieved_items=retrieval_result.items,

            reranked_items=reranked_items,

            answer=answer,

            retrieval_elapsed_ms=retrieval_elapsed,

            rerank_elapsed_ms=rerank_elapsed,

            llm_elapsed_ms=llm_elapsed,

            total_elapsed_ms=total_elapsed,

            cache_hit=retrieval_result.cache_hit

        )

        return {
            "answer": answer,
            "documents": reranked_items,
            "retrieved_count": len(reranked_items),
            "elapsed_ms": total_elapsed
        }


query_service = QueryService()