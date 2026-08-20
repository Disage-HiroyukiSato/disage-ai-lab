from pydantic import BaseModel


class QueryDocumentResponse(BaseModel):

    document: str

    score: float

    distance: float

    page: str | None = None

    metadata: dict