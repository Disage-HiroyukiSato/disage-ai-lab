from pydantic import BaseModel

from app.models.retrieval_item import RetrievalItem


class RetrievalResult(BaseModel):

    query: str

    total: int

    elapsed_ms: int

    items: list[RetrievalItem]