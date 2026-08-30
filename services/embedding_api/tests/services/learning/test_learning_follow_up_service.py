import json

from app.models.learning.follow_up import FollowUp
from app.services.learning.learning_follow_up_service import (
    LearningFollowUpService,
)


class TestLearningFollowUpService:

    def test_max_follow_ups_is_three(self):
        assert LearningFollowUpService.MAX_FOLLOW_UPS == 3

    def test_generate_returns_empty_for_empty_contexts(self):
        service = LearningFollowUpService()

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=[],
        )

        assert result == []

    def test_generate_returns_follow_up_list_from_llm(self, monkeypatch):
        service = LearningFollowUpService()

        llm_response = json.dumps(
            [
                {
                    "question": "@Overrideアノテーションとは？",
                    "reason": "回答に関連するアノテーションの理解を深めるため",
                },
                {
                    "question": "Objectクラスとは？",
                    "reason": "回答に登場するObjectクラスの理解を深めるため",
                },
                {
                    "question": "ObjectクラスのtoString()とは？",
                    "reason": "回答に登場するtoString()の理解を深めるため",
                },
            ],
            ensure_ascii=False,
        )

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: llm_response,
        )

        result = service.generate(
            question="toStringメソッドにはなぜOverrideアノテーションがついていますか？",
            answer="ObjectクラスのtoStringメソッドをオーバーライドしているためです。",
            contexts=[
                "ObjectクラスにはtoStringメソッドが定義されています。"
                "@Overrideアノテーションを使用します。"
            ],
        )

        assert isinstance(result, list)
        assert all(isinstance(item, FollowUp) for item in result)
        assert len(result) == 3

        questions = [item.question for item in result]

        assert "@Overrideアノテーションとは？" in questions
        assert "Objectクラスとは？" in questions
        assert "ObjectクラスのtoString()とは？" in questions

    def test_generate_limits_to_max_follow_ups(self, monkeypatch):
        service = LearningFollowUpService()

        llm_response = json.dumps(
            [
                {"question": "質問1", "reason": "理由1"},
                {"question": "質問2", "reason": "理由2"},
                {"question": "質問3", "reason": "理由3"},
                {"question": "質問4", "reason": "理由4"},
            ],
            ensure_ascii=False,
        )

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: llm_response,
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        assert len(result) == LearningFollowUpService.MAX_FOLLOW_UPS

    def test_generate_deduplicates_follow_ups(self, monkeypatch):
        service = LearningFollowUpService()

        llm_response = json.dumps(
            [
                {"question": "重複する質問", "reason": "理由A"},
                {"question": "重複する質問", "reason": "理由B"},
                {"question": "別の質問", "reason": "理由C"},
            ],
            ensure_ascii=False,
        )

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: llm_response,
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        questions = [item.question for item in result]

        assert len(questions) == len(set(questions))
        assert len(result) == 2

    def test_generate_returns_empty_when_llm_raises(self, monkeypatch):
        service = LearningFollowUpService()

        def raise_error(prompt):
            raise RuntimeError("LLM connection failed")

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            raise_error,
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        assert result == []

    def test_generate_returns_empty_when_response_is_not_json(
        self, monkeypatch
    ):
        service = LearningFollowUpService()

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: "これはJSONではありません。",
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        assert result == []

    def test_generate_returns_empty_when_llm_returns_empty_array(
        self, monkeypatch
    ):
        service = LearningFollowUpService()

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: "[]",
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        assert result == []

    def test_generate_skips_entries_missing_required_fields(
        self, monkeypatch
    ):
        service = LearningFollowUpService()

        llm_response = json.dumps(
            [
                {"question": "質問のみ"},
                {"reason": "理由のみ"},
                {"question": "完全な質問", "reason": "完全な理由"},
            ],
            ensure_ascii=False,
        )

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: llm_response,
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        assert len(result) == 1
        assert result[0].question == "完全な質問"

    def test_generate_handles_wrapped_object_response(self, monkeypatch):
        service = LearningFollowUpService()

        llm_response = json.dumps(
            {
                "follow_ups": [
                    {"question": "ラップされた質問", "reason": "理由"},
                ]
            },
            ensure_ascii=False,
        )

        monkeypatch.setattr(
            "app.services.learning.learning_follow_up_service."
            "llm_service.ask_rewriter",
            lambda prompt: llm_response,
        )

        result = service.generate(
            question="質問",
            answer="回答",
            contexts=["資料"],
        )

        assert len(result) == 1
        assert result[0].question == "ラップされた質問"