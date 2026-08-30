from fastapi import APIRouter

from pydantic import BaseModel

from app.config import settings

from app.models.query_response import (
    QueryResponse
)

from app.models.query_document_response import (
    QueryDocumentResponse
)

from app.models.query_source_response import (
    QuerySourceResponse
)

from app.models.query_metadata_response import (
    QueryMetadataResponse
)

from app.models.learning.follow_up import (
    FollowUp
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
    # Metadata
    # ======================================================
    #
    # 処理時間や検索件数など、
    # 回答本文とは別のシステム情報。
    #
    # QueryServiceで項目名を統一しているため、
    # ここでは変換・推測を行わず、そのまま受け取る。
    #
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
                0
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
                0
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
    # Documents
    # ======================================================
    #
    # RAG検索結果の詳細情報。
    #
    # documentsは検索結果そのものを表し、
    # sourcesとは役割を分ける。
    #
    # ======================================================

    documents = []

    for item in result.get(
        "documents",
        []
    ):

        metadata_item = (
            item.metadata
            if item.metadata
            else {}
        )

        # --------------------------------------------------
        # Page
        # --------------------------------------------------
        #
        # QueryDocumentResponseは既存仕様との互換性を
        # 維持するためpageを使用する。
        #
        # 正式なページ情報の基準は
        # metadata["page_reference"]。
        #
        # --------------------------------------------------

        page = (
            metadata_item.get(
                "page_reference"
            )
            or metadata_item.get(
                "page"
            )
            or metadata_item.get(
                "page_number"
            )
        )

        documents.append(

            QueryDocumentResponse(

                document=item.document,

                score=item.score,

                distance=item.distance,

                page=page,

                metadata=metadata_item

            )

        )

    # ======================================================
    # Sources
    # ======================================================
    #
    # 回答の根拠・参考資料。
    #
    # QueryServiceではpage_referenceを正式名称として
    # 使用する。
    #
    # ここでpageへ変換しない。
    #
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

                page_reference=source.get(
                    "page_reference"
                )

            )

        )

    # ======================================================
    # Source Pages
    # ======================================================
    #
    # 回答の根拠となったページ。
    #
    # QueryServiceでRAG metadataから抽出済み。
    #
    # Routerではページ番号を生成・推測しない。
    #
    # ======================================================

    source_pages = result.get(
        "source_pages",
        []
    )

    # ======================================================
    # Follow-up Questions
    # ======================================================
    #
    # 次に学ぶと理解しやすい概念の提示。
    #
    # QueryServiceがLearningFollowUpServiceで生成した
    # FollowUpオブジェクトのリストをそのまま受け取る。
    #
    # QueryServiceは既に FollowUp（pydanticモデル）の
    # リストを返しているため、Router側で値の再構築は
    # 行わず、型変換のみ行う。
    #

    follow_ups = []

    for follow_up in result.get(
        "follow_ups",
        []
    ):

        if isinstance(
            follow_up,
            FollowUp
        ):

            follow_ups.append(
                follow_up
            )

            continue

        # --------------------------------------------------
        # dict等で渡ってきた場合の後方互換
        # --------------------------------------------------

        follow_ups.append(

            FollowUp(

                question=follow_up.get(
                    "question",
                    ""
                ),

                reason=follow_up.get(
                    "reason",
                    ""
                )

            )

        )

    # ======================================================
    # Answerability
    # ======================================================
    #
    # FULL / PARTIAL / NONE
    #
    # QueryServiceで判定された結果をそのまま返す。
    #
    # Routerではbool化しない。
    #
    # ======================================================

    answerability_status = (
        result.get(
            "answerability_status"
        )
    )

    answerability_reason = (
        result.get(
            "answerability_reason",
            ""
        )
    )

    # ======================================================
    # Compatibility Values
    # ======================================================
    #
    # QueryResponseに残している既存互換項目。
    #
    # 新しい処理時間情報はmetadataを正式な格納先とする。
    #
    # ======================================================

    elapsed_ms = (
        metadata.total_elapsed_ms
    )

    retrieved_count = (
        metadata.retrieved_count
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
        # 回答の根拠
        # --------------------------------------------------

        sources=sources,

        # --------------------------------------------------
        # 根拠ページ
        # --------------------------------------------------

        source_pages=source_pages,

        # --------------------------------------------------
        # 互換項目
        # --------------------------------------------------

        elapsed_ms=elapsed_ms,

        retrieved_count=retrieved_count,

        # --------------------------------------------------
        # RAG検索結果
        # --------------------------------------------------

        documents=documents,

        # --------------------------------------------------
        # Answerability
        # --------------------------------------------------

        answerability_status=(
            answerability_status
        ),

        answerability_reason=(
            answerability_reason
        ),

        # --------------------------------------------------
        # Follow-up Questions
        # --------------------------------------------------

        follow_ups=follow_ups,

        # --------------------------------------------------
        # システム情報
        # --------------------------------------------------

        metadata=metadata

    )