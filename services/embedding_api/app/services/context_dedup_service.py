import logging
import re

from app.models.retrieval_item import RetrievalItem

logger = logging.getLogger(__name__)


class ContextDedupService:

    #
    # ------------------------------------------------------
    # 最終Context重複除去
    # ------------------------------------------------------
    #
    # RAG検索結果そのものには手を加えず、
    # 最終的にLLMへ渡すContextだけを対象とする。
    #
    # Phase14の検索・Reranker・Answerability Gateの結果を
    # 変更しないことが目的。
    #
    # 現段階では「完全一致」の重複だけを除去する。
    #
    # 類似度による重複除去は意図的に行わない。
    #
    # 理由：
    #
    #   類似しているが異なる説明を誤って削除すると、
    #   RAGの情報量を減らしてしまう可能性がある。
    #
    # まずは完全一致による安全な重複除去だけを行い、
    # 実際の検索ログを確認したうえで、必要なら
    # 次の段階として類似度ベースの重複除去を検討する。
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

            normalized_document = self._normalize(
                item.document
            )

            #
            # documentが空の場合はContextとして意味がないため、
            # 最終Contextから除外する。
            #

            if not normalized_document:

                logger.debug(
                    "Empty context removed : metadata=%s",
                    item.metadata
                )

                removed_count += 1

                continue

            #
            # 完全一致するdocumentを除外する。
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

    # ------------------------------------------------------
    # 正規化
    # ------------------------------------------------------
    #
    # 改行・連続空白など、表記上の違いだけを吸収する。
    #
    # 例：
    #
    #   "boolean は論理型です。"
    #
    #   "boolean   は論理型です。"
    #
    #   "boolean は\n論理型です。"
    #
    # を同一Contextとして扱う。
    #
    # ただし、文字列そのものを加工してresultへ返すことはしない。
    # 元のRetrievalItemをそのまま保持する。
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