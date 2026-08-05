from pydantic import BaseModel


class EmbeddingRequest(BaseModel):

    document_id: str

    text: str


class EmbeddingResponse(BaseModel):

    status: str

    document_id: str