from typing import Any

from pydantic import BaseModel


class DocumentChunk(BaseModel):

    # ======================================================
    # Chunk identification
    # ======================================================

    chunk_id: str

    document_id: str

    chunk_no: int

    # ======================================================
    # Chunk text
    # ======================================================

    text: str

    # ======================================================
    # Metadata
    # ======================================================
    #
    # ChromaDBへ登録するmetadata。
    #
    # ページ情報を含め、検索結果として必要な情報は
    # metadataを正とする。
    #
    # ======================================================

    metadata: dict[str, Any]

    # ======================================================
    # Basic metadata
    # ======================================================

    @property
    def title(self) -> str:

        return str(
            self.metadata.get(
                "title",
                ""
            )
        )

    @property
    def category(self) -> str:

        return str(
            self.metadata.get(
                "category",
                ""
            )
        )

    @property
    def keywords(self) -> str:

        return str(
            self.metadata.get(
                "keywords",
                ""
            )
        )

    # ======================================================
    # Phase15 : Java教材PDF RAG化
    # ======================================================
    #
    # chapter / section は登録時にAPI経由で
    # 指定される自由記述文字列。
    #
    # ======================================================

    @property
    def chapter(self) -> str:

        return str(
            self.metadata.get(
                "chapter",
                ""
            )
        )

    @property
    def section(self) -> str:

        return str(
            self.metadata.get(
                "section",
                ""
            )
        )

    # ======================================================
    # Page Reference
    # ======================================================
    #
    # 原資料上のページ情報。
    #
    # 正式なmetadataキー：
    #
    #     page_reference
    #
    # 例：
    #
    #     p.10
    #     p.12
    #     p.10-11
    #
    # ======================================================

    @property
    def page_reference(self) -> str | None:

        value = (
            self.metadata.get(
                "page_reference"
            )
        )

        if value is None:

            return None

        value = str(
            value
        ).strip()

        if not value:

            return None

        return value

    # ======================================================
    # Page Reference existence
    # ======================================================

    def has_page_reference(self) -> bool:

        return (
            self.page_reference
            is not None
        )

    # ======================================================
    # Content Type
    # ======================================================
    #
    # chunk_service側で自動判定される。
    #
    #     code
    #     text
    #
    # ======================================================

    @property
    def content_type(self) -> str:

        return str(
            self.metadata.get(
                "content_type",
                "text"
            )
        )

    # ======================================================
    # Language
    # ======================================================
    #
    # content_type="code" の場合に主に使用する。
    #
    # ======================================================

    @property
    def language(self) -> str:

        return str(
            self.metadata.get(
                "language",
                ""
            )
        )