from app.models.learning.follow_up import FollowUp
from app.services.learning.learning_follow_up_service import (
    LearningFollowUpService,
)


class TestLearningFollowUpService:

    def test_max_follow_ups_is_three(self):
        assert LearningFollowUpService.MAX_FOLLOW_UPS == 3


    def test_generate_returns_follow_up_list(self):
        service = LearningFollowUpService()

        result = service.generate(
            question="toStringメソッドにはなぜOverrideアノテーションがついていますか？",
            answer="ObjectクラスのtoStringメソッドをオーバーライドしているためです。",
            contexts=[
                "ObjectクラスにはtoStringメソッドが定義されています。",
            ],
        )

        assert isinstance(result, list)
        assert all(isinstance(item, FollowUp) for item in result)
        assert len(result) <= LearningFollowUpService.MAX_FOLLOW_UPS

    def test_generate_creates_follow_ups_from_context(self):
        service = LearningFollowUpService()

        result = service.generate(
            question="toStringメソッドにはなぜOverrideアノテーションがついていますか？",
            answer="ObjectクラスのtoStringメソッドをオーバーライドしているためです。",
            contexts=[
                "ObjectクラスにはtoStringメソッドが定義されています。"
                "@Overrideアノテーションを使用します。"
            ],
        )

        assert len(result) == 3

        questions = [item.question for item in result]

        assert "@Overrideアノテーションとは？" in questions
        assert "Objectクラスとは？" in questions
        assert "ObjectクラスのtoString()とは？" in questions

    def test_generate_deduplicates_follow_ups(self):
        service = LearningFollowUpService()

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=[
                "ObjectクラスにはtoStringメソッドがあります。",
                "ObjectクラスにはtoStringメソッドがあります。",
            ],
        )

        questions = [item.question for item in result]

        assert len(questions) == len(set(questions))

    def test_generate_returns_empty_for_empty_contexts(self):
        service = LearningFollowUpService()

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=[],
        )

        assert result == []