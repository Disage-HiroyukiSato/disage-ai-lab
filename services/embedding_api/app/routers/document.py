import logging

from fastapi import APIRouter
from fastapi import HTTPException

from pydantic import BaseModel

from app.config import settings
from app.services.embedding_service import embedding_service
from app.services.cache_service import cache_service

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

        #
        # Search Cache : 無効化
        #
        # 新しい文書が登録されると、既存の検索キャッシュは
        # 古い検索結果（新文書を含まない結果）を返し続けて
        # しまうため、登録のたびに検索キャッシュ全体を
        # クリアする。
        #
        # TTLによる自然失効に加えて、即時性が必要なため
        # 明示的にクリアする。
        #

        if settings.enable_search_cache:

            cleared = cache_service.clear_all()

            logger.info(

                "Search cache invalidated : %d keys",

                cleared

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