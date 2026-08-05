from pydantic import BaseModel
from typing import List, Optional


class Message(BaseModel):

    role: str

    content: str


class ChatCompletionRequest(BaseModel):

    model: Optional[str] = None

    messages: List[Message]

    temperature: Optional[float] = 0.2

    top_p: Optional[float] = 0.9

    stream: Optional[bool] = False


class Choice(BaseModel):

    index: int

    message: Message

    finish_reason: str


class Usage(BaseModel):

    prompt_tokens: int

    completion_tokens: int

    total_tokens: int


class ChatCompletionResponse(BaseModel):

    id: str

    object: str

    created: int

    model: str

    choices: List[Choice]

    usage: Usage