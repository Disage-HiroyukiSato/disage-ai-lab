import logging

from app.config import settings

logger = logging.getLogger(__name__)

class PromptBuilder:

    def build(

        self,

        question: str,

        contexts: list[str]

    ) -> str:

        logger.debug(

            "Prompt created"

        )

        if settings.log_prompt:

            logger.debug(
                "Prompt\n%s",
                prompt
            )

        #
        # Context生成
        #

        context = "\n\n".join(contexts)

        return f"""
あなたは社内RAG専用AIです。

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

# 資料

{context}

# 質問

{question}

# 回答
"""

prompt_builder = PromptBuilder()