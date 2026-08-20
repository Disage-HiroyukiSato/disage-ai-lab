import json
import logging
import re

from app.services.llm_service import llm_service


logger = logging.getLogger(__name__)


class QueryRewriteService:

    # ------------------------------------------------------
    # 回答形式
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # 指示語・省略表現
    # ------------------------------------------------------
    #
    # 「もの」「これ」「それ」「上記」などは、検索時に
    # そのまま使用すると検索精度を下げる。
    #
    # 例：
    #
    # Q1: 基本データ型にはどのようなものがあるか。
    # Q2: よく使用するもの上位3つに対して...
    #
    # Q2の「もの」は「基本データ型」を指す。
    #
    # ------------------------------------------------------

    CONTEXT_REFERENCE_TERMS = (
        "これ",
        "これら",
        "それ",
        "それら",
        "その",
        "その内容",
        "その部分",
        "上記",
        "前述",
        "先ほど",
        "先ほどの",
        "前の",
        "前回",
        "今回の",
        "もの",
        "ものについて",
        "ものの",
        "同じもの",
        "この内容",
        "この部分",
        "この場合"
    )

    # ------------------------------------------------------
    # 出力形式を表す表現
    # ------------------------------------------------------

    FORMAT_NOISE_PATTERNS = (

        r"で表してください",

        r"で表して",

        r"で表せますか",

        r"で表す",

        r"として出力してください",

        r"として出力して",

        r"を出力してください",

        r"を出力して",

        r"を教えてください",

        r"を教えて",

        r"について説明してください",

        r"について説明して",

        r"説明してください",

        r"説明して",

        r"サンプルコードを",

        r"サンプルコード",

        r"コードを",

        r"コードで",

        r"フローチャートで",

        r"図で",

        r"表で",

        r"一覧で",

        r"箇条書きで",

        r"ステップ形式で"

    )

    # ------------------------------------------------------
    # 会話履歴整形
    # ------------------------------------------------------

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

            content = str(
                turn.get(
                    "content",
                    ""
                )
            ).strip()

            if not content:
                continue

            if role == "user":

                speaker = "受講生"

            elif role == "assistant":

                speaker = "アシスタント"

            else:

                speaker = role or "不明"

            lines.append(
                f"{speaker}: {content}"
            )

        if not lines:
            return "なし"

        return "\n".join(
            lines
        )

    # ------------------------------------------------------
    # 直近の受講生質問だけを整形
    # ------------------------------------------------------
    #
    # 指示語解決ではassistant回答も参考にするが、
    # 最終的な知識トピックを決める際には、受講生が
    # 以前何を質問したかを特に重視する。
    #
    # ------------------------------------------------------

    def _format_user_questions(
        self,
        conversation_turns: list[dict] | None
    ) -> str:

        if not conversation_turns:
            return "なし"

        questions = []

        for turn in conversation_turns:

            if turn.get("role") != "user":
                continue

            content = str(
                turn.get(
                    "content",
                    ""
                )
            ).strip()

            if not content:
                continue

            questions.append(
                content
            )

        if not questions:
            return "なし"

        return "\n".join(
            f"{index + 1}. {question}"
            for index, question
            in enumerate(questions)
        )

    # ------------------------------------------------------
    # 指示語が含まれているか
    # ------------------------------------------------------

    def _contains_context_reference(
        self,
        question: str
    ) -> bool:

        normalized = question.strip()

        return any(
            term in normalized
            for term in self.CONTEXT_REFERENCE_TERMS
        )

    # ------------------------------------------------------
    # Query Rewrite Prompt
    # ------------------------------------------------------

    def _build_prompt(
        self,
        question: str,
        conversation_turns: list[dict] | None
    ) -> str:

        history_text = self._format_history(
            conversation_turns
        )

        user_questions = self._format_user_questions(
            conversation_turns
        )

        format_list = ", ".join(
            self.RESPONSE_FORMATS
        )

        has_context_reference = (
            self._contains_context_reference(
                question
            )
        )

        context_reference_instruction = ""

        if has_context_reference:

            context_reference_instruction = """
【重要：会話文脈の解決】

今回の質問には、直前または過去の会話を参照する表現が含まれています。

質問だけを見て検索キーワードを作ってはいけません。

会話履歴から、指示語・省略語が何を指しているかを判断し、
検索用のknowledge_queryを自己完結した表現にしてください。

特に「もの」という表現は重要です。

例：

受講生:
「基本データ型にはどのようなものがあるか。」

受講生:
「よく使用するもの上位3つに対してサンプルコードを出力してください。」

この場合、2つ目の「もの」は「基本データ型」を指します。

したがって、

knowledge_query:
「基本データ型」

としてください。

「よく使用するもの」
「上位3つ」
「サンプルコード」

をそのままknowledge_queryにしてはいけません。

また、指示語を解決するために、assistantの過去回答を
そのままknowledge_queryとしてコピーしてはいけません。

過去の受講生質問から、現在の知識トピックを特定してください。
"""

        else:

            context_reference_instruction = """
【会話文脈】

明確な指示語がない場合でも、会話の続きとして自然な場合は、
過去の質問から現在の知識トピックを判断してください。

ただし、現在の質問に明確なトピックがある場合は、
現在の質問を優先してください。
"""

        return f"""
あなたはRAG検索用のQuery Analysisを担当します。

目的は、受講生の質問から、

1. RAG検索に使用する「知識トピック」
2. 受講生が希望している「回答形式」

を分離することです。

【会話履歴】
{history_text}

【過去の受講生質問】
{user_questions}

【現在の質問】
{question}

{context_reference_instruction}

【knowledge_queryのルール】

1. knowledge_queryはRAG検索対象となる知識・技術・概念を表してください。

2. 「コードで」「サンプルコード」「表で」「図で」
   「フローチャートで」「説明してください」など、
   回答の形式や表現方法は原則として除外してください。

3. 「もの」「これ」「それ」「上記」などの指示語がある場合は、
   会話履歴から具体的な対象へ置き換えてください。

4. knowledge_queryは、現在の質問だけを見ても
   RAG検索対象が分かる自己完結した表現にしてください。

5. 回答形式をknowledge_queryに混ぜないでください。

6. 資料にあるかどうかをknowledge_queryの段階で判定しないでください。

7. 「Java研修の範囲外かどうか」をknowledge_queryの段階で判定しないでください。

8. HTML、CSS、JavaScript、SQLなど、現在のRAGに存在する可能性がある
   技術については、単に一般的な研修範囲外という理由で除外しないでください。

9. 現在の質問に明確な知識トピックがある場合は、
   過去の会話より現在の質問を優先してください。

【knowledge_queryの例】

例1:
質問:
「継承のサンプルコードをフローチャートで表すことはできますか？」

出力:
「継承」

例2:
質問:
「基本データ型にはどのようなものがあるか。」

出力:
「基本データ型」

例3:
会話:
「基本データ型にはどのようなものがあるか。」
現在:
「よく使用するもの上位3つに対してサンプルコードを出力してください。」

出力:
「基本データ型」

例4:
会話:
「継承とは何ですか？」
現在:
「それをフローチャートで表してください。」

出力:
「継承」

例5:
質問:
「HTMLとは？」

出力:
「HTML」

【response_format】

以下から1つだけ選択してください。

{format_list}

判断例:

通常の説明:
EXPLAIN

サンプルコード:
CODE

比較:
COMPARE

手順:
STEP_BY_STEP

フローチャート・図:
DIAGRAM

小テスト:
QUIZ

デバッグ:
DEBUG

要約:
SUMMARY

具体例:
EXAMPLE

【重要】

「サンプルコードを出力してください」のような質問でも、
knowledge_queryはコードではなく、
コードの対象となる知識トピックにしてください。

【出力形式】

JSONのみを出力してください。
Markdownや説明文は不要です。

{{
  "knowledge_query": "...",
  "response_format": "..."
}}
"""

    # ------------------------------------------------------
    # JSON抽出
    # ------------------------------------------------------

    JSON_BLOCK_PATTERN = re.compile(
        r"\{.*\}",
        re.DOTALL
    )

    def _extract_json(
        self,
        raw_response: str
    ) -> dict | None:

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

            return None

        if not isinstance(
            data,
            dict
        ):
            return None

        return data

    # ------------------------------------------------------
    # knowledge_queryの最低限の後処理
    # ------------------------------------------------------
    #
    # LLMが回答形式をknowledge_queryへ混ぜた場合に除去する。
    #
    # ただし、過度な文字列加工は行わない。
    # ------------------------------------------------------

    def _clean_knowledge_query(
        self,
        knowledge_query: str,
        fallback_query: str
    ) -> str:

        value = knowledge_query.strip()

        if not value:
            return fallback_query

        for pattern in self.FORMAT_NOISE_PATTERNS:

            value = re.sub(
                pattern,
                "",
                value,
                flags=re.IGNORECASE
            )

        value = re.sub(
            r"\s+",
            " ",
            value
        ).strip()

        value = value.strip(
            "、。！？!?：: "
        )

        if not value:
            return fallback_query

        return value

    # ------------------------------------------------------
    # response_format正規化
    # ------------------------------------------------------

    def _normalize_response_format(
        self,
        value: str
    ) -> str:

        response_format = str(
            value or ""
        ).strip().upper()

        if response_format in self.RESPONSE_FORMATS:
            return response_format

        if response_format:

            logger.warning(
                "Unknown response_format : %s. "
                "Falling back to %s.",
                response_format,
                self.DEFAULT_RESPONSE_FORMAT
            )

        return self.DEFAULT_RESPONSE_FORMAT

    # ------------------------------------------------------
    # LLM応答解析
    # ------------------------------------------------------

    def _parse_response(
        self,
        raw_response: str,
        fallback_query: str
    ) -> tuple[str, str]:

        data = self._extract_json(
            raw_response
        )

        if data is None:

            logger.warning(
                "Query analysis response has no valid JSON. "
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
        )

        response_format = str(
            data.get(
                "response_format",
                ""
            )
        )

        knowledge_query = (
            self._clean_knowledge_query(
                knowledge_query,
                fallback_query
            )
        )

        response_format = (
            self._normalize_response_format(
                response_format
            )
        )

        return (
            knowledge_query,
            response_format
        )

    # ------------------------------------------------------
    # LLM失敗時のローカルフォールバック
    # ------------------------------------------------------
    #
    # LLMが利用できない場合でも、会話中に直前の質問が
    # 存在する場合は、それを検索トピックとして利用できる
    # 可能性がある。
    #
    # ただし、勝手な意味推測は行わない。
    #
    # ------------------------------------------------------

    def _fallback_knowledge_query(
        self,
        question: str,
        conversation_turns: list[dict] | None
    ) -> str:

        if not conversation_turns:
            return question

        if not self._contains_context_reference(
            question
        ):
            return question

        previous_user_questions = [

            str(
                turn.get(
                    "content",
                    ""
                )
            ).strip()

            for turn in conversation_turns

            if turn.get("role") == "user"

            and str(
                turn.get(
                    "content",
                    ""
                )
            ).strip()
        ]

        if not previous_user_questions:
            return question

        # --------------------------------------------------
        # LLMが使用できない場合の最低限の保険。
        #
        # 完全な意味解析は行わず、
        # 「直前の受講生質問」を検索候補として利用する。
        # --------------------------------------------------

        previous_question = (
            previous_user_questions[-1]
        )

        logger.warning(
            "Using previous user question as "
            "fallback knowledge query: %s",
            previous_question
        )

        return previous_question

    # ------------------------------------------------------
    # 分析エントリポイント
    # ------------------------------------------------------
    #
    # 戻り値:
    #
    #   (
    #       knowledge_query,
    #       response_format
    #   )
    #
    # 既存QueryServiceとの互換性を維持するため、
    # 戻り値の構造は変更しない。
    #
    # ------------------------------------------------------

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

            raw_response = (
                llm_service.ask_rewriter(
                    prompt
                )
            )

        except Exception:

            logger.exception(
                "Query analysis failed."
            )

            fallback_query = (
                self._fallback_knowledge_query(
                    question,
                    conversation_turns
                )
            )

            return (
                fallback_query,
                self.DEFAULT_RESPONSE_FORMAT
            )

        knowledge_query, response_format = (
            self._parse_response(
                raw_response,
                question
            )
        )

        logger.info(
            "Query Analysis : "
            "question=%s -> "
            "knowledge_query=%s "
            "response_format=%s",
            question,
            knowledge_query,
            response_format
        )

        return (
            knowledge_query,
            response_format
        )


query_rewrite_service = QueryRewriteService()