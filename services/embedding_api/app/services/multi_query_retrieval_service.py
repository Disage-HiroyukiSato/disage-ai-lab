import logging
import time

from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult

from app.services.query_expansion_service import (
    query_expansion_service
)
from app.services.retrieval_service import (
    retrieval_service
)

logger = logging.getLogger(__name__)


class MultiQueryRetrievalService:

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
        logger.info("Multi Query Retrieval Start")
        logger.info("----------------------------------------")

        logger.info(
            "Question : %s",
            question
        )

        #
        # Query Expansion
        #

        queries = query_expansion_service.expand(
            question
        )

        if not queries:

            queries = [
                question
            ]

        logger.info(
            "Expanded Query Count : %d",
            len(queries)
        )

        for index, query in enumerate(
            queries,
            start=1
        ):

            logger.info(
                "Query [%d] : %s",
                index,
                query
            )

        #
        # 複数Query検索
        #

        all_items: list[RetrievalItem] = []

        retrieval_elapsed = 0

        for index, query in enumerate(
            queries,
            start=1
        ):

            logger.info("----------------------------------------")
            logger.info(
                "Retrieval [%d/%d]",
                index,
                len(queries)
            )
            logger.info("----------------------------------------")

            result = retrieval_service.search(
                question=query,
                limit=limit,
                document_id=document_id,
                category=category,
                title=title,
                keywords=keywords
            )

            retrieval_elapsed += result.elapsed_ms

            logger.info(
                "Query : %s",
                query
            )

            logger.info(
                "Retrieved : %d",
                result.total
            )

            if result.total == 0:

                continue

            all_items.extend(
                result.items
            )

        #
        # 検索結果なし
        #

        if not all_items:

            elapsed = int(
                (
                    time.perf_counter() - start
                ) * 1000
            )

            logger.info(
                "No documents retrieved."
            )

            logger.info(
                "Retrieval Time : %d ms",
                retrieval_elapsed
            )

            logger.info(
                "Elapsed Time : %d ms",
                elapsed
            )

            logger.info("----------------------------------------")
            logger.info("Multi Query Retrieval End")
            logger.info("----------------------------------------")

            return RetrievalResult(
                query=question,
                total=0,
                elapsed_ms=elapsed,
                items=[]
            )

        #
        # 重複除去
        #
        # document_id + chunk_noを基本キーとする。
        #
        # metadataが不足している場合は、
        # document本文をフォールバックキーとして使用する。
        #

        unique_items: dict[
            tuple,
            RetrievalItem
        ] = {}

        for item in all_items:

            metadata = item.metadata or {}

            document_id_value = metadata.get(
                "document_id"
            )

            chunk_no_value = metadata.get(
                "chunk_no"
            )

            if (
                document_id_value is not None
                and chunk_no_value is not None
            ):

                key = (
                    str(document_id_value),
                    str(chunk_no_value)
                )

            else:

                key = (
                    "document",
                    item.document
                )

            #
            # 新規登録
            #

            if key not in unique_items:

                unique_items[key] = item

                continue

            #
            # 同一Chunkが複数Queryから取得された場合
            #
            # Vector distanceが小さい方を採用する。
            #

            current_item = unique_items[key]

            if item.distance < current_item.distance:

                unique_items[key] = item

        merged_items = list(
            unique_items.values()
        )

        logger.info(
            "Retrieved Before Merge : %d",
            len(all_items)
        )

        logger.info(
            "Retrieved After Merge : %d",
            len(merged_items)
        )

        #
        # Distance順
        #
        # 現段階ではRetrievalServiceがRerankerを
        # 実行しているため、各Queryのscoreは存在する。
        #
        # Phase14-2でRetrievalServiceからRerankerを
        # 分離した後は、この部分をRerankerServiceへ
        # 渡す前の候補集合として使用する。
        #

        merged_items.sort(
            key=lambda item: item.distance
        )

        #
        # limit適用
        #
        # 現段階では既存RetrievalServiceとの互換性を
        # 維持するため、最終limitを適用する。
        #

        if limit > 0:

            merged_items = merged_items[:limit]

        #
        # 結果ログ
        #

        logger.info("----------------------------------------")
        logger.info("Merged Retrieval Result")
        logger.info("----------------------------------------")

        for index, item in enumerate(
            merged_items,
            start=1
        ):

            logger.info(
                "[%d] distance=%.4f score=%.4f",
                index,
                item.distance,
                item.score
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

        logger.info("----------------------------------------")
        logger.info("Multi Query Retrieval Summary")
        logger.info("----------------------------------------")

        logger.info(
            "Expanded Queries : %d",
            len(queries)
        )

        logger.info(
            "Retrieved Before Merge : %d",
            len(all_items)
        )

        logger.info(
            "Retrieved After Merge : %d",
            len(unique_items)
        )

        logger.info(
            "Returned : %d",
            len(merged_items)
        )

        logger.info(
            "Retrieval Time : %d ms",
            retrieval_elapsed
        )

        logger.info(
            "Elapsed Time : %d ms",
            elapsed
        )

        logger.info("----------------------------------------")
        logger.info("Multi Query Retrieval End")
        logger.info("----------------------------------------")

        return RetrievalResult(
            query=question,
            total=len(merged_items),
            elapsed_ms=elapsed,
            items=merged_items
        )


multi_query_retrieval_service = MultiQueryRetrievalService()