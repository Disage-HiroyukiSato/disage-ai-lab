"""
Tests for LearningResponseController.
"""

import pytest

from app.services.learning.learning_response_controller import (
    LearningAnswerLevel,
    LearningAnswerScope,
    LearningResponseController,
)


@pytest.fixture
def controller() -> LearningResponseController:
    """
    LearningResponseController fixture.
    """
    return LearningResponseController()


class TestLearningResponseController:
    """
    LearningResponseController の基本動作を検証する。
    """

    def test_full_answerability_uses_source_scope(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        FULLの場合は、RAGで取得した資料を根拠として回答する。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="EXPLAIN",
        )

        assert policy.answer_scope == LearningAnswerScope.SOURCE
        assert policy.allow_supplement is False

    def test_partial_answerability_allows_supplement(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        PARTIALの場合は、学習理解に必要な補足を許可する。
        """
        policy = controller.decide(
            answerability_status="PARTIAL",
            response_format="EXPLAIN",
        )

        assert policy.answer_scope == LearningAnswerScope.SUPPLEMENT
        assert policy.allow_supplement is True

    def test_none_answerability_is_restricted(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        NONEの場合は、根拠のない一般知識による回答を避ける。
        """
        policy = controller.decide(
            answerability_status="NONE",
            response_format="EXPLAIN",
        )

        assert policy.answer_scope == LearningAnswerScope.RESTRICTED
        assert policy.allow_supplement is False

    def test_unknown_answerability_is_restricted(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        未知のAnswerabilityStatusの場合は安全側に倒す。
        """
        policy = controller.decide(
            answerability_status="UNKNOWN",
            response_format="EXPLAIN",
        )

        assert policy.answer_scope == LearningAnswerScope.RESTRICTED
        assert policy.allow_supplement is False

    def test_explain_format_uses_normal_level(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        EXPLAINは、短答だけではなく最低限の説明が必要なため
        NORMALを使用する。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="EXPLAIN",
        )

        assert policy.answer_level == LearningAnswerLevel.NORMAL

    def test_diagram_format_allows_rephrasing(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        DIAGRAMでは資料内容を図解形式へ再表現できる。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="DIAGRAM",
        )

        assert policy.allow_rephrasing is True
        assert policy.answer_level == LearningAnswerLevel.NORMAL

    def test_code_format_allows_rephrasing(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        CODEでは資料内容をコード形式へ再表現できる。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="CODE",
        )

        assert policy.allow_rephrasing is True
        assert policy.answer_level == LearningAnswerLevel.NORMAL

    def test_summary_format_uses_short_level(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        SUMMARYでは短い回答を優先する。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="SUMMARY",
        )

        assert policy.answer_level == LearningAnswerLevel.SHORT

    def test_quiz_format_uses_short_level(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        QUIZでは短い回答を基本とする。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="QUIZ",
        )

        assert policy.answer_level == LearningAnswerLevel.SHORT

    @pytest.mark.parametrize(
        "response_format",
        [
            "EXPLAIN",
            "CODE",
            "COMPARE",
            "STEP_BY_STEP",
            "DIAGRAM",
            "DEBUG",
            "SUMMARY",
            "EXAMPLE",
        ],
    )
    def test_supported_formats_are_recognized(
        self,
        controller: LearningResponseController,
        response_format: str,
    ) -> None:
        """
        現在想定しているresponse_formatが正しく認識される。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format=response_format,
        )

        assert policy is not None

    def test_lowercase_values_are_normalized(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        status / response_format は大文字・小文字に依存しない。
        """
        policy = controller.decide(
            answerability_status="partial",
            response_format="diagram",
        )

        assert policy.answer_scope == LearningAnswerScope.SUPPLEMENT
        assert policy.answer_level == LearningAnswerLevel.NORMAL
        assert policy.allow_rephrasing is True
        assert policy.allow_supplement is True

    def test_none_values_are_handled_safely(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        status / response_format がNoneでも例外を発生させない。
        """
        policy = controller.decide(
            answerability_status=None,
            response_format=None,
        )

        assert policy.answer_scope == LearningAnswerScope.RESTRICTED
        assert policy.answer_level == LearningAnswerLevel.SHORT

    def test_empty_values_are_handled_safely(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        空文字が渡された場合も安全側に倒す。
        """
        policy = controller.decide(
            answerability_status="",
            response_format="",
        )

        assert policy.answer_scope == LearningAnswerScope.RESTRICTED
        assert policy.answer_level == LearningAnswerLevel.SHORT

    def test_none_answerability_always_uses_short_level(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        回答根拠がない場合、詳細な回答を生成しない。
        """
        formats = [
            "EXPLAIN",
            "CODE",
            "COMPARE",
            "STEP_BY_STEP",
            "DIAGRAM",
            "DEBUG",
            "EXAMPLE",
        ]

        for response_format in formats:
            policy = controller.decide(
                answerability_status="NONE",
                response_format=response_format,
            )

            assert policy.answer_scope == LearningAnswerScope.RESTRICTED
            assert policy.answer_level == LearningAnswerLevel.SHORT

    def test_beginner_friendly_is_enabled_by_default(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        研修AIでは初心者向け回答を基本方針とする。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="EXPLAIN",
        )

        assert policy.beginner_friendly is True

    def test_conclusion_is_presented_first(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        学習者が最初に結論を理解できるようにする。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="EXPLAIN",
        )

        assert policy.lead_with_conclusion is True

    def test_learning_guidance_is_enabled(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        今後の学習ナビゲーションにつなげるため、
        学習ガイダンスを有効にする。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="EXPLAIN",
        )

        assert policy.show_learning_guidance is True

    def test_follow_up_questions_are_not_generated_in_step1(
        self,
        controller: LearningResponseController,
    ) -> None:
        """
        Step 1ではFollow-up Questions生成をまだ実装しない。
        """
        policy = controller.decide(
            answerability_status="FULL",
            response_format="EXPLAIN",
        )

        assert policy.max_follow_up_questions == 0
