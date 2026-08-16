import logging

from app.config import settings

logger = logging.getLogger(__name__)


class PromptBuilder:

    def build(

        self,

        question: str,

        contexts: list[str],

        conversation_turns: list[dict] | None = None,

        is_off_topic: bool = False

    ) -> str:

        logger.debug(

            "Prompt created"

        )

        prompt = self._build_internal(

            question,

            contexts,

            conversation_turns,

            is_off_topic

        )

        if settings.log_prompt:

            logger.debug(
                "Prompt\n%s",
                prompt
            )

        return prompt

    #
    # ------------------------------------------------------
    # Phase17 : マルチターン履歴の整形
    # ------------------------------------------------------
    #
    # conversation_service.get_recent_turns()の戻り値
    # （role/content/is_off_topicの辞書リスト）を、
    # プロンプトに埋め込むテキストへ変換する。
    #

    def _format_history(

        self,

        conversation_turns: list[dict] | None

    ) -> str:

        if not conversation_turns:

            return ""

        lines = []

        for turn in conversation_turns:

            role = turn.get(

                "role",

                ""

            )

            content = turn.get(

                "content",

                ""

            )

            speaker = (

                "受講生"

                if role == "user"

                else "アシスタント"

            )

            lines.append(

                f"{speaker}: {content}"

            )

        history_text = "\n".join(

            lines

        )

        return f"""
# これまでの会話

{history_text}
"""

    def _build_internal(

        self,

        question: str,

        contexts: list[str],

        conversation_turns: list[dict] | None,

        is_off_topic: bool

    ) -> str:

        #
        # Context生成
        #

        context = "\n\n".join(contexts)

        #
        # Phase17 : マルチターン履歴
        #

        history_section = self._format_history(

            conversation_turns

        )

        #
        # Phase17 : 教材外フラグ
        #
        # OffTopicRouterServiceでin_scopeキーワードに
        # 一致しなかった質問の場合、LLMへその旨を伝え、
        # 回答の冒頭で明示するよう指示する。
        #
        # 合意済み方針：回答自体は行うが、教材外であることを
        # 明示する。
        #

        off_topic_instruction = ""

        if is_off_topic:

            off_topic_instruction = """
・この質問はJava研修教材の範囲外である可能性があります。
・回答の冒頭で「この内容はJava研修教材の範囲外です。」と一言明示してから、
  分かる範囲で回答してください。
・教材に基づかない一般知識で補う場合は、資料からの回答ではないことが
  分かるようにしてください。
"""

        return f"""
あなたはJava研修受講生向けのAI学習アシスタントです。

# 回答ルール

・回答は必ず資料を根拠にしてください。
・資料に記載がない内容は推測しないでください。
・資料だけでは回答できない場合は
「資料からは確認できません。」
と回答してください。
・知識を補完しないでください。
・同じ内容を繰り返さないでください。
・資料の内容を最優先してください。
・回答は日本語で記載してください。
・回答は箇条書きを優先してください。
・回答は200文字以内を目安にしてください。
・資料中に複数候補がある場合は全て列挙してください。
・簡潔に回答してください。
・これまでの会話の文脈を踏まえて回答してください。
{off_topic_instruction}
{history_section}
# 資料

{context}

# 質問

{question}

# 回答
"""


prompt_builder = PromptBuilder()