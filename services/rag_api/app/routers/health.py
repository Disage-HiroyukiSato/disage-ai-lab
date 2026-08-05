from fastapi import APIRouter

router = APIRouter(
    prefix="",
    tags=["Health"]
)


@router.get("/health")
async def health():

    return {

        "status": "ok",

        "service": "disage-rag-api",

        "version": "1.0.0"

    }