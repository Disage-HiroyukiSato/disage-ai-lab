import logging
import time

from app.config import settings

from app.services.answerability_gate_service import (
    answerability_gate_service
)
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

        return retrieval_result, reranked_items, gate_candidates

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

        is_off_topic = off_topic_router_service.is_off_topic(

            normalized_question

        )

        conversation_turns = conversation_service.get_recent_turns(

            session_id

        )

        #
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

        knowledge_query, response_format = query_rewrite_service.analyze(

            normalized_question,

            conversation_turns

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
        # Retrieval Fallback（二段階検索）
        # ------------------------------------------------------
        #
        # 1段階目 : knowledge_query（表現形式を除いた検索専用の
        #           質問）で検索・Rerankerを実行する。
        #
        # 1段階目が弱い（Reranker通過0件）場合、
        #
        # 2段階目 : 正規化後の元の質問（normalized_question）で
        #           再検索する。knowledge_queryの抽出が
        #           不適切だった場合の保険として機能する。
        #
        # 2段階目も弱い場合、資料外として回答を拒否する。
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
        # 二段階検索を経ても弱い場合は資料外として拒否する。
        #

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
        # Context生成
        # ------------------------------------------------------
        #
        # Answerability GateがYesと判定した資料集合
        # （gate_candidates）をそのままLLMのコンテキストとして
        # 使用する。
        #
        # reranked_items（min_rerank_score通過分）は
        # CrossEncoderのスコアリング誤り（短い無意味な文字列に
        # 高スコアを付ける等）で、本来関連度の高い資料を
        # 取りこぼすことがあるため、Gateが実際に「答えられる」と
        # 判定した資料を優先する。
        #

        contexts = [

            item.document

            for item in gate_candidates

        ]

        #
        # デバッグ : 最終的にLLM（メイン回答生成）へ渡される
        # contextsの内訳をログに残す。
        #

        logger.info(

            "----------------------------------------"

        )

        logger.info(

            "Final Contexts for LLM (post-Gate)"

        )

        logger.info(

            "----------------------------------------"

        )

        for index, item in enumerate(

            gate_candidates,

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
        # Prompt生成
        #
        # 最終回答生成には元の質問（question）を使う。
        # response_formatに応じた出力指示を渡す。
        #

        prompt = prompt_builder.build(
            question,
            contexts,
            conversation_turns=conversation_turns,
            is_off_topic=is_off_topic,
            response_format=response_format
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

        logger.info("========================================")
        logger.info("RAG Query End")
        logger.info("========================================")
        logger.info("")

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
            "documents": gate_candidates,
            "retrieved_count": len(gate_candidates),
            "elapsed_ms": total_elapsed,
            "is_off_topic": is_off_topic,
            "response_format": response_format
        }


query_service = QueryService()