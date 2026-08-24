import logging

from app.models.answerability import (
    AnswerabilityResult,
    AnswerabilityStatus
)

from app.models.retrieval_item import (
    RetrievalItem
)

from app.services.llm_service import (
    llm_service
)


logger = logging.getLogger(__name__)


class AnswerabilityGateService:

    # ======================================================
    # Answerability Gate
    # ======================================================
    #
    # Rerankerのスコアだけでは、
    # 「単語は一致しているが質問には答えていない」
    # というケースを完全には除去できない。
    #
    # そこで軽量LLMを使用し、
    #
    # FULL
    # PARTIAL
    # NONE
    #
    # の3段階で判定する。
    #
    # ======================================================

    TOP_N = 5

    # ======================================================
    # Prompt
    # ======================================================

    def _build_prompt(
        self,
        question: str,
        contexts: list[str]
    ) -> str:

        joined_contexts = "\n\n".join(

            f"[資料{index}]\n{context}"

            for index, context in enumerate(
                contexts,
                start=1
            )

        )

        return f"""
あなたはRAG検索結果の「回答可能性」を判定する
アシスタントです。

以下の資料と質問を比較し、
資料が質問に対してどの程度回答できるかを判定してください。

# 判定

次の3つのいずれかを選択してください。

FULL
資料に、質問への回答に必要な情報が十分に存在する。

PARTIAL
資料に質問に関連する有用な情報が存在するが、
質問の一部の条件、指定、順位、具体値などが
資料から確認できない。

NONE
資料に質問へ回答するための有用な情報が
ほとんど存在しない。

# 重要な判定ルール

・質問と資料に同じ単語があるだけではFULLにしない。

・資料に関連する情報が存在する場合、
質問の一部が資料にないだけでNONEにしてはいけない。

・質問が複数の条件を含む場合、
条件ごとに資料で確認できるか判断してください。

・例えば、

質問：
「基本データ型のうち、よく使用する上位3つについて
サンプルコードを出してください。」

資料：
「基本データ型にはboolean、byte、short、int、
long、float、doubleがある。」

この場合、

基本データ型の一覧
→ 資料から確認できる

よく使用する上位3つという順位
→ 資料から確認できない

サンプルコード
→ 基本データ型という関連情報があるため生成可能

したがって判定はPARTIALです。

・資料にサンプルコードそのものがなくても、
資料に対象となる概念・仕様・構文などがある場合は、
関連する回答を生成できる可能性があるため、
サンプルコード要求だけを理由にNONEにしないでください。

・HTML、CSS、SQLなどについても、
RAG資料に説明が存在する場合は、
「Java研修の範囲外」という理由だけでNONEにしないでください。

・資料から確認できない部分があっても、
関連情報が存在する場合はPARTIALとしてください。

# 資料

{joined_contexts}

# 質問

{question}

# 出力形式

必ず次のJSON形式だけを出力してください。

{{
  "status": "FULL",
  "reason": "資料に質問への回答に必要な情報があります。"
}}

statusにはFULL、PARTIAL、NONEのいずれかを指定してください。

reasonには、日本語で短い判定理由を記載してください。

JSON以外の文章は出力しないでください。
"""

    # ======================================================
    # Response Parse
    # ======================================================

    def _parse_response(
        self,
        response: str
    ) -> AnswerabilityResult:

        import json

        if not response:

            return AnswerabilityResult(

                status=AnswerabilityStatus.NONE,

                reason="Answerability Gateの応答が空でした。"

            )

        text = response.strip()

        # --------------------------------------------------
        # JSON部分だけを抽出
        # --------------------------------------------------

        start = text.find("{")

        end = text.rfind("}")

        if start >= 0 and end > start:

            text = text[
                start:end + 1
            ]

        try:

            data = json.loads(
                text
            )

            status_text = str(
                data.get(
                    "status",
                    ""
                )
            ).strip().upper()

            reason = str(
                data.get(
                    "reason",
                    ""
                )
            ).strip()

            if status_text == "FULL":

                return AnswerabilityResult(

                    status=AnswerabilityStatus.FULL,

                    reason=reason
                    or "資料から質問への回答が確認できます。"

                )

            if status_text == "PARTIAL":

                return AnswerabilityResult(

                    status=AnswerabilityStatus.PARTIAL,

                    reason=reason
                    or "資料に関連情報がありますが、一部を確認できません。"

                )

            if status_text == "NONE":

                return AnswerabilityResult(

                    status=AnswerabilityStatus.NONE,

                    reason=reason
                    or "資料から質問への回答に必要な情報を確認できません。"

                )

        except Exception:

            logger.warning(
                "Answerability Gate JSON parse failed: %s",
                response
            )

        # --------------------------------------------------
        # JSON解析失敗時のフォールバック
        # --------------------------------------------------

        normalized = (
            response
            .strip()
            .lower()
        )

        if normalized.startswith(
            "full"
        ) or normalized.startswith(
            "yes"
        ) or normalized.startswith(
            "はい"
        ):

            return AnswerabilityResult(

                status=AnswerabilityStatus.FULL,

                reason="Answerability Gateが肯定判定しました。"

            )

        if normalized.startswith(
            "partial"
        ):

            return AnswerabilityResult(

                status=AnswerabilityStatus.PARTIAL,

                reason="Answerability Gateが部分的な回答可能性を判定しました。"

            )

        return AnswerabilityResult(

            status=AnswerabilityStatus.NONE,

            reason="Answerability Gateの判定を解析できませんでした。"

        )

    # ======================================================
    # Candidate Logging
    # ======================================================

    def _log_candidates(
        self,
        items: list[RetrievalItem]
    ):

        logger.info(
            "----------------------------------------"
        )

        logger.info(
            "Answerability Gate Candidates"
        )

        logger.info(
            "----------------------------------------"
        )

        for index, item in enumerate(
            items,
            start=1
        ):

            metadata = (
                item.metadata
                or {}
            )

            logger.info(

                "[Gate候補 %d] "
                "document_id=%s "
                "chunk_no=%s "
                "score=%.4f "
                "distance=%.4f",

                index,

                metadata.get(
                    "document_id",
                    ""
                ),

                metadata.get(
                    "chunk_no",
                    ""
                ),

                item.score,

                item.distance

            )

            logger.info(

                "[Gate候補 %d 全文] %s",

                index,

                item.document

            )

        logger.info(
            "----------------------------------------"
        )

    # ======================================================
    # Assess
    # ======================================================

    def assess(
        self,
        question: str,
        items: list[RetrievalItem]
    ) -> AnswerabilityResult:

        if not items:

            return AnswerabilityResult(

                status=AnswerabilityStatus.NONE,

                reason="RAG検索結果がありません。"

            )

        top_items = items[
            :self.TOP_N
        ]

        self._log_candidates(
            top_items
        )

        contexts = [

            item.document

            for item in top_items

        ]

        prompt = self._build_prompt(

            question,

            contexts

        )

        try:

            response = (
                llm_service.ask_rewriter(
                    prompt
                )
            )

        except Exception:

            logger.exception(

                "Answerability Gate judgement failed."

            )

            return AnswerabilityResult(

                status=AnswerabilityStatus.NONE,

                reason=(
                    "Answerability Gateの判定に失敗しました。"
                )

            )

        result = self._parse_response(
            response
        )

        logger.info(
            "----------------------------------------"
        )

        logger.info(
            "Answerability Gate Result"
        )

        logger.info(
            "----------------------------------------"
        )

        logger.info(
            "Question : %s",
            question
        )

        logger.info(
            "Raw Response : %s",
            response.strip()
        )

        logger.info(
            "Status : %s",
            result.status.value
        )

        logger.info(
            "Reason : %s",
            result.reason
        )

        logger.info(
            "----------------------------------------"
        )

        return result

    # ======================================================
    # Backward Compatibility
    # ======================================================
    #
    # 既存コードがis_answerable()を呼んでいる場合に備えて、
    # メソッド自体は残す。
    #
    # ただし新規コードではassess()を使用する。
    #
    # ======================================================

    def is_answerable(
        self,
        question: str,
        items: list[RetrievalItem]
    ) -> bool:

        result = self.assess(
            question,
            items
        )

        return (
            result.status
            != AnswerabilityStatus.NONE
        )


answerability_gate_service = (
    AnswerabilityGateService()
)