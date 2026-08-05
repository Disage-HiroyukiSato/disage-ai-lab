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


@router.post(

    "",

    response_model=QueryResponse

)

async def query(

    request: QueryRequest

):

    result = query_service.ask(

        request.question,

        request.limit

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