import logging

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class QueryRewriteService:

    #
    # ------------------------------------------------------
    # Phase17 : Query Rewriting
    # ------------------------------------------------------
    #
    # 「今の話の続きで」のような指示語・省略を含む質問は、
    # そのままVector検索・BM25検索・Rerankerに渡しても
    # 意味的な関連度が低く、検索が失敗する。
    #
    # 会話履歴がある場合のみ、直近の会話を踏まえて
    # 質問を「単体で意味が通る自己完結型の質問」に
    # LLMで書き換える。
    #
    # 検索・Reranker用にのみ使用し、最終回答生成の
    # プロンプトには元の質問文（question）を使う
    # （受講生に見える文脈は変えないため）。
    #

    def rewrite(

        self,

        question: str,

        conversation_turns: list[dict] | None

    ) -> str:

        #
        # 履歴が無い場合は書き換え不要
        #
        # 1ターン目の質問はそもそも自己完結しているため、
        # 無駄なLLM呼び出しを避ける。
        #

        if not conversation_turns:

            return question

        history_lines = []

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

            history_lines.append(

                f"{speaker}: {content}"

            )

        history_text = "\n".join(

            history_lines

        )

        prompt = f"""
以下は受講生とAI学習アシスタントとの会話履歴です。

# 会話履歴

{history_text}

# 最新の質問

{question}

# 指示

「最新の質問」は会話の文脈に依存した表現（指示語・省略）を
含んでいる場合があります。

会話履歴の内容を踏まえて、この質問を単体で読んでも
意味が通じる、自己完結した1つの質問文に書き換えてください。

書き換えた質問文のみを出力してください。
説明や前置きは不要です。
質問文が既に自己完結している場合は、そのまま出力してください。

# 書き換え後の質問
"""

        try:

            rewritten = llm_service.ask_rewriter(

                prompt

            )

        except Exception:

            logger.exception(

                "Query rewrite failed. "
                "Falling back to original question."

            )

            return question

        rewritten = rewritten.strip()

        if not rewritten:

            logger.warning(

                "Query rewrite returned empty result. "
                "Falling back to original question."

            )

            return question

        logger.info(

            "Query Rewrite : %s -> %s",

            question,

            rewritten

        )

        return rewritten


query_rewrite_service = QueryRewriteService()