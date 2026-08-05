from fastapi import APIRouter
from fastapi import HTTPException

from app.services.chroma_service import chroma_service

router = APIRouter(

    tags=[

        "Health"

    ]

)


@router.get("/health")

async def health():

    return {

        "success": True,

        "status": "alive"

    }


@router.get("/ready")

async def ready():

    try:

        count = chroma_service.count()

        return {

            "success": True,

            "status": "ready",

            "documents": count

        }

    except Exception as ex:

        raise HTTPException(

            status_code=503,

            detail={

                "success": False,

                "message": str(ex)

            }

        )