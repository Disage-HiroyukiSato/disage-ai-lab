import logging

from app.models.retrieval_item import RetrievalItem
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class AnswerabilityGateService:

    #
    # ------------------------------------------------------
    # Answerability Gate
    # ------------------------------------------------------
    #
    # Reranker通過後の上位資料であっても、単語の一致だけで
    # min_rerank_scoreを超えてしまうケースがある
    # （例: 「今日の天気は？」に対し、コード例中の
    # `<%= weather %>` がヒットする）。
    #
    # 最終的にLLMへ渡す前に、軽量LLM（llama-rewriter）で
    # 「この質問に、これらの資料は実際に答えているか」を
    # Yes/No判定する最終防衛ラインとして機能する。
    #
    # 対象は上位数件（TOP_N）をまとめて渡し、
    # どれか1件でも答えられればYesとする。
    #
    # 判定失敗（タイムアウト等）時はNo扱いとし、
    # 安全側（無理に回答しない）に倒す。
    #

    #
    # Gateに渡す候補数。
    #
    # rerank_relaxed側で目次チャンクを除外するため、
    # フィルタ後も十分な判断材料が残るよう、
    # 単純なスコア上位3件よりやや広めに5件とする。
    #
    # UI操作手順・コード断片・演習の出力例等、目次以外の
    # ノイズはルールベースでは除外しきれないため
    # （正当な内容との境界が曖昧で誤検出リスクが高い）、
    # 候補数を広げることでノイズが多少混ざっても
    # 本文チャンクがGateの目に入りやすくする。
    #

    TOP_N = 5

    #
    # LLMの応答を解析してYesと判断する接頭語。
    #
    # 軽量モデルの応答揺れを吸収するため、
    # 大文字小文字を無視し、複数の表現を許容する。
    #

    YES_PREFIXES = (

        "yes",

        "はい"

    )

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
以下の資料が、質問に実際に答えているかどうかを判定してください。

# 判定基準

・資料の中に、質問への直接的な回答が明確に含まれている場合のみ「Yes」。
・資料中に質問と同じ単語が含まれているだけで、
  質問の意図には答えていない場合は「No」。
・資料がプログラムのコード例・サンプルコードであり、
  実際のデータや実行結果を示すものではない場合、
  それを根拠に質問へ答えることはできないため「No」。
・少しでも判断に迷う場合は「No」としてください。

# 資料

{joined_contexts}

# 質問

{question}

# 出力形式

"Yes" または "No" の一語のみを出力してください。
理由や説明は不要です。

# 判定結果
"""

    #
    # ------------------------------------------------------
    # 判定
    # ------------------------------------------------------
    #
    # 戻り値 : True の場合、資料は質問に回答可能と判定
    #

    def is_answerable(

        self,

        question: str,

        items: list[RetrievalItem]

    ) -> bool:

        if not items:

            return False

        top_items = items[:self.TOP_N]

        contexts = [

            item.document

            for item in top_items

        ]

        #
        # デバッグ : Gateに実際に渡される資料を全文ログに残す
        # ------------------------------------------------------
        #
        # 「Gateの判定結果」だけでは、そもそも渡された資料の
        # 中身が質問に関連しているのかを確認できないため、
        # 候補ごとにdocument_id・chunk_no・スコア・全文を
        # ログへ出力する。
        #

        logger.info(

            "----------------------------------------"

        )

        logger.info(

            "Answerability Gate Candidates (raw)"

        )

        logger.info(

            "----------------------------------------"

        )

        for index, item in enumerate(

            top_items,

            start=1

        ):

            metadata = item.metadata or {}

            logger.info(

                "[Gate候補 %d] document_id=%s chunk_no=%s "
                "score=%.4f distance=%.4f",

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

        prompt = self._build_prompt(

            question,

            contexts

        )

        try:

            response = llm_service.ask_rewriter(

                prompt

            )

        except Exception:

            logger.exception(

                "Answerability Gate judgement failed. "
                "Falling back to No (deny answering)."

            )

            return False

        normalized = response.strip().lower()

        result = normalized.startswith(

            self.YES_PREFIXES

        )

        logger.info(

            "----------------------------------------"

        )

        logger.info(

            "Answerability Gate Raw Response"

        )

        logger.info(

            "----------------------------------------"

        )

        logger.info(

            "%s",

            response.strip()

        )

        logger.info(

            "----------------------------------------"

        )

        logger.info(

            "Answerability Gate : question=%s "
            "candidates=%d parsed_result=%s -> answerable=%s",

            question,

            len(top_items),

            normalized[:50],

            result

        )

        return result


answerability_gate_service = AnswerabilityGateService()