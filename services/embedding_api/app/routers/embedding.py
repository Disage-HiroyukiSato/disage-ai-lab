from fastapi import APIRouter
from fastapi import HTTPException

from pydantic import BaseModel

from app.services.embedding_service import embedding_service


router = APIRouter(

    prefix="/embedding",

    tags=[

        "Embedding"

    ]

)


class EmbeddingRequest(BaseModel):

    text: str


@router.post("")

async def embedding(

    request: EmbeddingRequest

):

    try:

        vector = embedding_service.embedding(

            request.text

        )

        return {

            "success": True,

            "dimension": len(vector),

            "embedding": vector

        }

    except Exception as ex:

        raise HTTPException(

            status_code=500,

            detail={

                "success": False,

                "message": str(ex)

            }

        )