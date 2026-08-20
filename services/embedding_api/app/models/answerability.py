from enum import Enum

from pydantic import BaseModel


class AnswerabilityStatus(str, Enum):

    FULL = "FULL"

    PARTIAL = "PARTIAL"

    NONE = "NONE"


class AnswerabilityResult(BaseModel):

    status: AnswerabilityStatus

    reason: str = ""