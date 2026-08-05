import logging

from fastapi import APIRouter
from fastapi import HTTPException

from pydantic import BaseModel

from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

router = APIRouter(

    prefix="/documents",

    tags=[

        "Documents"

    ]

)


class DocumentRequest(BaseModel):

    document_id: str

    title: str = ""

    category: str = "General"

    keywords: str = ""

    text: str


@router.post("")

async def register(

    request: DocumentRequest

):

    logger.info(

        "Register document"

    )

    try:

        chunk_count = embedding_service.register(

            document_id=request.document_id,

            text=request.text,

            metadata={

                "title": request.title,

                "category": request.category,

                "keywords": request.keywords

            }

        )

        logger.info(

            "Chunks : %d",

            chunk_count

        )

        return {

            "success": True,

            "document_id": request.document_id,

            "chunks": chunk_count

        }

    except Exception as ex:

        raise HTTPException(

            status_code=500,

            detail={

                "success": False,

                "message": str(ex)

            }

        )