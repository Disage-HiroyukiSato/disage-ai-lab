import pytest

from app.models.answerability import AnswerabilityResult, AnswerabilityStatus
from app.models.learning.follow_up import FollowUp
from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult
from app.services.query_service import QueryService


def _make_item(document="資料の内容", distance=0.20, score=0.80):
    return RetrievalItem(
        document=document,
        metadata={
            "document_id": "doc-001",
            "chunk_no": 1,
        },
        distance=distance,
        score=score,
    )


class TestQueryServiceLearningIntegration:
    """
    QueryService と Learning系サービス
    （LearningResponseController / LearningFollowUpService）
    の統合部分を検証する。

    ask() の内部で呼ばれる各サービスは、
    このテストクラス内でまとめてモックする。
    """

    def setup_method(self):

        # --------------------------------------------------
        # QueryServiceは__init__で
        # self.learning_follow_up_serviceを生成するため、
        # モジュールレベルのシングルトンではなく
        # 新規インスタンスを都度作成してテストする。
        # --------------------------------------------------

        self.service = QueryService()

    def _patch_common_dependencies(
        self,
        mocker,
        *,
        answerability_status: str = "FULL",
        gate_candidates=None,
    ):
        """
        ask() の実行に必要な依存を一括でモックする。

        個々のテストではこのヘルパーを呼んだ後、
        必要な戻り値だけ追加で上書きする。
        """

        if gate_candidates is None:
            gate_candidates = [_make_item()]

        mocker.patch(
            "app.services.query_service.query_normalizer.normalize",
            return_value="正規化済みの質問",
        )

        mocker.patch(
            "app.services.query_service.collection_router_service.route",
            return_value="java_training",
        )

        mocker.patch(
            "app.services.query_service.progress_service"
            ".get_current_chapter",
            return_value="",
        )

        mocker.patch(
            "app.services.query_service.off_topic_router_service"
            ".is_off_topic",
            return_value=False,
        )

        mocker.patch(
            "app.services.query_service.conversation_service"
            ".get_recent_turns",
            return_value=[],
        )

        mocker.patch(
            "app.services.query_service.conversation_service"
            ".get_recent_questions",
            return_value=[],
        )

        mocker.patch(
            "app.services.query_service.query_rewrite_service.analyze",
            return_value=("knowledge_query", "EXPLAIN"),
        )

        retrieval_items = [_make_item()]

        mocker.patch(
            "app.services.query_service.multi_query_retrieval_service"
            ".search",
            return_value=RetrievalResult(
                query="knowledge_query",
                total=len(retrieval_items),
                elapsed_ms=10,
                items=retrieval_items,
            ),
        )

        mocker.patch(
            "app.services.query_service.reranker_service.rerank",
            return_value=retrieval_items,
        )

        mocker.patch(
            "app.services.query_service.reranker_service.rerank_relaxed",
            return_value=gate_candidates,
        )

        mocker.patch(
            "app.services.query_service.answerability_gate_service.assess",
            return_value=AnswerabilityResult(
                status=AnswerabilityStatus(answerability_status),
                reason="テスト用の判定理由",
            ),
        )

        mocker.patch(
            "app.services.query_service.context_dedup_service"
            ".deduplicate",
            return_value=retrieval_items if gate_candidates else [],
        )

        mocker.patch(
            "app.services.query_service.llm_service.ask",
            return_value="生成された回答",
        )

        mocker.patch(
            "app.services.query_service.search_log_service.log",
            return_value=None,
        )

        mocker.patch(
            "app.services.query_service.conversation_service.append",
            return_value=None,
        )

    # ======================================================
    # LearningResponseController 統合
    # ======================================================

    def test_learning_response_instruction_is_passed_to_prompt_builder(
        self,
        mocker,
    ):
        learning_response_instruction = (
            "・初心者にも分かりやすく説明してください。\n"
            "・最初に結論を示してください。"
        )

        self._patch_common_dependencies(
            mocker,
            answerability_status="FULL",
        )

        mocker.patch(
            "app.services.query_service.learning_response_controller"
            ".decide",
            return_value=mocker.Mock(),
        )

        mocker.patch(
            "app.services.query_service.learning_response_controller"
            ".build_instruction",
            return_value=learning_response_instruction,
        )

        prompt_builder_mock = mocker.patch(
            "app.services.query_service.prompt_builder.build",
            return_value="generated prompt",
        )

        self.service.ask(
            question=(
                "toStringメソッドにはなぜOverrideアノテーションが"
                "ついていますか？"
            ),
        )

        prompt_builder_mock.assert_called_once()

        call_kwargs = prompt_builder_mock.call_args.kwargs

        assert (
            call_kwargs["learning_response_instruction"]
            == learning_response_instruction
        )

    def test_learning_response_controller_is_not_called_for_none(
        self,
        mocker,
    ):
        self._patch_common_dependencies(
            mocker,
            answerability_status="NONE",
        )

        controller_decide_mock = mocker.patch(
            "app.services.query_service.learning_response_controller"
            ".decide",
        )

        self.service.ask(
            question="資料にない質問",
        )

        controller_decide_mock.assert_not_called()

    # ======================================================
    # LearningFollowUpService 統合
    # ======================================================

    def test_follow_ups_are_generated_after_answer(
        self,
        mocker,
    ):
        follow_ups = [
            FollowUp(
                question="@Overrideアノテーションとは？",
                reason="回答に関連するアノテーションの理解を深めるため",
            )
        ]

        self._patch_common_dependencies(
            mocker,
            answerability_status="FULL",
        )

        mocker.patch(
            "app.services.query_service.learning_response_controller"
            ".decide",
            return_value=mocker.Mock(),
        )

        mocker.patch(
            "app.services.query_service.learning_response_controller"
            ".build_instruction",
            return_value="",
        )

        mocker.patch(
            "app.services.query_service.prompt_builder.build",
            return_value="generated prompt",
        )

        # --------------------------------------------------
        # self.service.learning_follow_up_service は
        # __init__で生成済みの実インスタンスなので、
        # generate() メソッドだけを差し替える。
        # --------------------------------------------------

        generate_mock = mocker.patch.object(
            self.service.learning_follow_up_service,
            "generate",
            return_value=follow_ups,
        )

        result = self.service.ask(
            question=(
                "toStringメソッドにはなぜOverrideアノテーションが"
                "ついていますか？"
            ),
        )

        generate_mock.assert_called_once()

        assert result["follow_ups"] == follow_ups

    def test_follow_ups_are_not_generated_when_answerability_is_none(
        self,
        mocker,
    ):
        self._patch_common_dependencies(
            mocker,
            answerability_status="NONE",
        )

        generate_mock = mocker.patch.object(
            self.service.learning_follow_up_service,
            "generate",
        )

        result = self.service.ask(
            question="資料に存在しない質問",
        )

        generate_mock.assert_not_called()

        assert result["follow_ups"] == []