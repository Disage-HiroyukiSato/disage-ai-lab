import logging
import time

from app.config import settings

from app.models.answerability import (
    AnswerabilityResult,
    AnswerabilityStatus
)

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
        """
        Answerability Gateへ渡す候補が存在しない場合を
        弱い検索結果として扱う。

        注意：
        ここでは「回答不能」とは判定しない。

        あくまで、
        knowledge_queryによる検索結果が不足しているため、
        元質問によるFallback検索を試行するかどうかを
        判定するだけである。
        """

        return len(gate_candidates) == 0

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
        """
        Retrieval → Reranker → Answerability Gate候補生成。

        戻り値：

            retrieval_result
            reranked_items
            gate_candidates
            rerank_elapsed_ms

        rerankerの処理時間もここで計測する。
        """

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
                [],
                0
            )

        # --------------------------------------------------
        # Reranker
        # --------------------------------------------------

        rerank_start = time.perf_counter()

        reranked_items = (
            reranker_service.rerank(
                question=search_query,
                items=retrieval_result.items,
                limit=limit
            )
        )

        rerank_elapsed = int(
            (
                time.perf_counter()
                - rerank_start
            ) * 1000
        )

        # --------------------------------------------------
        # Answerability Gate候補
        # --------------------------------------------------
        #
        # Gateでは通常のlimitではなく、
        # Gate専用の候補数を使用する。
        #
        # ここではRerankerの結果を直接切り詰めず、
        # Retrieval結果全体からrelaxed rerankを行う。
        #

        gate_candidates = (
            reranker_service.rerank_relaxed(
                scored_items=retrieval_result.items,
                limit=answerability_gate_service.TOP_N
            )
        )

        return (
            retrieval_result,
            reranked_items,
            gate_candidates,
            rerank_elapsed
        )

    # ======================================================
    # Source Information
    # ======================================================
    #
    # 回答本文とは分離した、回答の根拠・参考資料。
    #
    # page_referenceはRAG metadataを正とする。
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

            sources.append(
                {
                    "document_id":
                        document_id,

                    "chunk_no":
                        chunk_no,

                    "title":
                        title,

                    "page_reference":
                        page_reference
                }
            )

        return sources

    # ======================================================
    # Source Pages
    # ======================================================
    #
    # PromptBuilderへ渡すページ情報。
    #
    # ページ番号はRAG metadata以外から生成しない。
    #
    # ======================================================

    def _build_source_pages(
        self,
        items: list
    ) -> list[str]:

        pages: list[str] = []

        for item in items:

            page_reference = (
                item.page_reference
            )

            if not page_reference:
                continue

            if page_reference in pages:
                continue

            pages.append(
                page_reference
            )

        return pages

    # ======================================================
    # Processing Metadata
    # ======================================================

    def _build_response_metadata(
        self,
        *,
        analyze_elapsed_ms: int,
        retrieval_elapsed_ms: int,
        rerank_elapsed_ms: int,
        answerability_elapsed_ms: int,
        llm_elapsed_ms: int,
        total_elapsed_ms: int,
        fallback_used: bool,
        cache_hit: bool,
        retrieved_count: int,
        gate_candidate_count: int,
        final_context_count: int
    ) -> dict:

        return {

            "query_analysis_elapsed_ms":
                analyze_elapsed_ms,

            "retrieval_elapsed_ms":
                retrieval_elapsed_ms,

            "rerank_elapsed_ms":
                rerank_elapsed_ms,

            "answerability_elapsed_ms":
                answerability_elapsed_ms,

            "llm_elapsed_ms":
                llm_elapsed_ms,

            "total_elapsed_ms":
                total_elapsed_ms,

            "cache_hit":
                cache_hit,

            "fallback_used":
                fallback_used,

            "retrieved_count":
                retrieved_count,

            "gate_candidate_count":
                gate_candidate_count,

            "final_context_count":
                final_context_count

        }

    # ======================================================
    # Empty Response
    # ======================================================

    def _build_empty_response(
        self,
        *,
        answer: str,
        metadata: dict,
        is_off_topic: bool,
        response_format: str,
        answerability_result: AnswerabilityResult | None = None
    ) -> dict:

        result = {

            "answer":
                answer,

            "sources":
                [],

            "source_pages":
                [],

            "documents":
                [],

            "metadata":
                metadata,

            "is_off_topic":
                is_off_topic,

            "response_format":
                response_format

        }

        if answerability_result is not None:

            result[
                "answerability_status"
            ] = (
                answerability_result.status.value
            )

            result[
                "answerability_reason"
            ] = (
                answerability_result.reason
            )

        return result

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

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=0,
                    retrieval_elapsed_ms=0,
                    rerank_elapsed_ms=0,
                    answerability_elapsed_ms=0,
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=False,
                    cache_hit=False,
                    retrieved_count=0,
                    gate_candidate_count=0,
                    final_context_count=0
                )
            )

            answer = (
                "質問内容を確認できませんでした。"
            )

            return self._build_empty_response(
                answer=answer,
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

        logger.info(
            "Current Chapter : %s",
            current_chapter
        )

        # ==================================================
        # Off Topic
        # ==================================================

        is_off_topic = (
            off_topic_router_service.is_off_topic(
                normalized_question
            )
        )

        logger.info(
            "Off Topic : %s",
            is_off_topic
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
            gate_candidates,
            rerank_elapsed
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

            fallback_used = True

            logger.info(
                "Retrieval Fallback : "
                "knowledge_query search was weak."
            )

            (
                fallback_result,
                fallback_reranked_items,
                fallback_gate_candidates,
                fallback_rerank_elapsed
            ) = self._search_and_rerank(
                search_query=normalized_question,
                collection_name=collection_name,
                current_chapter=current_chapter,
                limit=limit
            )

            # --------------------------------------------------
            # Fallback結果を採用
            # --------------------------------------------------

            retrieval_result = (
                fallback_result
            )

            reranked_items = (
                fallback_reranked_items
            )

            gate_candidates = (
                fallback_gate_candidates
            )

            rerank_elapsed += (
                fallback_rerank_elapsed
            )

        retrieval_elapsed = int(
            (
                time.perf_counter()
                - retrieval_start
            ) * 1000
        )

        logger.info(
            "Retrieval Time : %d ms",
            retrieval_elapsed
        )

        logger.info(
            "Rerank Time : %d ms",
            rerank_elapsed
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

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=analyze_elapsed,
                    retrieval_elapsed_ms=retrieval_elapsed,
                    rerank_elapsed_ms=rerank_elapsed,
                    answerability_elapsed_ms=0,
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=fallback_used,
                    cache_hit=(
                        retrieval_result.cache_hit
                    ),
                    retrieved_count=(
                        retrieval_result.total
                    ),
                    gate_candidate_count=0,
                    final_context_count=0
                )
            )

            answer = (
                "資料から回答できませんでした。"
            )

            return self._build_empty_response(
                answer=answer,
                metadata=metadata,
                is_off_topic=is_off_topic,
                response_format=response_format
            )

        # ==================================================
        # Answerability Gate
        # ==================================================
        #
        # boolではなく、
        #
        # FULL / PARTIAL / NONE
        #
        # の結果を保持する。
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

        answerability_result = (
            answerability_gate_service.assess(
                question=gate_query,
                items=gate_candidates
            )
        )

        answerability_elapsed = int(
            (
                time.perf_counter()
                - gate_start
            ) * 1000
        )

        logger.info(
            "Answerability Status : %s",
            answerability_result.status.value
        )

        logger.info(
            "Answerability Reason : %s",
            answerability_result.reason
        )

        # ==================================================
        # NONE
        # ==================================================
        #
        # 本当にRAGに関連情報がない場合だけ、
        # 資料を根拠とした回答を終了する。
        #
        # FULL / PARTIALの場合はLLMへ進む。
        #
        # ==================================================

        if (
            answerability_result.status
            == AnswerabilityStatus.NONE
        ):

            total_elapsed = int(
                (
                    time.perf_counter()
                    - overall_start
                ) * 1000
            )

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=analyze_elapsed,
                    retrieval_elapsed_ms=retrieval_elapsed,
                    rerank_elapsed_ms=rerank_elapsed,
                    answerability_elapsed_ms=(
                        answerability_elapsed
                    ),
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=fallback_used,
                    cache_hit=(
                        retrieval_result.cache_hit
                    ),
                    retrieved_count=(
                        retrieval_result.total
                    ),
                    gate_candidate_count=len(
                        gate_candidates
                    ),
                    final_context_count=0
                )
            )

            answer = (
                "資料からは確認できません。"
            )

            return self._build_empty_response(
                answer=answer,
                metadata=metadata,
                is_off_topic=is_off_topic,
                response_format=response_format,
                answerability_result=(
                    answerability_result
                )
            )
        # ==================================================
        # Answerability Gate
        # ==================================================
        #
        # boolではなく、FULL/PARTIAL/NONEの結果を保持する。
        #
        # FULL / PARTIALの場合はLLMへ進む。
        # NONEの場合のみ、資料を根拠とした回答を終了する。
        #

        gate_query = (
            normalized_question
            if fallback_used
            else knowledge_query
        )

        gate_start = (
            time.perf_counter()
        )

        answerability_result = (
            answerability_gate_service.assess(
                question=gate_query,
                items=gate_candidates
            )
        )

        answerability_elapsed = int(
            (
                time.perf_counter()
                - gate_start
            ) * 1000
        )

        logger.info(
            "Answerability Status : %s",
            answerability_result.status.value
        )

        logger.info(
            "Answerability Reason : %s",
            answerability_result.reason
        )

        # ==================================================
        # Answerability NONE
        # ==================================================
        #
        # 本当にRAGに関連情報がない場合だけ、
        # 資料を根拠とした回答を終了する。
        #
        # FULL / PARTIALの場合はLLMへ進む。
        #

        if (
            answerability_result.status
            == AnswerabilityStatus.NONE
        ):

            total_elapsed = int(
                (
                    time.perf_counter()
                    - overall_start
                ) * 1000
            )

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=analyze_elapsed,
                    retrieval_elapsed_ms=retrieval_elapsed,
                    answerability_elapsed_ms=(
                        answerability_elapsed
                    ),
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=fallback_used,
                    cache_hit=(
                        retrieval_result.cache_hit
                    ),
                    retrieved_count=(
                        retrieval_result.total
                    ),
                    gate_candidate_count=len(
                        gate_candidates
                    ),
                    final_context_count=0
                )
            )

            answer = (
                "資料からは確認できません。"
            )

            return self._build_empty_response(
                answer=answer,
                metadata=metadata,
                is_off_topic=is_off_topic,
                response_format=response_format,
                answerability_result=(
                    answerability_result
                )
            )

        # ==================================================
        # Answer Context
        # ==================================================
        #
        # Answerability Gate用候補と、
        # 実際の回答生成用候補を統合する。
        #
        # reranked_items:
        #   通常のRerankerによる回答関連度順の候補。
        #
        # gate_candidates:
        #   Answerability Gateが関連情報を判定するための
        #   緩和候補。
        #
        # Gate用候補にしか存在しない関連情報も
        # 回答生成へ利用できるようにする。
        #

        answer_context_candidates = (
            reranked_items
            + gate_candidates
        )

        final_context_items = (
            context_dedup_service.deduplicate(
                answer_context_candidates
            )
        )

        # ==================================================
        # Defensive Check
        # ==================================================
        #
        # Answerability Gateを通過しているにもかかわらず、
        # Context統合後に利用可能なContextがなくなった場合。
        #

        if not final_context_items:

            total_elapsed = int(
                (
                    time.perf_counter()
                    - overall_start
                ) * 1000
            )

            metadata = (
                self._build_response_metadata(
                    analyze_elapsed_ms=analyze_elapsed,
                    retrieval_elapsed_ms=retrieval_elapsed,
                    answerability_elapsed_ms=(
                        answerability_elapsed
                    ),
                    llm_elapsed_ms=0,
                    total_elapsed_ms=total_elapsed,
                    fallback_used=fallback_used,
                    cache_hit=(
                        retrieval_result.cache_hit
                    ),
                    retrieved_count=(
                        retrieval_result.total
                    ),
                    gate_candidate_count=len(
                        gate_candidates
                    ),
                    final_context_count=0
                )
            )

            answer = (
                "回答に利用できる資料を"
                "整理できませんでした。"
            )

            return self._build_empty_response(
                answer=answer,
                metadata=metadata,
                is_off_topic=is_off_topic,
                response_format=response_format,
                answerability_result=(
                    answerability_result
                )
            )

        # ==================================================
        # Context
        # ==================================================

        contexts = [

            item.document

            for item in final_context_items

        ]

        # ==================================================
        # Sources
        # ==================================================
        #
        # 回答本文とは分離した、
        # 回答の根拠となる資料情報。
        #

        sources = (
            self._build_sources(
                final_context_items
            )
        )

        # ==================================================
        # Source Pages
        # ==================================================

        source_pages = (
            self._build_source_pages(
                final_context_items
            )
        )

        logger.info(
            "Source Pages : %s",
            source_pages
        )

        # ==================================================
        # Prompt
        # ==================================================
        #
        # QueryRewriteServiceで判定した
        # response_formatをPromptBuilderへ渡す。
        #
        # Answerability Gateの結果も渡す。
        #
        # ページ情報はRAG metadataから取得したものだけを渡す。
        #

        prompt = (
            prompt_builder.build(

                question=question,

                contexts=contexts,

                conversation_questions=(
                    conversation_questions
                ),

                is_off_topic=is_off_topic,

                response_format=response_format,

                answerability_status=(
                    answerability_result.status.value
                ),

                answerability_reason=(
                    answerability_result.reason
                ),

                source_pages=source_pages

            )
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
        # Response Metadata
        # ==================================================

        metadata = (
            self._build_response_metadata(

                analyze_elapsed_ms=(
                    analyze_elapsed
                ),

                retrieval_elapsed_ms=(
                    retrieval_elapsed
                ),

                answerability_elapsed_ms=(
                    answerability_elapsed
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

                gate_candidate_count=(
                    len(gate_candidates)
                ),

                final_context_count=(
                    len(final_context_items)
                )

            )
        )

        # ==================================================
        # Search Log
        # ==================================================
        #
        # reranked_itemsには、
        # Gate候補ではなく通常のReranker結果を記録する。
        #
        # 検索ログ上の「Reranker結果」と、
        # 実際にLLMへ渡したContextは別物として扱う。
        #

        search_log_service.log(

            question=question,

            normalized_question=(
                normalized_question
            ),

            retrieved_items=(
                retrieval_result.items
            ),

            reranked_items=(
                reranked_items
            ),

            answer=answer,

            retrieval_elapsed_ms=(
                retrieval_elapsed
            ),

            # 現在のQueryServiceでは
            # Reranker単独の処理時間を計測していない。
            #
            # 必要になった場合は
            # _search_and_rerank()内で計測する。
            #
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
        #
        # LLMによる回答生成が正常に完了した場合のみ、
        # 今回の質問・回答を会話履歴へ追加する。
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

        # ==================================================
        # Final Response
        # ==================================================

        return {

            "answer":
                answer,

            "sources":
                sources,

            "source_pages":
                source_pages,

            "documents":
                final_context_items,

            "answerability_status":
                answerability_result.status.value,

            "answerability_reason":
                answerability_result.reason,

            "metadata":
                metadata,

            "is_off_topic":
                is_off_topic,

            "response_format":
                response_format

        }


query_service = QueryService()