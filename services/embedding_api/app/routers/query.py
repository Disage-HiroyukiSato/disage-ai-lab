from fastapi import APIRouter

from pydantic import BaseModel

from app.config import settings

from app.models.query_response import QueryResponse
from app.models.query_document_response import QueryDocumentResponse

from app.services.query_service import query_service


router = APIRouter(

    prefix="/query",

    tags=["Query"]

)


class QueryRequest(BaseModel):

    question: str

    limit: int = settings.default_limit

    #
    # Phase17 : 研修用AIアシスタント
    #
    # student_id : 受講生ID。指定するとstudent_progressを
    #              参照し、現在の学習chapterで検索結果を
    #              ブーストする。未指定時はブースト無効。
    #
    # session_id : 会話セッションID。マルチターン対話の
    #              履歴をひも付けるためのキー。未指定時は
    #              履歴の保存・参照ともに行わない
    #              （単発Q&Aとして動作、既存動作と同じ）。
    #

    student_id: str | None = None

    session_id: str | None = None


@router.post(

    "",

    response_model=QueryResponse

)

async def query(

    request: QueryRequest

):

    result = query_service.ask(

        request.question,

        request.limit,

        student_id=request.student_id,

        session_id=request.session_id

    )

    return QueryResponse(

        answer=result["answer"],

        elapsed_ms=result["elapsed_ms"],

        retrieved_count=result["retrieved_count"],

        documents=[

            QueryDocumentResponse(

                document=item.document,

                score=item.score,

                distance=item.distance,

                metadata=item.metadata

            )

            for item in result["documents"]

        ]

    )