from fastapi import APIRouter

from app.services.llama_service import llama_service

router = APIRouter(
    prefix="/v1",
    tags=["Models"]
)


@router.get("/models")
async def models():

    return await llama_service.models()