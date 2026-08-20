from typing import Any

from pydantic import BaseModel
from pydantic import Field


class RetrievalItem(BaseModel):

    # ======================================================
    # Retrieved document
    # ======================================================

    document: str

    # ======================================================
    # Metadata
    # ======================================================
    #
    # document_id
    # chunk_no
    # page_reference
    # title
    #
    # など、RAG登録時に付与された情報を保持する。
    #
    # ページ情報については metadata を正とする。
    #
    # ======================================================

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    # ======================================================
    # Retrieval score
    # ======================================================

    distance: float

    score: float = 0.0

    # ======================================================
    # Hybrid Search
    # ======================================================
    #
    # BM25 score と Vector類似度を
    # 正規化・合成した値。
    #
    # ENABLE_HYBRID_SEARCH=false の場合は 0.0 のまま。
    #
    # Reranker実行後に上書きされる score とは
    # 役割が異なるため、別フィールドとして保持する。
    #
    # ======================================================

    hybrid_score: float = 0.0

    # ======================================================
    # Hybrid Search : 内訳スコア
    # ======================================================
    #
    # Phase14-6 Search Log Analysisで、
    # Vector / BM25それぞれの寄与度を確認するために保持。
    #
    # ======================================================

    bm25_raw_score: float = 0.0

    vector_similarity: float = 0.0

    # ======================================================
    # Source information
    # ======================================================
    #
    # 以下は metadata から取得する。
    #
    # 明示的なフィールドとして保存するのではなく、
    # metadataを正とすることで、
    #
    # Chroma
    #   ↓
    # RetrievalItem
    #
    # の間で情報が二重管理されることを防ぐ。
    #
    # ======================================================

    @property
    def document_id(self) -> str:
        """
        ドキュメントIDを取得する。
        """

        value = self.metadata.get(
            "document_id"
        )

        if value is None:
            return ""

        return str(value)

    @property
    def chunk_no(self) -> str:
        """
        チャンク番号を取得する。
        """

        value = self.metadata.get(
            "chunk_no"
        )

        if value is None:
            return ""

        return str(value)

    @property
    def title(self) -> str:
        """
        ドキュメントタイトルを取得する。
        """

        value = (
            self.metadata.get("title")
            or self.metadata.get("document_title")
            or self.metadata.get("source_title")
        )

        if value is None:
            return ""

        return str(value)

    @property
    def page_reference(self) -> str | None:
        """
        原資料上のページ情報を取得する。

        正式なキーは page_reference を想定する。

        既存データとの互換性を考慮し、
        page / page_number もフォールバックとして扱う。
        """

        value = (
            self.metadata.get("page_reference")
            or self.metadata.get("page")
            or self.metadata.get("page_number")
        )

        if value is None:
            return None

        return str(value)

    @property
    def source_reference(self) -> str:
        """
        回答根拠として表示可能な資料参照情報を返す。

        ページが存在する場合：
            「p.12」

        ページが存在しない場合：
            空文字
        """

        if self.page_reference:
            return self.page_reference

        return ""

    def has_page_reference(self) -> bool:
        """
        ページ情報を保持しているか判定する。
        """

        return bool(
            self.page_reference
        )