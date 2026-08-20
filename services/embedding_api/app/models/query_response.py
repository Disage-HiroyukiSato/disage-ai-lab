from pydantic import BaseModel

from app.models.query_document_response import (
    QueryDocumentResponse
)

from app.models.query_metadata_response import (
    QueryMetadataResponse
)

from app.models.query_source_response import (
    QuerySourceResponse
)


class QueryResponse(BaseModel):

    # ======================================================
    # 回答本文
    # ======================================================

    answer: str

    # ======================================================
    # 回答の根拠
    # ======================================================

    sources: list[QuerySourceResponse] = []

    source_pages: list[str] = []

    # ======================================================
    # 従来レスポンスとの互換項目
    # ======================================================

    elapsed_ms: int = 0

    retrieved_count: int = 0

    # ======================================================
    # RAG検索結果
    # ======================================================

    documents: list[QueryDocumentResponse] = []

    # ======================================================
    # 回答判定
    # ======================================================

    answerability_status: str | None = None

    answerability_reason: str = ""

    # ======================================================
    # システム情報
    # ======================================================

    metadata: QueryMetadataResponse