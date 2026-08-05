from pydantic import BaseModel

from app.models.query_document_response import (
    QueryDocumentResponse
)


class QueryResponse(BaseModel):

    answer: str

    elapsed_ms: int

    retrieved_count: int

    documents: list[QueryDocumentResponse]