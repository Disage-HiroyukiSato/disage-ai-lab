import logging
import re

from app.models.retrieval_item import RetrievalItem


logger = logging.getLogger(__name__)


class ContextDedupService:

    # ======================================================
    # 最終Context重複除去
    # ======================================================
    #
    # RAG検索結果そのものには手を加えず、
    # 最終的にLLMへ渡すContextだけを対象とする。
    #
    # Phase14の検索・Reranker・Answerability Gateの結果を
    # 変更しないことが目的。
    #
    # ------------------------------------------------------
    # 重複判定
    # ------------------------------------------------------
    #
    # 現段階では完全一致のContextだけを重複として扱う。
    #
    # 改行・連続空白など、表記上の差だけは正規化して
    # 同一Contextとして扱う。
    #
    # 一方、
    #
    # ・類似文章
    # ・同一テーマだが内容が異なる文章
    # ・同一document内の近似chunk
    #
    # については削除しない。
    #
    # 理由：
    #
    # 類似しているという理由だけでContextを削除すると、
    # 回答に必要な情報まで失う可能性があるため。
    #
    # 類似度ベースの重複除去は、実際の検索ログを確認したうえで
    # 将来必要になった場合に別途検討する。
    #

    def deduplicate(
        self,
        items: list[RetrievalItem]
    ) -> list[RetrievalItem]:

        if not items:

            return []

        result: list[RetrievalItem] = []

        seen: set[str] = set()

        removed_count = 0

        for item in items:

            # --------------------------------------------------
            # Context本文
            # --------------------------------------------------

            normalized_document = (
                self._normalize(
                    item.document
                )
            )

            # --------------------------------------------------
            # 空Context
            # --------------------------------------------------
            #
            # documentが空の場合は、LLMへ渡すContextとして
            # 意味がないため除外する。
            #
            # RetrievalItemそのものは変更しない。
            #

            if not normalized_document:

                logger.debug(
                    "Empty context removed : metadata=%s",
                    item.metadata
                )

                removed_count += 1

                continue

            # --------------------------------------------------
            # 完全一致重複
            # --------------------------------------------------
            #
            # 正規化後のdocument本文が完全一致する場合のみ
            # 重複として扱う。
            #
            # 最初に登場したItemを残す。
            #
            # QueryServiceでは、
            #
            # reranked_items + gate_candidates
            #
            # の順で渡されるため、
            # 同じContextが存在した場合は通常のReranker結果を
            # 優先して残すことになる。
            #

            if normalized_document in seen:

                logger.info(
                    "Duplicate context removed : "
                    "metadata=%s distance=%s score=%s",
                    item.metadata,
                    item.distance,
                    item.score
                )

                removed_count += 1

                continue

            seen.add(
                normalized_document
            )

            result.append(
                item
            )

        logger.info(
            "Context deduplication completed : "
            "input=%d output=%d removed=%d",
            len(items),
            len(result),
            removed_count
        )

        return result

    # ======================================================
    # Context正規化
    # ======================================================
    #
    # 重複判定専用の正規化。
    #
    # RetrievalItem.documentそのものは変更しない。
    #
    # 例：
    #
    #   "boolean は論理型です。"
    #
    #   "boolean   は論理型です。"
    #
    #   "boolean は\n論理型です。"
    #
    # は同一Contextとして扱う。
    #
    # ただし、句読点や文字列内容そのものを変更するような
    # 強い正規化は行わない。
    #

    def _normalize(
        self,
        text: str
    ) -> str:

        if not text:

            return ""

        return re.sub(
            r"\s+",
            " ",
            text
        ).strip()


context_dedup_service = ContextDedupService()