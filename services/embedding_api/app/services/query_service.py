import logging
import time

from app.config import settings

from app.services.answerability_gate_service import (
    answerability_gate_service
)

from app.services.collection_router_service import (
    collection_router_service
)

from app.services.context_dedup_service import (
    context_dedup_service
)

from app.services.conversation_service import (
    conversation_service
)

from app.services.llm_service import (
    llm_service
)

from app.services.multi_query_retrieval_service import (
    multi_query_retrieval_service
)

from app.services.off_topic_router_service import (
    off_topic_router_service
)

from app.services.progress_service import (
    progress_service
)

from app.services.prompt_builder import (
    prompt_builder
)

from app.services.query_normalizer import (
    query_normalizer
)

from app.services.query_rewrite_service import (
    query_rewrite_service
)

from app.services.reranker_service import (
    reranker_service
)

from app.services.search_log_service import (
    search_log_service
)


logger = logging.getLogger(__name__)


class QueryService:

    # ======================================================
    # Retrieval Fallback
    # ======================================================

    def _is_weak(
        self,
        gate_candidates: list
    ) -> bool:

        return len(
            gate_candidates
        ) == 0

    # ======================================================
    # Search + Rerank
    # ======================================================

    def _search_and_rerank(
        self,
        search_query: str,
        collection_name: str,
        current_chapter: str,
        limit: int
    ):

        retrieval_result = (
            multi_query_retrieval_service.search(
                question=search_query,
                limit=settings.retrieval_candidate_size,
                collection_name=collection_name,
                current_chapter=current_chapter
            )
        )

        if retrieval_result.total == 0:

            return (
                retrieval_result,
                [],
                []
            )

        reranked_items = (
            reranker_service.rerank(
                question=search_query,
                items=retrieval_result.items,
                limit=limit
            )
        )

        gate_candidates = (
            reranker_service.rerank_relaxed(
                scored_items=retrieval_result.items,
                limit=answerability_gate_service.TOP_N
            )
        )

        return (
            retrieval_result,
            reranked_items,
            gate_candidates
        )

    # ======================================================
    # Source Information
    # ======================================================
    #
    # 回答本文と資料情報を分離する。
    #
    # sourcesには「回答の根拠・参考情報」を格納する。
    #
    # ======================================================

    def _build_sources(
        self,
        items: list
    ) -> list[dict]:

        sources: list[dict] = []

        seen: set[tuple] = set()

        for item in items:

            metadata = (
                item.metadata
                or {}
            )

            document_id = str(
                metadata.get(
                    "document_id",
                    ""
                )
            )

            chunk_no = metadata.get(
                "chunk_no"
            )

            title = str(
                metadata.get(
                    "title",
                    ""
                )
            )

            page_reference = (
                item.page_reference
            )

            key = (
                document_id,
                chunk_no,
                page_reference
            )

            if key in seen:

                continue

            seen.add(
                key
            )

            source = {
                "document_id":
                    document_id,

                "title":
                    title,

                "chunk_no":
                    chunk_no,

                "page_reference":
                    page_reference
            }

            # ----------------------------------------------
            # 空の値は除外
            # ----------------------------------------------

            source = {
                key: value
                for key, value in source.items()
                if value not in (
                    None,
                    ""
                )
            }

            sources.append(
                source
            )

        return sources

    # ======================================================
    # Processing Metadata
    # ======================================================
    #
    # 検索時間など、回答本文とは関係ない情報。
    #
    # ======================================================

    def _build_response_metadata(
        self,
        *,
        analyze_elapsed_ms: int,
        retrieval_elapsed_ms: int,
        gate_elapsed_ms: int,
        llm_elapsed_ms: int,
        total_elapsed_ms: int,
        fallback_used: bool,
        cache_hit: bool,
        retrieved_count: int,
        reranked_count: int,
        gate_candidate_count: int,
        final_context_count: int
    ) -> dict:

        return {

            "query_analysis_time_ms":
                analyze_elapsed_ms,

            "retrieval_time_ms":
                retrieval_elapsed_ms,

            "answerability_gate_time_ms":
                gate_elapsed_ms,

            "llm_time_ms":
                llm_elapsed_ms,

            "total_time_ms":
                total_elapsed_ms,

            "fallback_used":
                fallback_used,

            "cache_hit":
                cache_hit,

            "retrieved_count":
                retrieved_count,

            "reranked_count":
                reranked_count,

            "gate_candidate_count":
                gate_candidate_count,

            "final_context_count":
                final_context_count

        }

    # ======================================================
    # Empty / Rejected Response
    # ======================================================

    def _build_empty_response(
        self,
        *,
        answer: str,
        total_elapsed_ms: int,
        metadata: dict,
        is_off_topic: bool,
        response_format: str
    ) -> dict:

        return {

            "answer":
                answer,

            "sources":
                [],

            "metadata":
                metadata,

            "is_off_topic":
                is_off_topic,

            "response_format":
                response_format

        }

    # ======================================================
    # Main Query
    # ======================================================

    def ask(
        self,
        question: str,
        limit: int = 5,
        student_id: str | None = None,
        session_id: str | None = None
    ):

        overall_start = (
            time.perf_counter()
        )

        logger.info("")
        logger.info(
            "========================================"
        )
        logger.info(
            "RAG Query Start"
        )
        logger.info(
            "========================================"
        )

        logger.info(
            "Question : %s",
            question
        )

        logger.info(
            "student_id=%s session_id=%s",
            student_id,
            session_id
        )

        # ==================================================
        # Query Normalize
        # ==================================================

        normalized_question = (
            query_normalizer.normalize(
                question
            )
        )

        logger.info(
            "Normalized : %s",
            normalized_question
        )

        # ==================================================
        # Empty Question
        # ==================================================

        if not normalized_question:

            total_elapsed = int(
                (
                    time.perf_counter()
                    - overall_start
                ) * 1000
            )

            answer = (
                "質問内容を確認できませんでした。"
            )

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=0,
                    retrieval_elapsed_ms=0,
                    gate_elapsed_ms=0,
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=False,
                    cache_hit=False,
                    retrieved_count=0,
                    reranked_count=0,
                    gate_candidate_count=0,
                    final_context_count=0
                )
            )

            search_log_service.log(
                question=question,
                normalized_question=normalized_question,
                retrieved_items=[],
                reranked_items=[],
                answer=answer,
                retrieval_elapsed_ms=0,
                rerank_elapsed_ms=0,
                llm_elapsed_ms=0,
                total_elapsed_ms=total_elapsed,
                cache_hit=False
            )

            return self._build_empty_response(
                answer=answer,
                total_elapsed_ms=total_elapsed,
                metadata=metadata,
                is_off_topic=False,
                response_format="EXPLAIN"
            )

        # ==================================================
        # Collection
        # ==================================================

        collection_name = (
            collection_router_service.route(
                normalized_question
            )
        )

        logger.info(
            "Collection Router : %s",
            collection_name
        )

        # ==================================================
        # Progress
        # ==================================================

        current_chapter = (
            progress_service.get_current_chapter(
                student_id
            )
        )

        # ==================================================
        # Off Topic
        # ==================================================

        is_off_topic = (
            off_topic_router_service.is_off_topic(
                normalized_question
            )
        )

        # ==================================================
        # Conversation
        # ==================================================

        conversation_turns = (
            conversation_service.get_recent_turns(
                session_id
            )
        )

        conversation_questions = (
            conversation_service.get_recent_questions(
                session_id
            )
        )

        logger.info(
            "Conversation Turns Loaded : %d",
            len(conversation_turns)
        )

        logger.info(
            "Conversation Questions Loaded : %d",
            len(conversation_questions)
        )

        # ==================================================
        # Query Analysis
        # ==================================================

        analyze_start = (
            time.perf_counter()
        )

        (
            knowledge_query,
            response_format
        ) = query_rewrite_service.analyze(
            normalized_question,
            conversation_turns
        )

        analyze_elapsed = int(
            (
                time.perf_counter()
                - analyze_start
            ) * 1000
        )

        logger.info(
            "Query Analysis Time : %d ms",
            analyze_elapsed
        )

        logger.info(
            "Knowledge Query : %s",
            knowledge_query
        )

        logger.info(
            "Response Format : %s",
            response_format
        )

        # ==================================================
        # Retrieval
        # ==================================================

        retrieval_start = (
            time.perf_counter()
        )

        (
            retrieval_result,
            reranked_items,
            gate_candidates
        ) = self._search_and_rerank(
            search_query=knowledge_query,
            collection_name=collection_name,
            current_chapter=current_chapter,
            limit=limit
        )

        fallback_used = False

        # ==================================================
        # Retrieval Fallback
        # ==================================================

        if self._is_weak(
            gate_candidates
        ):

            logger.info(
                "Retrieval Fallback : "
                "knowledge_query search was weak."
            )

            fallback_used = True

            (
                retrieval_result,
                reranked_items,
                gate_candidates
            ) = self._search_and_rerank(
                search_query=normalized_question,
                collection_name=collection_name,
                current_chapter=current_chapter,
                limit=limit
            )

        retrieval_elapsed = int(
            (
                time.perf_counter()
                - retrieval_start
            ) * 1000
        )

        logger.info(
            "Retrieval + Rerank Time : %d ms",
            retrieval_elapsed
        )

        logger.info(
            "Fallback Used : %s",
            fallback_used
        )

        logger.info(
            "Retrieved : %d",
            retrieval_result.total
        )

        logger.info(
            "Reranked : %d",
            len(reranked_items)
        )

        # ==================================================
        # No Retrieval Result
        # ==================================================

        if not gate_candidates:

            total_elapsed = int(
                (
                    time.perf_counter()
                    - overall_start
                ) * 1000
            )

            answer = (
                "資料から回答できませんでした。"
            )

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=analyze_elapsed,
                    retrieval_elapsed_ms=retrieval_elapsed,
                    gate_elapsed_ms=0,
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=fallback_used,
                    cache_hit=(
                        retrieval_result.cache_hit
                    ),
                    retrieved_count=(
                        retrieval_result.total
                    ),
                    reranked_count=len(
                        reranked_items
                    ),
                    gate_candidate_count=0,
                    final_context_count=0
                )
            )

            search_log_service.log(
                question=question,
                normalized_question=normalized_question,
                retrieved_items=(
                    retrieval_result.items
                ),
                reranked_items=[],
                answer=answer,
                retrieval_elapsed_ms=(
                    retrieval_elapsed
                ),
                rerank_elapsed_ms=0,
                llm_elapsed_ms=0,
                total_elapsed_ms=(
                    total_elapsed
                ),
                cache_hit=(
                    retrieval_result.cache_hit
                )
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

            return self._build_empty_response(
                answer=answer,
                total_elapsed_ms=total_elapsed,
                metadata=metadata,
                is_off_topic=is_off_topic,
                response_format=response_format
            )

        # ==================================================
        # Answerability Gate
        # ==================================================
        #
        # ここでは「資料が質問に完全回答できるか」ではなく、
        # 「回答を構成するために意味のある関連資料か」を
        # 最終確認する。
        #
        # 例えば、
        #
        #   Q:
        #   よく使用するもの上位3つに
        #   サンプルコードを出してください。
        #
        #   RAG:
        #   boolean / byte / short / int / ...
        #
        # の場合、
        #
        # 「上位3つ」という順位は資料から確認できない。
        #
        # しかし基本データ型という関連情報は存在するため、
        # LLMへ渡して、
        #
        # 「順位は資料から確認できないが、
        #  資料にある基本データ型についてコード例を示す」
        #
        # という回答を可能にする。
        #
        # ==================================================

        gate_query = (
            normalized_question
            if fallback_used
            else knowledge_query
        )

        gate_start = (
            time.perf_counter()
        )

        is_answerable = (
            answerability_gate_service.is_answerable(
                gate_query,
                gate_candidates
            )
        )

        gate_elapsed = int(
            (
                time.perf_counter()
                - gate_start
            ) * 1000
        )

        logger.info(
            "Answerability Gate Time : %d ms",
            gate_elapsed
        )

        logger.info(
            "Answerability Gate Result : %s",
            is_answerable
        )

        # ==================================================
        # Gate rejection
        # ==================================================
        #
        # GateがNoでも、RAG検索結果そのものが存在する場合は
        # 直ちに回答を終了しない。
        #
        # 「資料には関連情報があるが、質問への直接回答は
        # できない」という状態をLLMに判断させる。
        #
        # ==================================================

        if not is_answerable:

            logger.info(
                "Answerability Gate rejected "
                "direct-answer judgement, "
                "but retrieved context exists. "
                "Continuing with contextual answer generation."
            )

        # ==================================================
        # Context Dedup
        # ==================================================

        final_context_items = (
            context_dedup_service.deduplicate(
                gate_candidates
            )
        )

        logger.info(
            "Gate Candidates Count : %d",
            len(gate_candidates)
        )

        logger.info(
            "Final Context Count : %d",
            len(final_context_items)
        )

        # ==================================================
        # Defensive fallback
        # ==================================================

        if not final_context_items:

            total_elapsed = int(
                (
                    time.perf_counter()
                    - overall_start
                ) * 1000
            )

            answer = (
                "資料からは確認できません。"
            )

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=analyze_elapsed,
                    retrieval_elapsed_ms=retrieval_elapsed,
                    gate_elapsed_ms=gate_elapsed,
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=fallback_used,
                    cache_hit=(
                        retrieval_result.cache_hit
                    ),
                    retrieved_count=(
                        retrieval_result.total
                    ),
                    reranked_count=len(
                        reranked_items
                    ),
                    gate_candidate_count=len(
                        gate_candidates
                    ),
                    final_context_count=0
                )
            )

            search_log_service.log(
                question=question,
                normalized_question=normalized_question,
                retrieved_items=(
                    retrieval_result.items
                ),
                reranked_items=(
                    gate_candidates
                ),
                answer=answer,
                retrieval_elapsed_ms=(
                    retrieval_elapsed
                ),
                rerank_elapsed_ms=0,
                llm_elapsed_ms=0,
                total_elapsed_ms=(
                    total_elapsed
                ),
                cache_hit=(
                    retrieval_result.cache_hit
                )
            )

            return self._build_empty_response(
                answer=answer,
                total_elapsed_ms=total_elapsed,
                metadata=metadata,
                is_off_topic=is_off_topic,
                response_format=response_format
            )

        # ==================================================
        # Context
        # ==================================================

        contexts = [
            item.document
            for item in final_context_items
        ]

        # ==================================================
        # Source Information
        # ==================================================
        #
        # 回答生成前にsourcesを確定する。
        #
        # LLM回答本文にはページ情報を強制的に混ぜない。
        #
        # ==================================================

        sources = (
            self._build_sources(
                final_context_items
            )
        )

        logger.info(
            "Source Count : %d",
            len(sources)
        )

        for index, source in enumerate(
            sources,
            start=1
        ):

            logger.info(
                "[Source %d] document_id=%s "
                "title=%s page=%s",
                index,
                source.get(
                    "document_id",
                    ""
                ),
                source.get(
                    "title",
                    ""
                ),
                source.get(
                    "page_reference",
                    "(none)"
                )
            )

        # ==================================================
        # Prompt
        # ==================================================

        prompt = (
            prompt_builder.build(
                question,
                contexts,
                conversation_questions=(
                    conversation_questions
                ),
                is_off_topic=is_off_topic,
                response_format=response_format
            )
        )

        if settings.log_prompt:

            logger.debug(
                "Prompt\n%s",
                prompt
            )

        # ==================================================
        # LLM
        # ==================================================

        llm_start = (
            time.perf_counter()
        )

        answer = (
            llm_service.ask(
                prompt
            )
        )

        llm_elapsed = int(
            (
                time.perf_counter()
                - llm_start
            ) * 1000
        )

        total_elapsed = int(
            (
                time.perf_counter()
                - overall_start
            ) * 1000
        )

        # ==================================================
        # Logs
        # ==================================================

        logger.info(
            "----------------------------------------"
        )

        logger.info(
            "RAG Query Result"
        )

        logger.info(
            "----------------------------------------"
        )

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
            "Knowledge Query : %s",
            knowledge_query
        )

        logger.info(
            "Response Format : %s",
            response_format
        )

        logger.info(
            "Fallback Used : %s",
            fallback_used
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
            "Gate Candidates Count : %d",
            len(gate_candidates)
        )

        logger.info(
            "Final Context Count : %d",
            len(final_context_items)
        )

        logger.info(
            "Answerability Gate : %s (%d ms)",
            is_answerable,
            gate_elapsed
        )

        logger.info(
            "Query Analysis Time : %d ms",
            analyze_elapsed
        )

        logger.info(
            "Retrieval Time : %d ms",
            retrieval_elapsed
        )

        logger.info(
            "LLM Time : %d ms",
            llm_elapsed
        )

        logger.info(
            "Total Time : %d ms",
            total_elapsed
        )

        # ==================================================
        # Search Log
        # ==================================================

        search_log_service.log(
            question=question,
            normalized_question=normalized_question,
            retrieved_items=(
                retrieval_result.items
            ),
            reranked_items=(
                gate_candidates
            ),
            answer=answer,
            retrieval_elapsed_ms=(
                retrieval_elapsed
            ),
            rerank_elapsed_ms=0,
            llm_elapsed_ms=(
                llm_elapsed
            ),
            total_elapsed_ms=(
                total_elapsed
            ),
            cache_hit=(
                retrieval_result.cache_hit
            )
        )

        # ==================================================
        # Conversation History
        # ==================================================

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

        # ==================================================
        # Response Metadata
        # ==================================================

        response_metadata = (
            self._build_response_metadata(
                analyze_elapsed_ms=(
                    analyze_elapsed
                ),
                retrieval_elapsed_ms=(
                    retrieval_elapsed
                ),
                gate_elapsed_ms=(
                    gate_elapsed
                ),
                llm_elapsed_ms=(
                    llm_elapsed
                ),
                total_elapsed_ms=(
                    total_elapsed
                ),
                fallback_used=(
                    fallback_used
                ),
                cache_hit=(
                    retrieval_result.cache_hit
                ),
                retrieved_count=(
                    retrieval_result.total
                ),
                reranked_count=(
                    len(reranked_items)
                ),
                gate_candidate_count=(
                    len(gate_candidates)
                ),
                final_context_count=(
                    len(final_context_items)
                )
            )
        )

        # ==================================================
        # Final Response
        # ==================================================
        #
        # answer
        #   → 回答本文
        #
        # sources
        #   → 根拠・参考資料・ページ
        #
        # metadata
        #   → 処理時間・検索件数等
        #
        # ==================================================

        return {

            "answer":
                answer,

            "sources":
                sources,

            "metadata":
                response_metadata,

            "is_off_topic":
                is_off_topic,

            "response_format":
                response_format

        }


query_service = QueryService()