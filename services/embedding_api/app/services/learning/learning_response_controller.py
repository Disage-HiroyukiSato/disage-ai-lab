"""
Learning Response Controller.

学習者向け回答を生成するための「回答方針」を決定するサービス。

責務:
- 回答レベルの決定
- 学習者向け回答方針の決定
- AnswerabilityStatus に応じた回答方針の決定
- response_format に応じた回答方針の決定

このクラス自身はLLMを呼び出さない。
実際の回答生成は PromptBuilder / LLM 側が担当する。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LearningAnswerLevel(str, Enum):
    """
    学習者向け回答の詳細度。
    """

    SHORT = "short"
    NORMAL = "normal"
    DETAILED = "detailed"


class LearningAnswerScope(str, Enum):
    """
    回答に利用する情報の範囲。

    SOURCE:
        RAGで取得した資料を中心に回答する。

    SUPPLEMENT:
        資料の理解に必要な基礎知識を補足として利用する。

    RESTRICTED:
        資料から十分な根拠を確認できないため、
        推測による回答を避ける。
    """

    SOURCE = "source"
    SUPPLEMENT = "supplement"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class LearningResponsePolicy:
    """
    学習者向け回答生成ポリシー。

    このオブジェクトは「どのように回答するか」を表現する。
    実際の文章生成は行わない。
    """

    answer_level: LearningAnswerLevel
    answer_scope: LearningAnswerScope

    beginner_friendly: bool = True

    lead_with_conclusion: bool = True

    allow_rephrasing: bool = True

    allow_supplement: bool = False

    show_learning_guidance: bool = True

    max_follow_up_questions: int = 0


class LearningResponseController:
    """
    学習者向け回答方針を決定するController。

    QueryServiceから渡された情報をもとに、
    LLMへ渡す回答方針を決定する。

    重要:
        このクラスではLLMを呼び出さない。
        また、RAG検索も行わない。
    """

    # 現在の研修AIでは、最初の回答を短くすることを基本方針とする。
    DEFAULT_ANSWER_LEVEL = LearningAnswerLevel.SHORT

    # 将来的にFollow-up Questionsを実装するための上限。
    # Step 1では生成処理そのものは行わない。
    DEFAULT_MAX_FOLLOW_UP_QUESTIONS = 0

    def decide(
        self,
        *,
        answerability_status: Optional[str] = None,
        response_format: Optional[str] = None,
        question: Optional[str] = None,
    ) -> LearningResponsePolicy:
        """
        学習者向け回答ポリシーを決定する。

        Args:
            answerability_status:
                RAG側で判定された回答可能性。
                想定値:
                    FULL
                    PARTIAL
                    NONE

            response_format:
                QueryRewriteService等で判定された回答形式。
                例:
                    EXPLAIN
                    CODE
                    COMPARE
                    STEP_BY_STEP
                    DIAGRAM
                    QUIZ
                    DEBUG
                    SUMMARY
                    EXAMPLE

            question:
                現在の質問。
                Step 1では主として将来拡張用。
                現段階では回答方針決定に直接利用しない。

        Returns:
            LearningResponsePolicy
        """

        status = self._normalize(answerability_status)
        format_name = self._normalize(response_format)

        answer_scope = self._decide_scope(status)

        answer_level = self._decide_answer_level(
            response_format=format_name,
            answer_scope=answer_scope,
        )

        allow_supplement = (
            answer_scope == LearningAnswerScope.SUPPLEMENT
        )

        allow_rephrasing = (
            format_name in self._REPHRASABLE_FORMATS
        )

        return LearningResponsePolicy(
            answer_level=answer_level,
            answer_scope=answer_scope,
            beginner_friendly=True,
            lead_with_conclusion=True,
            allow_rephrasing=allow_rephrasing,
            allow_supplement=allow_supplement,
            show_learning_guidance=True,
            max_follow_up_questions=self.DEFAULT_MAX_FOLLOW_UP_QUESTIONS,
        )

    def _decide_scope(
        self,
        answerability_status: Optional[str],
    ) -> LearningAnswerScope:
        """
        AnswerabilityStatusから回答範囲を決定する。
        """

        if answerability_status == "FULL":
            return LearningAnswerScope.SOURCE

        if answerability_status == "PARTIAL":
            return LearningAnswerScope.SUPPLEMENT

        if answerability_status == "NONE":
            return LearningAnswerScope.RESTRICTED

        # 不明な状態では、安全側に倒す。
        return LearningAnswerScope.RESTRICTED

    def _decide_answer_level(
        self,
        *,
        response_format: Optional[str],
        answer_scope: LearningAnswerScope,
    ) -> LearningAnswerLevel:
        """
        回答形式と回答可能範囲から詳細度を決定する。
        """

        if answer_scope == LearningAnswerScope.RESTRICTED:
            return LearningAnswerLevel.SHORT

        if response_format in self._DETAILED_FORMATS:
            return LearningAnswerLevel.NORMAL

        if response_format in self._SHORT_FORMATS:
            return LearningAnswerLevel.SHORT

        return self.DEFAULT_ANSWER_LEVEL

    @staticmethod
    def _normalize(value: Optional[str]) -> Optional[str]:
        """
        文字列を比較しやすい形式へ正規化する。
        """

        if value is None:
            return None

        normalized = value.strip().upper()

        if not normalized:
            return None

        return normalized

    def build_instruction(
        self,
        policy: LearningResponsePolicy,
    ) -> str:
        """
        LearningResponsePolicyをPrompt用の指示文へ変換する。
        """

        instructions = []

        if policy.beginner_friendly:
            instructions.append(
                "・IT初心者や学習中の受講者にも理解しやすい言葉で説明してください。"
            )

        if policy.lead_with_conclusion:
            instructions.append(
                "・最初に質問への結論を簡潔に示してください。"
            )

        if policy.answer_level == LearningAnswerLevel.SHORT:
            instructions.append(
                "・最初の回答は簡潔にまとめ、必要以上に長く説明しないでください。"
            )

        elif policy.answer_level == LearningAnswerLevel.NORMAL:
            instructions.append(
                "・結論に加えて、受講者が理解するために必要な説明を簡潔に加えてください。"
            )

        elif policy.answer_level == LearningAnswerLevel.DETAILED:
            instructions.append(
                "・結論だけでなく、背景や理由も含めて段階的に説明してください。"
            )

        if policy.answer_scope == LearningAnswerScope.SOURCE:
            instructions.append(
                "・RAG資料の内容を根拠として回答してください。"
            )

        elif policy.answer_scope == LearningAnswerScope.SUPPLEMENT:
            instructions.append(
                "・RAG資料の内容を中心に回答し、理解に必要な基礎知識は補足して構いません。"
            )

            instructions.append(
                "・資料から確認できる内容と、理解のために補足した内容を混同しないでください。"
            )

        elif policy.answer_scope == LearningAnswerScope.RESTRICTED:
            instructions.append(
                "・RAG資料から確認できない内容を推測して回答しないでください。"
            )

        if policy.allow_rephrasing:
            instructions.append(
                "・資料の内容を、受講者が求める形式に分かりやすく整理・変換して構いません。"
            )

        if policy.show_learning_guidance:
            instructions.append(
                "・受講者が内容を理解しやすいよう、必要な場合は説明の順序を整理してください。"
            )

        return "\n".join(instructions)

    # ----------------------------------------------------
    # クラス変数（フォーマット分類）
    # ----------------------------------------------------
    #
    # メソッド定義より後にクラス変数を置いても
    # クラス属性としては問題なく機能するが、
    # 可読性のため定義位置はそのまま維持している。
    #

    _SHORT_FORMATS = {
        "SUMMARY",
        "QUIZ",
    }

    _DETAILED_FORMATS = {
        "EXPLAIN",
        "CODE",
        "COMPARE",
        "STEP_BY_STEP",
        "DIAGRAM",
        "DEBUG",
        "EXAMPLE",
    }

    _REPHRASABLE_FORMATS = {
        "EXPLAIN",
        "CODE",
        "COMPARE",
        "STEP_BY_STEP",
        "DIAGRAM",
        "SUMMARY",
        "EXAMPLE",
    }


# ==========================================================
# シングルトンインスタンス
# ==========================================================
#
# query_service.py からは、このインスタンスを直接importして
# 利用する。
#
#   from app.services.learning.learning_response_controller import (
#       learning_response_controller
#   )
#
# ==========================================================

learning_response_controller = LearningResponseController()