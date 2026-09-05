import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.routers.query import QueryRequest
from app.services.query_stream_service import query_stream_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/query",
    tags=["Query"],
)


def _encode_event(event: dict) -> bytes:
    return (
        json.dumps(
            event,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


@router.post("/stream")
def query_stream(request: QueryRequest):

    def generate():
        try:
            for event in query_stream_service.stream(
                question=request.question,
                limit=request.limit,
                student_id=request.student_id,
                session_id=request.session_id,
            ):
                yield _encode_event(event)
        except Exception as ex:
            logger.exception("Streaming query failed")
            yield _encode_event({
                "type": "error",
                "message": "回答処理中にエラーが発生しました。",
                "detail": str(ex),
            })

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
