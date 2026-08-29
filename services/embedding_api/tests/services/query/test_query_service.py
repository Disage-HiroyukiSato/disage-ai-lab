from app.services.query_service import query_service
from app.services.learning.learning_response_controller import (
    LearningAnswerLevel,
    LearningAnswerScope,
    LearningResponseController,
)

def test_learning_response_instruction_is_passed_to_prompt_builder(
    self,
    mocker,
):
    learning_response_instruction = (
        "・初心者にも分かりやすく説明してください。\n"
        "・最初に結論を示してください。"
    )

    mocker.patch(
        "app.services.learning.learning_response_controller"
        ".learning_response_controller.decide",
        return_value=mocker.Mock(),
    )

    mocker.patch(
        "app.services.learning.learning_response_controller"
        ".learning_response_controller.build_instruction",
        return_value=learning_response_instruction,
    )

    prompt_builder = mocker.patch.object(
        self.service.prompt_builder,
        "build",
        return_value="generated prompt",
    )

    # 既存のQueryServiceテストで使用している
    # Retrieval / Answerability等のMockを設定して実行

    self.service.query(
        question="toStringメソッドにはなぜOverrideアノテーションがついていますか？",
        # 既存テストと同じ必要な引数
    )

    prompt_builder.assert_called_once()

    call_kwargs = prompt_builder.call_args.kwargs

    assert (
        call_kwargs["learning_response_instruction"]
        == learning_response_instruction
    )

def test_learning_response_controller_is_not_called_for_none(
    self,
    mocker,
):
    controller = mocker.patch(
        "app.services.learning.learning_response_controller"
        ".learning_response_controller.decide",
    )

    # Answerability = NONE になる既存Mockを設定

    self.service.query(
        question="資料にない質問",
        # 既存テストと同じ必要な引数
    )

    controller.assert_not_called()