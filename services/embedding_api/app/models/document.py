from pydantic import BaseModel


class DocumentChunk(BaseModel):

    chunk_id: str

    document_id: str

    chunk_no: int

    text: str

    metadata: dict

    @property
    def title(self):

        return self.metadata.get(

            "title",

            ""

        )

    @property
    def category(self):

        return self.metadata.get(

            "category",

            ""

        )

    @property
    def keywords(self):

        return self.metadata.get(

            "keywords",

            ""

        )

    #
    # Phase15 : Java教材PDF RAG化
    #
    # chapter / section は登録時にAPI経由で
    # 人が自由記述文字列として指定する。
    #

    @property
    def chapter(self):

        return self.metadata.get(

            "chapter",

            ""

        )

    @property
    def section(self):

        return self.metadata.get(

            "section",

            ""

        )

    #
    # content_type は chunk_service 側で
    # コードブロック検出ロジックにより自動判定される。
    #
    # "code" | "text"
    #

    @property
    def content_type(self):

        return self.metadata.get(

            "content_type",

            "text"

        )

    #
    # language は content_type="code" の場合のみ
    # 意味を持つ。未指定時は空文字列。
    #

    @property
    def language(self):

        return self.metadata.get(

            "language",

            ""

        )