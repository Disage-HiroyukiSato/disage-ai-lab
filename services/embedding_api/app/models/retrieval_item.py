from typing import Any

from pydantic import BaseModel
from pydantic import Field


class RetrievalItem(BaseModel):

    document: str

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    distance: float

    score: float = 0.0