from pydantic import BaseModel, Field


class FollowUp(BaseModel):
    question: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)