from fastapi import APIRouter
from fastapi import HTTPException

from app.schemas.chat import ChatCompletionRequest

from app.services.llama_service import llama_service


router = APIRouter(
    prefix="/v1",
    tags=["Chat"]
)


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):

    try:

        payload = request.model_dump(exclude_none=True)

        return await llama_service.chat_completion(payload)

    except Exception as ex:

        raise HTTPException(

            status_code=500,

            detail=str(ex)

        )