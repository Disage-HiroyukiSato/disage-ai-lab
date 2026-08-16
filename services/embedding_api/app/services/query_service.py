import logging
import time

from app.config import settings

from app.services.collection_router_service import (
    collection_router_service
)
from app.services.conversation_service import conversation_service
from app.services.llm_service import llm_service
from app.services.multi_query_retrieval_service import (
    multi_query_retrieval_service
)
from app.services.off_topic_router_service import (
    off_topic_router_service
)
from app.services.progress_service import progress_service
from app.services.prompt_builder import prompt_builder
from app.services.query_normalizer import query_normalizer
from app.services.query_rewrite_service import query_rewrite_service
from app.services.reranker_service import reranker_service
from app.services.search_log_service import search_log_service

logger = logging.getLogger(__name__)


class QueryService:

    def ask(
        self,
        question: str,
        limit: int = 5,
        student_id: str | None = None,
        session_id: str | None = None
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
        logger.info(
            "student_id=%s session_id=%s",
            student_id,
            session_id
        )
        logger.info("")

        normalized_question = query_normalizer.normalize(
            question
        )

        logger.info(
            "Normalized : %s",
            normalized_question
        )

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

        collection_name = collection_router_service.route(

            normalized_question

        )

        logger.info(

            "Collection Router : %s",

            collection_name

        )

        current_chapter = progress_service.get_current_chapter(

            student_id

        )

        #
        # Phase17 : 教材外判定
        #
        # 元の質問（書き換え前）に対して判定する。
        # 書き換え後の質問は教材寄りの表現に補完されて
        # しまう可能性があり、受講生が実際に打った言葉の
        # 教材外らしさを見たいため。
        #

        is_off_topic = off_topic_router_service.is_off_topic(

            normalized_question

        )

        conversation_turns = conversation_service.get_recent_turns(

            session_id

        )

        #
        # Phase17 : Query Rewriting
        #
        # 「今の話の続きで」のような指示語を含む質問を、
        # 会話履歴を踏まえて自己完結型に書き換える。
        #
        # 書き換え後の質問（search_query）は検索・Rerankerに
        # のみ使用し、最終回答生成のプロンプトには
        # 元の質問（question）を使う。
        #
        # 履歴が無い場合はLLM呼び出しをスキップし、
        # normalized_questionをそのまま返す
        # （query_rewrite_service内部でハンドリング済み）。
        #

        rewrite_start = time.perf_counter()

        search_query = query_rewrite_service.rewrite(

            normalized_question,

            conversation_turns

        )

        rewrite_elapsed = int(
            (
                time.perf_counter() - rewrite_start
            ) * 1000
        )

        logger.info(
            "Query Rewrite Time : %d ms",
            rewrite_elapsed
        )

        #
        # Multi Query Retrieval
        #
        # 検索クエリは書き換え後（search_query）を使用する。
        #

        retrieval_start = time.perf_counter()

        retrieval_result = multi_query_retrieval_service.search(
            question=search_query,
            limit=settings.retrieval_candidate_size,
            collection_name=collection_name,
            current_chapter=current_chapter
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

            answer = "資料から回答できませんでした。"

            search_log_service.log(

                question=question,

                normalized_question=normalized_question,

                retrieved_items=[],

                reranked_items=[],

                answer=answer,

                retrieval_elapsed_ms=retrieval_elapsed,

                rerank_elapsed_ms=0,

                llm_elapsed_ms=0,

                total_elapsed_ms=total_elapsed,

                cache_hit=retrieval_result.cache_hit

            )

            conversation_service.append(

                session_id=session_id,

                student_id=student_id,

                role="user",

                content=question

            )

            conversation_service.append(

                session_id=session_id,

                student_id=student_id,

                role="assistant",

                content=answer,

                is_off_topic=is_off_topic

            )

            return {
                "answer": answer,
                "elapsed_ms": total_elapsed,
                "retrieved_count": 0,
                "documents": []
            }

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
        # 質問文は検索と同じくsearch_query（書き換え後）を使う。
        # 検索とRerankerで異なる質問文を使うと、Rerankerが
        # 検索意図とズレたスコアを付けてしまうため一貫させる。
        #

        rerank_start = time.perf_counter()

        reranked_items = reranker_service.rerank(
            question=search_query,
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

            answer = "資料から回答できませんでした。"

            search_log_service.log(

                question=question,

                normalized_question=normalized_question,

                retrieved_items=retrieval_result.items,

                reranked_items=[],

                answer=answer,

                retrieval_elapsed_ms=retrieval_elapsed,

                rerank_elapsed_ms=rerank_elapsed,

                llm_elapsed_ms=0,

                total_elapsed_ms=total_elapsed,

                cache_hit=retrieval_result.cache_hit

            )

            conversation_service.append(

                session_id=session_id,

                student_id=student_id,

                role="user",

                content=question

            )

            conversation_service.append(

                session_id=session_id,

                student_id=student_id,

                role="assistant",

                content=answer,

                is_off_topic=is_off_topic

            )

            return {
                "answer": answer,
                "elapsed_ms": total_elapsed,
                "retrieved_count": 0,
                "documents": []
            }

        contexts = [

            item.document

            for item in reranked_items

        ]

        #
        # Prompt生成
        #
        # 最終回答生成には元の質問（question）を使う。
        # 受講生が実際に打った表現をLLMに見せることで、
        # 「今の話の続きで」といった自然な会話継続に
        # 沿った回答になるようにする
        # （検索用に書き換えたsearch_queryはここでは使わない）。
        #

        prompt = prompt_builder.build(
            question,
            contexts,
            conversation_turns=conversation_turns,
            is_off_topic=is_off_topic
        )

        if settings.log_prompt:

            logger.debug(
                "Prompt\n%s",
                prompt
            )

        llm_start = time.perf_counter()

        answer = llm_service.ask(
            prompt
        )

        llm_elapsed = int(
            (
                time.perf_counter() - llm_start
            ) * 1000
        )

        total_elapsed = int(
            (
                time.perf_counter() - overall_start
            ) * 1000
        )

        logger.info("----------------------------------------")
        logger.info("RAG Query Result")
        logger.info("----------------------------------------")

        logger.info(
            "Answer Preview : %s",
            answer[:300]
        )

        logger.info(
            "Collection : %s",
            collection_name
        )

        logger.info(
            "Current Chapter : %s",
            current_chapter or "(none)"
        )

        logger.info(
            "Is Off Topic : %s",
            is_off_topic
        )

        logger.info(
            "Search Query (rewritten) : %s",
            search_query
        )

        logger.info(
            "Conversation Turns Loaded : %d",
            len(conversation_turns)
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
            "Query Rewrite Time : %d ms",
            rewrite_elapsed
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

        #
        # Phase17 : 会話履歴保存
        #
        # 保存する質問文は元の質問（question）とする。
        # 次のターンのQuery Rewritingでも、受講生が
        # 実際に発した表現を履歴として参照させるため。
        #

        conversation_service.append(

            session_id=session_id,

            student_id=student_id,

            role="user",

            content=question

        )

        conversation_service.append(

            session_id=session_id,

            student_id=student_id,

            role="assistant",

            content=answer,

            is_off_topic=is_off_topic

        )

        return {
            "answer": answer,
            "documents": reranked_items,
            "retrieved_count": len(reranked_items),
            "elapsed_ms": total_elapsed,
            "is_off_topic": is_off_topic
        }


query_service = QueryService()