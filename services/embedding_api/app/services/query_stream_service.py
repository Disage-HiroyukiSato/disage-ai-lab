import time

from app.config import settings
from app.models.answerability import AnswerabilityStatus
from app.services.conversation.conversation_service import conversation_service
from app.services.conversation.progress_service import progress_service
from app.services.infra.llm_service import llm_service
from app.services.learning.learning_follow_up_service import LearningFollowUpService
from app.services.learning.learning_response_controller import learning_response_controller
from app.services.observability.search_log_service import search_log_service
from app.services.prompt.prompt_builder import prompt_builder
from app.services.query_processing.collection_router_service import collection_router_service
from app.services.query_processing.off_topic_router_service import off_topic_router_service
from app.services.query_processing.query_normalizer import query_normalizer
from app.services.query_processing.query_rewrite_service import query_rewrite_service
from app.services.query_service import query_service
from app.services.retrieval.answerability_gate_service import answerability_gate_service
from app.services.retrieval.context_dedup_service import context_dedup_service


class QueryStreamService:

    def __init__(self):
        self.learning_follow_up_service = LearningFollowUpService()

    @staticmethod
    def _status(stage: str, message: str, **extra) -> dict:
        payload = {
            "type": "status",
            "stage": stage,
            "message": message,
        }
        payload.update(extra)
        return payload

    @staticmethod
    def _complete(result: dict) -> dict:
        return {
            "type": "complete",
            **result,
        }

    def stream(
        self,
        question: str,
        limit: int = 5,
        student_id: str | None = None,
        session_id: str | None = None,
    ):
        overall_start = time.perf_counter()

        yield self._status(
            "analysis",
            "質問内容を確認しています"
        )

        normalized_question = query_normalizer.normalize(question)

        if not normalized_question:
            metadata = query_service._build_response_metadata(
                analyze_elapsed_ms=0,
                retrieval_elapsed_ms=0,
                rerank_elapsed_ms=0,
                answerability_elapsed_ms=0,
                llm_elapsed_ms=0,
                total_elapsed_ms=int((time.perf_counter() - overall_start) * 1000),
                fallback_used=False,
                cache_hit=False,
                retrieved_count=0,
                gate_candidate_count=0,
                final_context_count=0,
            )
            yield self._complete({
                "answer": "質問内容を確認できませんでした。",
                "sources": [],
                "source_pages": [],
                "answerability_status": None,
                "answerability_reason": "",
                "follow_ups": [],
                "metadata": metadata,
            })
            return

        collection_name = collection_router_service.route(
            normalized_question
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
        conversation_questions = conversation_service.get_recent_questions(
            session_id
        )

        analyze_start = time.perf_counter()
        knowledge_query, response_format = query_rewrite_service.analyze(
            normalized_question,
            conversation_turns,
        )
        analyze_elapsed = int(
            (time.perf_counter() - analyze_start) * 1000
        )

        yield self._status(
            "retrieval",
            "関連する社内資料を検索しています"
        )

        retrieval_start = time.perf_counter()
        (
            retrieval_result,
            reranked_items,
            gate_candidates,
            rerank_elapsed,
        ) = query_service._search_and_rerank(
            search_query=knowledge_query,
            collection_name=collection_name,
            current_chapter=current_chapter,
            limit=limit,
        )

        fallback_used = False
        if query_service._is_weak(gate_candidates):
            fallback_used = True
            (
                retrieval_result,
                reranked_items,
                gate_candidates,
                fallback_rerank_elapsed,
            ) = query_service._search_and_rerank(
                search_query=normalized_question,
                collection_name=collection_name,
                current_chapter=current_chapter,
                limit=limit,
            )
            rerank_elapsed += fallback_rerank_elapsed

        retrieval_elapsed = int(
            (time.perf_counter() - retrieval_start) * 1000
        )

        if not gate_candidates:
            metadata = query_service._build_response_metadata(
                analyze_elapsed_ms=analyze_elapsed,
                retrieval_elapsed_ms=retrieval_elapsed,
                rerank_elapsed_ms=rerank_elapsed,
                answerability_elapsed_ms=0,
                llm_elapsed_ms=0,
                total_elapsed_ms=int((time.perf_counter() - overall_start) * 1000),
                fallback_used=fallback_used,
                cache_hit=retrieval_result.cache_hit,
                retrieved_count=retrieval_result.total,
                gate_candidate_count=0,
                final_context_count=0,
            )
            yield self._complete({
                "answer": "資料から回答できませんでした。",
                "sources": [],
                "source_pages": [],
                "answerability_status": None,
                "answerability_reason": "",
                "follow_ups": [],
                "metadata": metadata,
            })
            return

        yield self._status(
            "answerability",
            "回答の根拠として使える情報を確認しています",
            retrieved_count=retrieval_result.total,
        )

        gate_query = normalized_question if fallback_used else knowledge_query
        gate_start = time.perf_counter()
        answerability_result = answerability_gate_service.assess(
            question=gate_query,
            items=gate_candidates,
        )
        answerability_elapsed = int(
            (time.perf_counter() - gate_start) * 1000
        )

        if answerability_result.status == AnswerabilityStatus.NONE:
            metadata = query_service._build_response_metadata(
                analyze_elapsed_ms=analyze_elapsed,
                retrieval_elapsed_ms=retrieval_elapsed,
                rerank_elapsed_ms=rerank_elapsed,
                answerability_elapsed_ms=answerability_elapsed,
                llm_elapsed_ms=0,
                total_elapsed_ms=int((time.perf_counter() - overall_start) * 1000),
                fallback_used=fallback_used,
                cache_hit=retrieval_result.cache_hit,
                retrieved_count=retrieval_result.total,
                gate_candidate_count=len(gate_candidates),
                final_context_count=0,
            )
            yield self._complete({
                "answer": "資料からは確認できません。",
                "sources": [],
                "source_pages": [],
                "answerability_status": answerability_result.status.value,
                "answerability_reason": answerability_result.reason,
                "follow_ups": [],
                "metadata": metadata,
            })
            return

        final_context_items = context_dedup_service.deduplicate(
            reranked_items + gate_candidates
        )

        if not final_context_items:
            metadata = query_service._build_response_metadata(
                analyze_elapsed_ms=analyze_elapsed,
                retrieval_elapsed_ms=retrieval_elapsed,
                rerank_elapsed_ms=rerank_elapsed,
                answerability_elapsed_ms=answerability_elapsed,
                llm_elapsed_ms=0,
                total_elapsed_ms=int((time.perf_counter() - overall_start) * 1000),
                fallback_used=fallback_used,
                cache_hit=retrieval_result.cache_hit,
                retrieved_count=retrieval_result.total,
                gate_candidate_count=len(gate_candidates),
                final_context_count=0,
            )
            yield self._complete({
                "answer": "回答に利用できる資料を整理できませんでした。",
                "sources": [],
                "source_pages": [],
                "answerability_status": answerability_result.status.value,
                "answerability_reason": answerability_result.reason,
                "follow_ups": [],
                "metadata": metadata,
            })
            return

        contexts = [item.document for item in final_context_items]
        sources = query_service._build_sources(final_context_items)
        source_pages = query_service._build_source_pages(final_context_items)

        learning_response_policy = learning_response_controller.decide(
            question=question,
            answerability_status=answerability_result.status.value,
            response_format=response_format,
        )
        learning_response_instruction = (
            learning_response_controller.build_instruction(
                learning_response_policy
            )
        )

        prompt = prompt_builder.build(
            question=question,
            contexts=contexts,
            conversation_questions=conversation_questions,
            is_off_topic=is_off_topic,
            response_format=response_format,
            answerability_status=answerability_result.status.value,
            answerability_reason=answerability_result.reason,
            source_pages=source_pages,
            learning_response_instruction=learning_response_instruction,
            answer_level=learning_response_policy.answer_level.value,
        )

        yield self._status(
            "generation",
            "回答を生成しています",
            source_count=len(sources),
        )

        llm_start = time.perf_counter()
        answer_parts: list[str] = []

        for token in llm_service.ask_stream(prompt):
            answer_parts.append(token)
            yield {
                "type": "token",
                "text": token,
            }

        answer = "".join(answer_parts).strip()
        llm_elapsed = int(
            (time.perf_counter() - llm_start) * 1000
        )
        total_elapsed = int(
            (time.perf_counter() - overall_start) * 1000
        )

        metadata = query_service._build_response_metadata(
            analyze_elapsed_ms=analyze_elapsed,
            retrieval_elapsed_ms=retrieval_elapsed,
            rerank_elapsed_ms=rerank_elapsed,
            answerability_elapsed_ms=answerability_elapsed,
            llm_elapsed_ms=llm_elapsed,
            total_elapsed_ms=total_elapsed,
            fallback_used=fallback_used,
            cache_hit=retrieval_result.cache_hit,
            retrieved_count=retrieval_result.total,
            gate_candidate_count=len(gate_candidates),
            final_context_count=len(final_context_items),
        )

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
            cache_hit=retrieval_result.cache_hit,
        )

        follow_ups = self.learning_follow_up_service.generate(
            question=question,
            answer=answer,
            contexts=contexts,
        )

        conversation_service.append(
            session_id=session_id,
            student_id=student_id,
            role="user",
            content=question,
        )
        conversation_service.append(
            session_id=session_id,
            student_id=student_id,
            role="assistant",
            content=answer,
            is_off_topic=is_off_topic,
        )

        follow_up_payload = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in follow_ups
        ]

        yield self._complete({
            "answer": answer,
            "sources": sources,
            "source_pages": source_pages,
            "answerability_status": answerability_result.status.value,
            "answerability_reason": answerability_result.reason,
            "follow_ups": follow_up_payload,
            "metadata": metadata,
        })


query_stream_service = QueryStreamService()
