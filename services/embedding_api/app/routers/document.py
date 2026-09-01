import logging

from fastapi import APIRouter
from fastapi import HTTPException

from pydantic import BaseModel
from pydantic import Field

from app.config import settings

from app.services.ingestion.embedding_service import (
    embedding_service
)

from app.services.infra.cache_service import (
    cache_service
)


logger = logging.getLogger(__name__)


router = APIRouter(

    prefix="/documents",

    tags=[
        "Documents"
    ]

)


class DocumentRequest(BaseModel):

    # ======================================================
    # Document
    # ======================================================

    document_id: str

    title: str = ""

    category: str = "General"

    keywords: str = ""

    # ======================================================
    # Phase15 : Java教材PDF RAG化
    # ======================================================

    chapter: str = ""

    section: str = ""

    language: str = ""

    # ======================================================
    # Page Reference
    # ======================================================
    #
    # 原資料上のページ情報。
    #
    # 例：
    #     "p.12"
    #     "12"
    #     "12-13"
    #
    # 正式なmetadataキーは
    #
    #     page_reference
    #
    # とする。
    #
    # この値はEmbeddingService -> ChunkServiceを経由して
    # 各Chunkのmetadataへ引き継がれる。
    #
    # ======================================================

    page_reference: str | None = None

    # ======================================================
    # Phase16 : 複数コレクション対応
    # ======================================================
    #
    # 登録先コレクションを選択する。
    #
    # 未指定時はsettings.chroma_collectionへ登録する。
    #
    # 例：
    #
    #     java_training
    #     instructor_ops
    #
    # ======================================================

    collection: str = ""

    # ======================================================
    # Document Text
    # ======================================================

    text: str = Field(

        min_length=1,

        description=(
            "RAGへ登録するテキスト"
        )

    )


@router.post("")
def register(
    request: DocumentRequest
):

    logger.info(
        "Register document "
        "(document_id=%s, collection=%s, page=%s)",

        request.document_id,

        request.collection or "(default)",

        request.page_reference or "(none)"

    )

    # ======================================================
    # Metadata
    # ======================================================
    #
    # RAG登録時のメタデータをここで一元的に構築する。
    #
    # page_referenceについては、
    # Noneの場合はmetadataへ無理に登録しない。
    #
    # ======================================================

    metadata = {

        "title": request.title,

        "category": request.category,

        "keywords": request.keywords,

        "chapter": request.chapter,

        "section": request.section,

        "language": request.language

    }

    if request.page_reference is not None:

        metadata[
            "page_reference"
        ] = request.page_reference

    # ======================================================
    # Register
    # ======================================================

    try:

        chunk_count = (
            embedding_service.register(

                document_id=request.document_id,

                text=request.text,

                metadata=metadata,

                collection_name=(

                    request.collection

                    or None

                )

            )
        )

        logger.info(

            "Document registered "
            "(document_id=%s, chunks=%d, "
            "page=%s)",

            request.document_id,

            chunk_count,

            request.page_reference or "(none)"

        )

        # ==================================================
        # Search Cache : 無効化
        # ==================================================
        #
        # 新しい文書が登録された場合、
        # 既存キャッシュには新文書が反映されないため、
        # 登録成功後に検索キャッシュをクリアする。
        #
        # ==================================================

        if settings.enable_search_cache:

            cleared = (
                cache_service.clear_all()
            )

            logger.info(

                "Search cache invalidated : %d keys",

                cleared

            )

        # ==================================================
        # Response
        # ==================================================

        return {

            "success": True,

            "document_id": (
                request.document_id
            ),

            "collection": (

                request.collection

                or settings.chroma_collection

            ),

            "chunks": chunk_count,

            "page_reference": (
                request.page_reference
            )

        }

    except Exception as ex:

        logger.exception(

            "Document registration failed : %s",

            request.document_id

        )

        raise HTTPException(

            status_code=500,

            detail={

                "success": False,

                "message": str(ex)

            }

        )