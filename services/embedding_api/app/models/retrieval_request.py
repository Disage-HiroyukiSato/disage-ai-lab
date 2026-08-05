from pydantic import BaseModel


class RetrievalRequest(BaseModel):

    question: str

    limit: int = 5

    document_id: str | None = None

    category: str | None = None

    title: str | None = None

    keywords: str | None = None