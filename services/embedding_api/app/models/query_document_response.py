from pydantic import BaseModel


class QueryDocumentResponse(BaseModel):

    document: str

    score: float

    distance: float

    metadata: dict