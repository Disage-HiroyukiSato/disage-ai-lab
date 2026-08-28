from fastapi import APIRouter

from app.models.retrieval_request import RetrievalRequest
from app.services.retrieval.retrieval_service import retrieval_service

router = APIRouter(

    prefix="/retrieval",

    tags=[

        "Retrieval"

    ]

)


@router.post("")

async def retrieval(

    request: RetrievalRequest

):

    result = retrieval_service.search(

        question=request.question,

        limit=request.limit,

        document_id=request.document_id,

        category=request.category,

        title=request.title,

        keywords=request.keywords

    )

    return {

        "query": result.query,

        "total": result.total,

        "elapsed_ms": result.elapsed_ms,

        "items": [

            {

                "document": item.document,

                "score": item.score,

                "distance": item.distance,

                "metadata": item.metadata

            }

            for item in result.items

        ]

    }