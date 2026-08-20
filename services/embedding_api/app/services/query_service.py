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

    #
    # ------------------------------------------------------
    # Retrieval Fallback : 検索結果が弱いかどうかの判定
    # ------------------------------------------------------
    #
    # 「弱い」の基準は、既存のReranker足切り判定
    # （min_rerank_score）をそのまま流用する。
    # Reranker通過後の件数が0件であれば「弱い」とみなす。
    #

    def _is_weak(
        self,
        gate_candidates: list
    ) -> bool:

        return len(gate_candidates) == 0

    #
    # ------------------------------------------------------
    # 検索 + Reranker を1セットにしたヘルパー
    # ------------------------------------------------------
    #

    def _search_and_rerank(
        self,
        search_query: str,
        collection_name: str,
        current_chapter: str,
        limit: int
    ):

        retrieval_result = multi_query_retrieval_service.search(
            question=search_query,
            limit=settings.retrieval_candidate_size,
            collection_name=collection_name,
            current_chapter=current_chapter
        )

        if retrieval_result.total == 0:

            return retrieval_result, [], []

        reranked_items = reranker_service.rerank(
            question=search_query,
            items=retrieval_result.items,
            limit=limit
        )

        #
        # Answerability Gate向けの緩和候補
        # ------------------------------------------------------
        #
        # min_rerank_scoreで足切りされる前の
        # retrieval_result.items（既にitem.scoreが
        # rerank()実行時に設定済み）からスコア上位3件を取得する。
        #
        # reranked_itemsが0件（min_rerank_score未満のみ）の
        # 場合でも、Gateはこの緩和候補を使って
        # 「実は答えられる資料が上位に埋もれていないか」を
        # 確認できる。
        #

        gate_candidates = reranker_service.rerank_relaxed(
            scored_items=retrieval_result.items,
            limit=answerability_gate_service.TOP_N
        )

        return (
            retrieval_result,
            reranked_items,
            gate_candidates
        )

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

            logger.info(
                "========================================"
            )
            logger.info(
                "RAG Query End"
            )
            logger.info(
                "========================================"
            )

            answer = "質問内容を確認できませんでした。"

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

            return {
                "answer": answer,
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

        is_off_topic = off_topic_router_service.is_off_topic(
            normalized_question
        )

        #
        # ------------------------------------------------------
        # 会話履歴
        # ------------------------------------------------------
        #
        # Query Rewriteでは、assistant回答を含む従来の会話履歴を
        # 使用する。
        #
        # 例えば、
        #
        #   Q: 継承とは何ですか？
        #   A: 継承とは...
        #   Q: それをフローチャートで表してください。
        #
        # のような会話では、Query Rewriteが「それ」が
        # 「継承」を指していることを判断するために、
        # 過去のassistant回答も含めた文脈が有効。
        #

        conversation_turns = conversation_service.get_recent_turns(
            session_id
        )

        #
        # 最終回答生成用には、assistant回答を除外する。
        #
        # ここが今回の修正の重要ポイント。
        #
        # 過去のassistant回答本文をLLMへ再投入すると、
        # 小型LLMがその回答を「今回の回答候補」として
        # そのまま模倣する可能性がある。
        #
        # そのため、最終Promptには受講生の質問だけを
        # 会話文脈として渡す。
        #

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

        #
        # ------------------------------------------------------
        # Knowledge Query分離 + 回答形式判定
        # ------------------------------------------------------
        #
        # 質問から「検索に使う知識部分（knowledge_query）」と
        # 「求められている出力形式（response_format）」を
        # 1回のLLM呼び出しで分離する。
        #
        # 会話履歴がある場合は、同じ呼び出しの中で
        # 自己完結化（指示語の解決）も行われる。
        #

        analyze_start = time.perf_counter()

        knowledge_query, response_format = (
            query_rewrite_service.analyze(
                normalized_question,
                conversation_turns
            )
        )

        analyze_elapsed = int(
            (
                time.perf_counter() - analyze_start
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

        #
        # ------------------------------------------------------
        # Retrieval Fallback（二段階検索）
        # ------------------------------------------------------
        #
        # 1段階目 : knowledge_query（表現形式を除いた検索専用の
        #           質問）で検索・Rerankerを実行する。
        #
        # 1段階目が弱い（Reranker通過0件）場合、
        #
        # 2段階目 : 正規化後の元の質問（normalized_question）で
        #           再検索する。
        #
        # knowledge_queryの抽出が不適切だった場合の保険として
        # 機能する。
        #

        retrieval_start = time.perf_counter()

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

        if self._is_weak(
            gate_candidates
        ):

            logger.info(
                "Retrieval Fallback : knowledge_query search was "
                "weak. Retrying with normalized_question."
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
                time.perf_counter() - retrieval_start
            ) * 1000
        )

        logger.info(
            "Retrieval + Rerank Time (fallback included) : %d ms",
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

        #
        # ------------------------------------------------------
        # 二段階検索を経ても弱い場合
        # ------------------------------------------------------

        if self._is_weak(
            gate_candidates
        ):

            total_elapsed = int(
                (
                    time.perf_counter() - overall_start
                ) * 1000
            )

            logger.info(
                "Both retrieval attempts were weak. "
                "Rejecting as out-of-scope."
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
        #
        # ------------------------------------------------------
        # Answerability Gate
        # ------------------------------------------------------
        #
        # Reranker通過後の資料であっても、単語の一致だけで
        # スコアを超えてしまうケースがある。
        #
        # LLMへ渡す直前の最終防衛ラインとして、軽量LLMで
        # 「この資料は実際に質問へ答えているか」を判定する。
        #
        # 判定に使う質問は、検索・Rerankerと同じ質問文
        # （knowledge_query、Fallback使用時はnormalized_question）
        # に揃える。
        #

        gate_query = (
            normalized_question
            if fallback_used
            else knowledge_query
        )

        gate_start = time.perf_counter()

        is_answerable = answerability_gate_service.is_answerable(
            gate_query,
            gate_candidates
        )

        gate_elapsed = int(
            (
                time.perf_counter() - gate_start
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

        if not is_answerable:

            total_elapsed = int(
                (
                    time.perf_counter() - overall_start
                ) * 1000
            )

            logger.info(
                "Answerability Gate rejected the candidates."
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

            answer = "資料からは確認できません。"

            search_log_service.log(
                question=question,
                normalized_question=normalized_question,
                retrieved_items=retrieval_result.items,
                reranked_items=gate_candidates,
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

        #
        # ------------------------------------------------------
        # Context重複除去
        # ------------------------------------------------------
        #
        # Answerability Gateが「回答可能」と判定した候補を、
        # LLMへ渡す直前に整理する。
        #
        # ここでは検索アルゴリズムそのものを変更しない。
        #
        # Gate Candidates
        #       ↓
        # Context Dedup
        #       ↓
        # Final Context
        #
        # 完全一致のContextだけを除去する。
        # 類似度による除去は現段階では行わない。
        #

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

        #
        # Contextが重複除去によって0件になった場合。
        #
        # 通常は発生しないが、防御的に処理する。
        #

        if not final_context_items:

            total_elapsed = int(
                (
                    time.perf_counter() - overall_start
                ) * 1000
            )

            logger.warning(
                "No usable context remained after deduplication."
            )

            answer = "資料からは確認できません。"

            search_log_service.log(
                question=question,
                normalized_question=normalized_question,
                retrieved_items=retrieval_result.items,
                reranked_items=gate_candidates,
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

        #
        # ------------------------------------------------------
        # Context生成
        # ------------------------------------------------------
        #
        # LLMへ実際に渡すのは、
        #
        #   final_context_items
        #
        # だけ。
        #
        # Gate CandidatesそのものをPromptへ渡さない。
        #

        contexts = [
            item.document
            for item in final_context_items
        ]

        #
        # ------------------------------------------------------
        # デバッグログ
        # ------------------------------------------------------
        #
        # Gate通過後の候補数と、最終的にLLMへ渡すContext数を
        # 明確に分離して記録する。
        #

        logger.info(
            "----------------------------------------"
        )

        logger.info(
            "Final Contexts for LLM"
        )

        logger.info(
            "----------------------------------------"
        )

        for index, item in enumerate(
            final_context_items,
            start=1
        ):

            metadata = item.metadata or {}

            logger.info(
                "[Context %d] document_id=%s chunk_no=%s",
                index,
                metadata.get(
                    "document_id",
                    ""
                ),
                metadata.get(
                    "chunk_no",
                    ""
                )
            )

        logger.info(
            "----------------------------------------"
        )

        #
        # ------------------------------------------------------
        # Prompt生成
        # ------------------------------------------------------
        #
        # ここが今回の会話履歴対策の中心。
        #
        # Query Rewriteにはconversation_turnsを使うが、
        # 最終回答生成にはconversation_questionsを使用する。
        #
        # したがって、過去のassistant回答本文は
        # 最終Promptへ渡されない。
        #

        prompt = prompt_builder.build(
            question,
            contexts,
            conversation_questions=conversation_questions,
            is_off_topic=is_off_topic,
            response_format=response_format
        )

        if settings.log_prompt:

            logger.debug(
                "Prompt\n%s",
                prompt
            )

        #
        # ------------------------------------------------------
        # LLM
        # ------------------------------------------------------

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

        #
        # ------------------------------------------------------
        # 結果ログ
        # ------------------------------------------------------

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
            "Conversation Turns Loaded : %d",
            len(conversation_turns)
        )

        logger.info(
            "Conversation Questions Loaded : %d",
            len(conversation_questions)
        )

        logger.info(
            "Retrieved Count : %d",
            retrieval_result.total
        )

        logger.info(
            "Reranked Count (strict) : %d",
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
            "Retrieval Time (fallback included) : %d ms",
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

        logger.info(
            "========================================"
        )

        logger.info(
            "RAG Query End"
        )

        logger.info(
            "========================================"
        )

        logger.info(
            ""
        )

        #
        # ------------------------------------------------------
        # 検索ログ保存
        # ------------------------------------------------------
        #
        # search_logには、従来どおりGate Candidatesを保存する。
        #
        # 理由：
        # 検索品質の分析では、Gateが何を候補として判定したかを
        # 残しておいた方がよい。
        #
        # ContextDedupはLLM投入直前のPrompt最適化なので、
        # 検索ログの意味を変更しない。
        #

        search_log_service.log(
            question=question,
            normalized_question=normalized_question,
            retrieved_items=retrieval_result.items,
            reranked_items=gate_candidates,
            answer=answer,
            retrieval_elapsed_ms=retrieval_elapsed,
            rerank_elapsed_ms=0,
            llm_elapsed_ms=llm_elapsed,
            total_elapsed_ms=total_elapsed,
            cache_hit=retrieval_result.cache_hit
        )

        #
        # ------------------------------------------------------
        # 会話履歴保存
        # ------------------------------------------------------
        #
        # 保存する履歴は従来どおりuser / assistantの両方。
        #
        # 今回変更したのは「保存方法」ではなく、
        # 「最終回答生成時にどの履歴を使うか」だけ。
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
            "documents": final_context_items,
            "retrieved_count": len(final_context_items),
            "elapsed_ms": total_elapsed,
            "is_off_topic": is_off_topic,
            "response_format": response_format
        }


query_service = QueryService()