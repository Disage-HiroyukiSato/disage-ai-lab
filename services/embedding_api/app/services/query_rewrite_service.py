import json
import logging
import re

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class QueryRewriteService:

    #
    # ------------------------------------------------------
    # Knowledge Query分離 + 回答形式判定
    # ------------------------------------------------------
    #
    # ユーザーの質問には「検索すべき知識」と「どう回答してほしいか
    # （出力形式）」が混ざっていることが多い。
    #
    # 例：「継承のサンプルコードをフローチャートで表すことは
    #       できますか？」
    #
    #   knowledge_query   : "継承"（資料検索に使う）
    #   response_format   : "DIAGRAM"（回答の見せ方）
    #
    # これらを分離せずそのまま検索クエリに使うと、
    # 「フローチャートで表す」のような表現形式の指定が
    # ノイズとなり、資料検索・Rerank・Answerability Gateの
    # 精度を下げてしまう。
    #
    # 会話履歴がある場合は、同じLLM呼び出しの中で
    # 「今の話の続きで」のような指示語の自己完結化も
    # 同時に行う。
    #

    RESPONSE_FORMATS = (

        "EXPLAIN",

        "CODE",

        "COMPARE",

        "STEP_BY_STEP",

        "DIAGRAM",

        "QUIZ",

        "DEBUG",

        "SUMMARY",

        "EXAMPLE"

    )

    DEFAULT_RESPONSE_FORMAT = "EXPLAIN"

    def _format_history(

        self,

        conversation_turns: list[dict] | None

    ) -> str:

        if not conversation_turns:

            return "なし"

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

        return "\n".join(

            lines

        )

    def _build_prompt(

        self,

        question: str,

        conversation_turns: list[dict] | None

    ) -> str:

        history_text = self._format_history(

            conversation_turns

        )

        format_list = ", ".join(

            self.RESPONSE_FORMATS

        )

        return f"""会話履歴:
{history_text}

質問: {question}

質問から「検索キーワード」と「回答形式」を抽出してJSONで出力して。

検索キーワード(knowledge_query)のルール:
- 「〜を表で」「〜をコードで」「〜を図で」「〜を一覧で」のような
  表現形式の指定は削除する
- 短い名詞句だけにする
- 例: 「継承のサンプルコードをフローチャートで表せますか」→「継承」

回答形式(response_format)は次から1つ選ぶ:
{format_list}

出力はこのJSON形式のみ。他の文章は書かない:
{{"knowledge_query": "...", "response_format": "..."}}
"""

    #
    # ------------------------------------------------------
    # LLM応答からJSONを抽出
    # ------------------------------------------------------
    #

    JSON_BLOCK_PATTERN = re.compile(

        r"\{.*\}",

        re.DOTALL

    )

    def _parse_response(

        self,

        raw_response: str,

        fallback_query: str

    ) -> tuple[str, str]:

        match = self.JSON_BLOCK_PATTERN.search(

            raw_response

        )

        if not match:

            logger.warning(

                "Query analysis response has no JSON block. "
                "Falling back to original question. "
                "raw_response=%s",

                raw_response

            )

            return (

                fallback_query,

                self.DEFAULT_RESPONSE_FORMAT

            )

        try:

            data = json.loads(

                match.group()

            )

        except json.JSONDecodeError:

            logger.warning(

                "Query analysis response is not valid JSON. "
                "Falling back to original question. "
                "raw_response=%s",

                raw_response

            )

            return (

                fallback_query,

                self.DEFAULT_RESPONSE_FORMAT

            )

        knowledge_query = str(

            data.get(

                "knowledge_query",

                ""

            )

        ).strip()

        response_format = str(

            data.get(

                "response_format",

                ""

            )

        ).strip().upper()

        if not knowledge_query:

            knowledge_query = fallback_query

        if response_format not in self.RESPONSE_FORMATS:

            if response_format:

                logger.warning(

                    "Unknown response_format : %s. "
                    "Falling back to %s.",

                    response_format,

                    self.DEFAULT_RESPONSE_FORMAT

                )

            response_format = self.DEFAULT_RESPONSE_FORMAT

        return (

            knowledge_query,

            response_format

        )

    #
    # ------------------------------------------------------
    # 分析エントリポイント
    # ------------------------------------------------------
    #
    # 戻り値 : (knowledge_query, response_format)
    #
    # LLM呼び出しに失敗した場合は、安全側として
    # (元の質問, EXPLAIN) にフォールバックする。
    #

    def analyze(

        self,

        question: str,

        conversation_turns: list[dict] | None

    ) -> tuple[str, str]:

        prompt = self._build_prompt(

            question,

            conversation_turns

        )

        try:

            raw_response = llm_service.ask_rewriter(

                prompt

            )

        except Exception:

            logger.exception(

                "Query analysis failed. "
                "Falling back to (original question, EXPLAIN)."

            )

            return (

                question,

                self.DEFAULT_RESPONSE_FORMAT

            )

        knowledge_query, response_format = self._parse_response(

            raw_response,

            question

        )

        logger.info(

            "Query Analysis : question=%s -> "
            "knowledge_query=%s response_format=%s",

            question,

            knowledge_query,

            response_format

        )

        return (

            knowledge_query,

            response_format

        )


query_rewrite_service = QueryRewriteService()