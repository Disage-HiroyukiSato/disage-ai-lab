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