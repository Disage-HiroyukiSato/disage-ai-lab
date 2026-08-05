import logging
import time

from app.config import settings

from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult

from app.services.embedding_service import embedding_service
from app.services.chroma_service import chroma_service

logger = logging.getLogger(__name__)


class RetrievalService:

    def search(
        self,
        question: str,
        limit: int = 5,
        document_id: str | None = None,
        category: str | None = None,
        title: str | None = None,
        keywords: str | None = None
    ) -> RetrievalResult:

        start = time.perf_counter()

        logger.info("----------------------------------------")
        logger.info("Vector Retrieval Start")
        logger.info("----------------------------------------")

        logger.info(
            "Question : %s",
            question
        )

        #
        # Embedding生成
        #

        embedding_start = time.perf_counter()

        embedding = embedding_service.embedding(
            question
        )

        embedding_elapsed = int(
            (
                time.perf_counter() - embedding_start
            ) * 1000
        )

        logger.info(
            "Embedding Time : %d ms",
            embedding_elapsed
        )

        #
        # Metadata Filter生成
        #

        where = {}

        if document_id:

            where["document_id"] = document_id

        if category:

            where["category"] = category

        if title:

            where["title"] = title

        if keywords:

            where["keywords"] = keywords

        logger.info(
            "Metadata Filter : %s",
            where if where else None
        )

        #
        # ChromaDB検索
        #

        chroma_start = time.perf_counter()

        result = chroma_service.query(
            embedding=embedding,
            candidate_size=settings.retrieval_candidate_size,
            where=where if where else None
        )

        chroma_elapsed = int(
            (
                time.perf_counter() - chroma_start
            ) * 1000
        )

        logger.info(
            "Chroma Search Time : %d ms",
            chroma_elapsed
        )

        #
        # 検索結果確認
        #

        documents = []

        metadatas = []

        distances = []

        if result.get("documents"):

            documents = result["documents"][0]

        if result.get("metadatas"):

            metadatas = result["metadatas"][0]

        if result.get("distances"):

            distances = result["distances"][0]

        if not documents:

            elapsed = int(
                (
                    time.perf_counter() - start
                ) * 1000
            )

            logger.info(
                "No vector search results."
            )

            logger.info(
                "Elapsed Time : %d ms",
                elapsed
            )

            logger.info("----------------------------------------")
            logger.info("Vector Retrieval End")
            logger.info("----------------------------------------")

            return RetrievalResult(
                query=question,
                total=0,
                elapsed_ms=elapsed,
                items=[]
            )

        #
        # Distance Filter
        #

        items: list[RetrievalItem] = []

        for document, metadata, distance in zip(
            documents,
            metadatas,
            distances
        ):

            if distance > settings.max_distance:

                continue

            items.append(
                RetrievalItem(
                    document=document,
                    metadata=metadata or {},
                    distance=float(distance)
                )
            )

        logger.info(
            "Candidate Count : %d",
            len(documents)
        )

        logger.info(
            "Distance Filter : %d -> %d",
            len(documents),
            len(items)
        )

        #
        # Distance昇順
        #
        # Rerankerはここでは実行しない。
        #
        # 複数Query検索では、
        #
        # Query Expansion
        #       ↓
        # Vector Retrieval
        #       ↓
        # Merge
        #       ↓
        # Reranker
        #
        # の順序にするため、Rerankerは
        # MultiQueryRetrievalServiceより後段で実行する。
        #

        items.sort(
            key=lambda item: item.distance
        )

        #
        # limit適用
        #
        # retrieval_candidate_sizeで取得した候補から、
        # 呼び出し側へ返す件数を制限する。
        #

        if limit > 0:

            items = items[:limit]

        #
        # Retrieval結果ログ
        #

        logger.info("----------------------------------------")
        logger.info("Vector Retrieval Result")
        logger.info("----------------------------------------")

        for index, item in enumerate(
            items,
            start=1
        ):

            logger.info(
                "[%d] distance=%.4f",
                index,
                item.distance
            )

            logger.info(
                "Metadata : %s",
                item.metadata
            )

            preview = item.document.replace(
                "\n",
                " "
            )

            logger.info(
                "Document : %s",
                preview[:120]
            )

        #
        # 処理時間
        #

        elapsed = int(
            (
                time.perf_counter() - start
            ) * 1000
        )

        logger.info(
            "Returned : %d",
            len(items)
        )

        logger.info(
            "Elapsed Time : %d ms",
            elapsed
        )

        logger.info("----------------------------------------")
        logger.info("Vector Retrieval End")
        logger.info("----------------------------------------")

        return RetrievalResult(
            query=question,
            total=len(items),
            elapsed_ms=elapsed,
            items=items
        )


retrieval_service = RetrievalService()