import json
import logging
import re

from app.services.llm_service import llm_service


logger = logging.getLogger(__name__)


class QueryRewriteService:

    # ======================================================
    # 回答形式
    # ======================================================

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

    # ======================================================
    # 指示語・省略表現
    # ======================================================
    #
    # 検索対象を特定するために、会話履歴を参照すべき
    # 表現。
    #
    # 「もの」は単独では意味を持たないことが多いため、
    # 特に重要。
    #
    # ======================================================

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

    # ======================================================
    # 回答形式に関するノイズ
    # ======================================================
    #
    # LLMがknowledge_queryへ回答形式まで含めてしまった
    # 場合に最低限除去する。
    #
    # ただし、ここでは「知識トピックそのもの」を
    # 削除しない。
    #
    # ======================================================

    FORMAT_NOISE_PATTERNS = (

        r"サンプルコードを",
        r"サンプルコード",
        r"コードを",
        r"コードで",

        r"フローチャートで",
        r"フローチャートを",

        r"図で",
        r"図を",

        r"表で",
        r"表を",

        r"一覧で",
        r"一覧を",

        r"箇条書きで",

        r"ステップ形式で",

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
        r"説明して"
    )

    # ======================================================
    # 会話履歴整形
    # ======================================================

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

        return "\n".join(lines)

    # ======================================================
    # 受講生質問のみ抽出
    # ======================================================
    #
    # knowledge_queryを決める際には、assistant回答そのものを
    # トピックとしてコピーしない。
    #
    # ======================================================

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

    # ======================================================
    # 指示語が含まれているか
    # ======================================================

    def _contains_context_reference(
        self,
        question: str
    ) -> bool:

        normalized = question.strip()

        return any(
            term in normalized
            for term in self.CONTEXT_REFERENCE_TERMS
        )

    # ======================================================
    # Query Rewrite Prompt
    # ======================================================

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

        if has_context_reference:

            context_instruction = """
【会話文脈の解決が必要】

現在の質問には、過去の会話を参照する表現が含まれています。

「これ」「それ」「もの」「上記」などをそのまま
knowledge_queryにしてはいけません。

会話履歴から、それらが指している具体的な
「知識トピック」を特定してください。

重要なのは、過去の質問全文をコピーすることではありません。

現在の質問が「何について質問しているのか」を特定し、
その知識トピックだけをknowledge_queryにしてください。

例えば、

受講生:
「基本データ型にはどのようなものがあるか。」

受講生:
「よく使用するもの上位3つに対してサンプルコードを
出力してください。」

この場合、

knowledge_query:
「基本データ型」

response_format:
「CODE」

としてください。

「よく使用するもの」
「上位3つ」
「サンプルコード」

をknowledge_queryにしてはいけません。
"""

        else:

            context_instruction = """
【会話文脈】

現在の質問に明確な知識トピックがある場合は、
現在の質問を最優先してください。

現在の質問だけでは知識トピックが不足している場合のみ、
過去の会話からトピックを補完してください。

過去のassistant回答をknowledge_queryとして
そのままコピーしてはいけません。
"""

        return f"""
あなたはRAG検索用のQuery Analysisを担当します。

あなたの仕事は、受講生の質問を分析し、

1. RAG検索に使用する「知識トピック」
2. 受講生が希望している「回答形式」

を分離することです。

==================================================
【最重要ルール】
==================================================

knowledge_queryは、

「回答の対象となる知識・技術・概念」

です。

回答の表現方法ではありません。

例えば、

「継承のサンプルコードをフローチャートで
表すことはできますか？」

という質問の場合、

knowledge_query:
「継承」

response_format:
「DIAGRAM」

です。

「サンプルコード」
「フローチャート」
「表すこと」

をknowledge_queryに含めてはいけません。

==================================================
【会話履歴】
==================================================

{history_text}

==================================================
【過去の受講生質問】
==================================================

{user_questions}

==================================================
【現在の質問】
==================================================

{question}

{context_instruction}

==================================================
【knowledge_queryのルール】
==================================================

1.
knowledge_queryはRAG検索対象となる
知識・技術・概念・テーマを表してください。

2.
回答形式をknowledge_queryに混ぜないでください。

例えば、

「継承のサンプルコード」
ではなく
「継承」

「継承をフローチャートで」
ではなく
「継承」

「基本データ型を表で」
ではなく
「基本データ型」

としてください。

3.
以下のような表現は、原則として
knowledge_queryから除外してください。

・サンプルコード
・コード
・フローチャート
・図
・表
・一覧
・箇条書き
・ステップ形式
・説明してください
・教えてください
・出力してください

ただし、これらを除外した結果、
知識トピックまで失ってはいけません。

4.
「これ」「それ」「もの」「上記」
などの指示語がある場合は、
会話履歴から具体的な知識トピックへ
置き換えてください。

5.
knowledge_queryは、現在の質問だけを見ても
RAG検索対象が分かる自己完結した表現にしてください。

6.
過去の質問全文をknowledge_queryとして
そのままコピーしないでください。

7.
assistantの過去回答をknowledge_queryとして
そのままコピーしないでください。

8.
資料に存在するかどうかを
knowledge_queryの段階で判定しないでください。

9.
Java研修の範囲外かどうかを
knowledge_queryの段階で判定しないでください。

10.
HTML、CSS、JavaScript、SQLなど、
RAGに存在する可能性がある技術については、
単に一般的な研修範囲外という理由だけで
除外しないでください。

11.
現在の質問に明確な知識トピックがある場合は、
過去の会話より現在の質問を優先してください。

==================================================
【knowledge_queryの作り方】
==================================================

質問:
「継承とは何ですか？」

knowledge_query:
「継承」

--------------------------------------------

質問:
「継承のサンプルコードを出してください。」

knowledge_query:
「継承」

--------------------------------------------

質問:
「継承のサンプルコードをフローチャートで
表すことはできますか？」

knowledge_query:
「継承」

--------------------------------------------

質問:
「基本データ型にはどのようなものがあるか。」

knowledge_query:
「基本データ型」

--------------------------------------------

会話:
「基本データ型にはどのようなものがあるか。」

現在:
「よく使用するもの上位3つに対して
サンプルコードを出力してください。」

knowledge_query:
「基本データ型」

--------------------------------------------

会話:
「継承とは何ですか？」

現在:
「それをフローチャートで表してください。」

knowledge_query:
「継承」

--------------------------------------------

質問:
「HTMLとは？」

knowledge_query:
「HTML」

--------------------------------------------

質問:
「HTMLとCSSの違いを教えてください。」

knowledge_query:
「HTMLとCSS」

==================================================
【複数の知識トピック】
==================================================

現在の質問に複数の知識トピックが明示されている場合は、
検索に必要な範囲で両方を保持してください。

例えば、

「継承とポリモーフィズムの違いを説明してください。」

の場合、

knowledge_query:
「継承とポリモーフィズム」

response_format:
「COMPARE」

としてください。

ただし、回答形式を表す語を
knowledge_queryへ追加してはいけません。

==================================================
【response_format】
==================================================

以下から必ず1つだけ選択してください。

{format_list}

判断基準:

通常の説明
→ EXPLAIN

サンプルコード・コード例
→ CODE

2つ以上の対象の違い・比較
→ COMPARE

手順・順番・処理の流れ
→ STEP_BY_STEP

フローチャート・図・構造図
→ DIAGRAM

小テスト・問題・クイズ
→ QUIZ

エラー・バグ・原因調査・デバッグ
→ DEBUG

要点整理・短いまとめ
→ SUMMARY

具体例・例を挙げる
→ EXAMPLE

==================================================
【回答形式とknowledge_queryを混同しない】
==================================================

例えば、

質問:
「継承のサンプルコードをフローチャートで
表すことはできますか？」

正しい出力:

knowledge_query:
「継承」

response_format:
「DIAGRAM」

です。

「継承 サンプルコード フローチャート」

をknowledge_queryにしてはいけません。

==================================================
【重要】
==================================================

knowledge_queryでは、
「何について答えるのか」を残してください。

response_formatでは、
「どのように答えるのか」を指定してください。

この2つを混同しないでください。

また、資料に存在するかどうかは
ここでは判定しないでください。

==================================================
【出力形式】
==================================================

JSONのみを出力してください。

Markdownや説明文は不要です。

{{
  "knowledge_query": "...",
  "response_format": "..."
}}
"""

    # ======================================================
    # JSON抽出
    # ======================================================

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

            logger.warning(
                "Failed to parse Query Analysis JSON."
            )

            return None

        if not isinstance(
            data,
            dict
        ):
            return None

        return data

    # ======================================================
    # knowledge_query後処理
    # ======================================================
    #
    # LLMが回答形式を混ぜた場合だけ最低限除去する。
    #
    # ここで質問全体を加工してはいけない。
    #
    # ======================================================

    def _clean_knowledge_query(
        self,
        knowledge_query: str,
        fallback_query: str
    ) -> str:

        value = str(
            knowledge_query or ""
        ).strip()

        if not value:
            return fallback_query

        # --------------------------------------------------
        # 回答形式由来のノイズのみ除去
        # --------------------------------------------------

        for pattern in self.FORMAT_NOISE_PATTERNS:

            value = re.sub(
                pattern,
                "",
                value,
                flags=re.IGNORECASE
            )

        # --------------------------------------------------
        # 連続空白を整理
        # --------------------------------------------------

        value = re.sub(
            r"\s+",
            " ",
            value
        ).strip()

        # --------------------------------------------------
        # 文末記号のみ除去
        # --------------------------------------------------

        value = value.strip(
            "、。！？!?：: "
        )

        if not value:
            return fallback_query

        return value

    # ======================================================
    # response_format正規化
    # ======================================================

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

    # ======================================================
    # LLM応答解析
    # ======================================================

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

    # ======================================================
    # LLM失敗時のローカルフォールバック
    # ======================================================
    #
    # 指示語を含む質問の場合、
    # 直前の質問をそのまま使う。
    #
    # 完全な意味解析はLLMに任せる。
    #
    # ======================================================

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

        previous_question = (
            previous_user_questions[-1]
        )

        logger.warning(
            "Using previous user question as "
            "fallback knowledge query: %s",
            previous_question
        )

        return previous_question

    # ======================================================
    # 分析エントリポイント
    # ======================================================

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