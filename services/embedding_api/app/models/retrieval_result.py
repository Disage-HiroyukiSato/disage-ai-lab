from pydantic import BaseModel

from app.models.retrieval_item import RetrievalItem


class RetrievalResult(BaseModel):

    query: str

    total: int

    elapsed_ms: int

    items: list[RetrievalItem]

    #
    # Search Cache : Hitしたかどうか
    #
    # 検索ログ分析（Phase14-6）でCache Hit率を算出するために
    # query_service側まで伝播させる。
    #

    cache_hit: bool = False

    # ------------------------------------------------------
    # RAG回答根拠ページ
    # ------------------------------------------------------
    #
    # 検索結果itemsから抽出されたページ情報。
    #
    # これは「回答本文」ではなく、後段で
    # answer / sourcesを構築するための検索結果情報。
    #
    # 同じページが複数chunkから検索された場合は、
    # 重複を除いたページ番号を返す。
    # ------------------------------------------------------

    @property
    def source_pages(self) -> list[str]:

        pages: list[str] = []

        for item in self.items:

            reference = (
                item.page_reference
            )

            if not reference:
                continue

            if reference in pages:
                continue

            pages.append(
                reference
            )

        return pages