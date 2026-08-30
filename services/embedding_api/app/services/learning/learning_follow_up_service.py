import json
import logging
import re

from app.models.learning.follow_up import FollowUp
from app.services.infra.llm_service import llm_service


logger = logging.getLogger(__name__)


class LearningFollowUpService:

    # ======================================================
    # Follow-up Questions
    # ======================================================
    #
    # 「回答内容の研修特化改修」の方針に基づき、
    # Follow-upは単なる関連質問の列挙ではなく、
    #
    #     回答に登場した概念を、理解のために掘り下げる
    #     ナビゲーション
    #
    # として位置付ける。
    #
    # 特定の文字列（"Objectクラス" 等）に対する
    # if文の羅列では、教材が増えるたびに個別対応が
    # 必要になり汎用性がないため、軽量LLM
    # （llama-rewriterコンテナ、query_rewrite_serviceや
    # answerability_gate_serviceと同じ呼び出し経路）を
    # 使用して、質問・回答・contextsから動的に
    # Follow-upを抽出する。
    #
    # LLM呼び出しが失敗した場合や、応答の解析に
    # 失敗した場合は、空リストを返す。
    #
    # Follow-up生成の失敗は回答本体の品質・可用性に
    # 影響を与えてはならないため、例外はここで
    # 握りつぶし、呼び出し元（query_service）には
    # 常に正常なlist[FollowUp]を返す。
    #
    # ======================================================

    MAX_FOLLOW_UPS = 3

    # ======================================================
    # JSON抽出
    # ======================================================
    #
    # query_rewrite_service._extract_json()と同様、
    # LLM応答からJSON配列/オブジェクト部分のみを
    # 抽出する。
    #
    # ======================================================

    JSON_BLOCK_PATTERN = re.compile(
        r"\[.*\]|\{.*\}",
        re.DOTALL
    )

    # ======================================================
    # Prompt
    # ======================================================

    def _build_prompt(
        self,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> str:

        joined_contexts = "\n\n".join(

            f"[資料{index}]\n{context}"

            for index, context in enumerate(
                contexts,
                start=1
            )

        )

        return f"""
あなたはJava研修受講生向けのAI学習アシスタントです。

あなたの役割は、今回の質問と回答を踏まえて、
受講生が「次に学ぶと理解が深まる概念」を
抽出することです。

# 重要な考え方

Follow-upは単なる関連質問の列挙ではありません。

今回の回答の中に登場した概念のうち、
受講生がまだ理解していない可能性がある、
または理解を深めるために掘り下げる価値のある
概念をFollow-upとして提示してください。

例えば、

質問：
「toStringメソッドにはなぜOverrideアノテーションが
ついていますか？」

回答：
「ObjectクラスのtoStringメソッドをオーバーライド
しているためです。」

の場合、回答に登場した

・Objectクラス
・toString
・Override
・@Override（アノテーション）

のうち、受講生の理解を深めるのに役立つ概念を
Follow-upとして抽出してください。

# 抽出ルール

・今回の質問・回答・資料に実際に登場した概念、
またはそれらから直接連想される学習項目のみを
対象にしてください。

・資料に存在しない発展的な話題を、
資料の内容であるかのように提示しないでください。

・Follow-upの質問文は、受講生がそのまま次の質問として
使える形式にしてください（例：「Objectクラスとは？」）。

・reasonには、なぜその概念を学ぶとよいかを
簡潔に日本語で記載してください。

・最大{self.MAX_FOLLOW_UPS}件までとしてください。

・today's回答内容と重複する内容や、
同じ概念を言い換えただけのFollow-upは
出力しないでください。

・資料・回答から学習項目を抽出できない場合は、
空の配列を出力してください。

# 資料

{joined_contexts if contexts else "資料なし"}

# 質問

{question}

# 回答

{answer}

# 出力形式

JSONのみを出力してください。

Markdownや説明文は不要です。

[
  {{
    "question": "...",
    "reason": "..."
  }}
]
"""

    # ======================================================
    # LLM応答解析
    # ======================================================

    def _extract_json(
        self,
        raw_response: str
    ) -> list | dict | None:

        if not raw_response:
            return None

        match = self.JSON_BLOCK_PATTERN.search(
            raw_response
        )

        if not match:
            return None

        try:

            data = json.loads(
                match.group()
            )

        except json.JSONDecodeError:

            logger.warning(
                "Failed to parse follow-up JSON."
            )

            return None

        return data

    def _parse_response(
        self,
        raw_response: str
    ) -> list[FollowUp]:

        data = self._extract_json(
            raw_response
        )

        if data is None:

            logger.warning(
                "Follow-up response has no valid JSON. "
                "raw_response=%s",
                raw_response
            )

            return []

        #
        # LLMが {"follow_ups": [...]} 形式で
        # 返した場合のフォールバック対応。
        #

        if isinstance(data, dict):

            data = data.get(
                "follow_ups",
                []
            )

        if not isinstance(data, list):

            logger.warning(
                "Follow-up JSON is not a list : %s",
                data
            )

            return []

        follow_ups: list[FollowUp] = []

        for entry in data:

            if not isinstance(entry, dict):
                continue

            question_text = str(
                entry.get(
                    "question",
                    ""
                )
            ).strip()

            reason_text = str(
                entry.get(
                    "reason",
                    ""
                )
            ).strip()

            if not question_text or not reason_text:
                continue

            try:

                follow_ups.append(
                    FollowUp(
                        question=question_text,
                        reason=reason_text,
                    )
                )

            except Exception:

                logger.warning(
                    "Invalid follow-up entry skipped : %s",
                    entry
                )

                continue

        return follow_ups

    # ======================================================
    # 重複除去
    # ======================================================

    def _deduplicate(
        self,
        follow_ups: list[FollowUp],
    ) -> list[FollowUp]:

        result: list[FollowUp] = []
        seen: set[str] = set()

        for follow_up in follow_ups:

            if follow_up.question in seen:
                continue

            seen.add(follow_up.question)

            result.append(follow_up)

        return result[: self.MAX_FOLLOW_UPS]

    # ======================================================
    # 生成エントリポイント
    # ======================================================

    def generate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> list[FollowUp]:

        if not contexts:
            return []

        prompt = self._build_prompt(
            question=question,
            answer=answer,
            contexts=contexts,
        )

        try:

            raw_response = llm_service.ask_rewriter(
                prompt
            )

        except Exception:

            logger.exception(
                "Follow-up generation failed."
            )

            return []

        follow_ups = self._parse_response(
            raw_response
        )

        follow_ups = self._deduplicate(
            follow_ups
        )

        logger.info(
            "Follow-up generated : question=%s count=%d",
            question,
            len(follow_ups)
        )

        return follow_ups