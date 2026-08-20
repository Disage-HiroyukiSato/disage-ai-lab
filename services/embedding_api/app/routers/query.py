from fastapi import APIRouter

from pydantic import BaseModel

from app.config import settings

from app.models.query_response import QueryResponse

from app.models.query_document_response import (
    QueryDocumentResponse
)

from app.models.query_source_response import (
    QuerySourceResponse
)

from app.models.query_metadata_response import (
    QueryMetadataResponse
)

from app.services.query_service import (
    query_service
)


router = APIRouter(

    prefix="/query",

    tags=["Query"]

)


class QueryRequest(BaseModel):

    question: str

    limit: int = settings.default_limit

    # ======================================================
    # Phase17 : 研修用AIアシスタント
    # ======================================================
    #
    # student_id
    #
    # 受講生ID。
    #
    # 指定された場合、
    # 現在の学習chapterを検索処理に利用する。
    #
    # ======================================================

    student_id: str | None = None

    # ======================================================
    # session_id
    # ======================================================
    #
    # 会話セッションID。
    #
    # 指定された場合、
    # 過去の会話履歴を取得・保存する。
    #
    # ======================================================

    session_id: str | None = None


@router.post(
    "",
    response_model=QueryResponse
)
async def query(
    request: QueryRequest
):

    # ======================================================
    # Query Service
    # ======================================================

    result = query_service.ask(

        request.question,

        request.limit,

        student_id=request.student_id,

        session_id=request.session_id

    )

    # ======================================================
    # Documents
    # ======================================================

    documents = []

    for item in result.get(
        "documents",
        []
    ):

        metadata = (
            item.metadata
            if item.metadata
            else {}
        )

        page = (
            metadata.get("page")
            or metadata.get("page_number")
            or metadata.get("page_reference")
        )

        documents.append(

            QueryDocumentResponse(

                document=item.document,

                score=item.score,

                distance=item.distance,

                page=page,

                metadata=metadata

            )

        )

    # ======================================================
    # Sources
    # ======================================================

    sources = []

    for source in result.get(
        "sources",
        []
    ):

        sources.append(

            QuerySourceResponse(

                document_id=str(
                    source.get(
                        "document_id",
                        ""
                    )
                ),

                chunk_no=str(
                    source.get(
                        "chunk_no",
                        ""
                    )
                ),

                title=str(
                    source.get(
                        "title",
                        ""
                    )
                ),

                page=source.get(
                    "page"
                )

            )

        )

    # ======================================================
    # Metadata
    # ======================================================

    result_metadata = (
        result.get(
            "metadata",
            {}
        )
    )

    metadata = QueryMetadataResponse(

        query_analysis_elapsed_ms=
            result_metadata.get(
                "query_analysis_elapsed_ms",
                0
            ),

        retrieval_elapsed_ms=
            result_metadata.get(
                "retrieval_elapsed_ms",
                0
            ),

        answerability_elapsed_ms=
            result_metadata.get(
                "answerability_elapsed_ms",
                0
            ),

        llm_elapsed_ms=
            result_metadata.get(
                "llm_elapsed_ms",
                0
            ),

        total_elapsed_ms=
            result_metadata.get(
                "total_elapsed_ms",
                result.get(
                    "elapsed_ms",
                    0
                )
            ),

        cache_hit=
            result_metadata.get(
                "cache_hit",
                False
            ),

        fallback_used=
            result_metadata.get(
                "fallback_used",
                False
            ),

        retrieved_count=
            result_metadata.get(
                "retrieved_count",
                result.get(
                    "retrieved_count",
                    0
                )
            ),

        gate_candidate_count=
            result_metadata.get(
                "gate_candidate_count",
                0
            ),

        final_context_count=
            result_metadata.get(
                "final_context_count",
                0
            )

    )

    # ======================================================
    # Response
    # ======================================================

    return QueryResponse(

        # --------------------------------------------------
        # 回答本文
        # --------------------------------------------------

        answer=result.get(
            "answer",
            ""
        ),

        # --------------------------------------------------
        # 根拠
        # --------------------------------------------------

        sources=sources,

        source_pages=result.get(
            "source_pages",
            []
        ),

        # --------------------------------------------------
        # 互換項目
        # --------------------------------------------------

        elapsed_ms=result.get(
            "elapsed_ms",
            metadata.total_elapsed_ms
        ),

        retrieved_count=result.get(
            "retrieved_count",
            metadata.retrieved_count
        ),

        # --------------------------------------------------
        # 検索結果
        # --------------------------------------------------

        documents=documents,

        # --------------------------------------------------
        # Answerability
        # --------------------------------------------------

        answerability_status=
            result.get(
                "answerability_status"
            ),

        answerability_reason=
            result.get(
                "answerability_reason",
                ""
            ),

        # --------------------------------------------------
        # システム情報
        # --------------------------------------------------

        metadata=metadata

    )