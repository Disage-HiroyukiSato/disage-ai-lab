from app.services.prompt.prompt_builder import PromptBuilder


class TestPromptBuilderLearningResponse:

    def test_learning_response_instruction_is_included(self):
        builder = PromptBuilder()

        instruction = (
            "・初心者にも分かりやすく説明してください。\n"
            "・最初に結論を示してください。"
        )

        prompt = builder.build(
            question="toStringメソッドにはなぜOverrideアノテーションがついていますか？",
            contexts=[
                "ObjectクラスにはtoStringメソッドが定義されています。"
            ],
            response_format="EXPLAIN",
            answerability_status="FULL",
            learning_response_instruction=instruction,
        )

        assert "学習者向け回答方針" in prompt
        assert "初心者にも分かりやすく説明してください。" in prompt
        assert "最初に結論を示してください。" in prompt

    def test_empty_learning_response_instruction_does_not_break_prompt(self):
        builder = PromptBuilder()

        prompt = builder.build(
            question="Javaとは何ですか？",
            contexts=["Javaはプログラミング言語です。"],
            response_format="EXPLAIN",
            answerability_status="FULL",
            learning_response_instruction="",
        )

        assert prompt
        assert "Javaとは何ですか？" in prompt

    def test_learning_response_instruction_coexists_with_answerability(self):
        builder = PromptBuilder()

        instruction = (
            "・資料にある内容を中心に説明してください。\n"
            "・初心者にも分かりやすく説明してください。"
        )

        prompt = builder.build(
            question="継承とは何ですか？",
            contexts=["継承では親クラスの機能を子クラスが利用できます。"],
            response_format="EXPLAIN",
            answerability_status="PARTIAL",
            answerability_reason="関連情報はあるが詳細が不足しています。",
            learning_response_instruction=instruction,
        )

        assert "学習者向け回答方針" in prompt
        assert "初心者にも分かりやすく説明してください。" in prompt
        assert "PARTIAL" in prompt
        assert "関連情報はあるが詳細が不足しています。" in prompt

    def test_learning_response_instruction_coexists_with_diagram_format(self):
        builder = PromptBuilder()

        instruction = (
            "・初心者にも分かりやすく説明してください。\n"
            "・資料の内容を分かりやすく整理してください。"
        )

        prompt = builder.build(
            question="継承のサンプルコードをフローチャートで表してください。",
            contexts=[
                "親クラスを継承して子クラスを作成するサンプルコードがあります。"
            ],
            response_format="DIAGRAM",
            answerability_status="FULL",
            learning_response_instruction=instruction,
        )

        assert "学習者向け回答方針" in prompt
        assert "初心者にも分かりやすく説明してください。" in prompt
        assert "DIAGRAM" in prompt
        assert "Mermaid" in prompt