import logging
import time

from app.config import settings

from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult

from app.services.embedding_service import embedding_service
from app.services.chroma_service import chroma_service
from app.services.bm25_service import get_bm25_service
from app.services.cache_service import cache_service
from app.services.collection_router_service import (
    collection_router_service
)

logger = logging.getLogger(__name__)


class RetrievalService:

    def _normalize(
        self,
        values: list[float]
    ) -> list[float]:

        if not values:

            return []

        minimum = min(values)

        maximum = max(values)

        spread = maximum - minimum

        if spread <= 0:

            return [
                1.0
                for _ in values
            ]

        return [
            (value - minimum) / spread
            for value in values
        ]

    def _apply_hybrid_score(
        self,
        question: str,
        items: list[RetrievalItem],
        collection_name: str
    ) -> None:

        if not items:

            return

        logger.info("----------------------------------------")
        logger.info("Hybrid Search Start")
        logger.info("----------------------------------------")

        vector_similarities = [

            1.0 - item.distance

            for item in items

        ]

        normalized_vector = self._normalize(

            vector_similarities

        )

        bm25_service = get_bm25_service(

            collection_name

        )

        bm25_results = bm25_service.search(

            query=question,

            limit=settings.retrieval_candidate_size

        )

        bm25_score_map: dict[str, float] = {}

        for result in bm25_results:

            chunk_id = (

                result.get("metadata", {})

                .get("chunk_id")

            )

            if not chunk_id:

                continue

            bm25_score_map[chunk_id] = result["score"]

        raw_bm25_scores = []

        for item in items:

            chunk_id = item.metadata.get(

                "chunk_id"

            )

            raw_bm25_scores.append(

                bm25_score_map.get(

                    chunk_id,

                    0.0

                )
            )

        normalized_bm25 = self._normalize(

            raw_bm25_scores

        )

        for (

            item,

            vector_similarity,

            normalized_vector_score,

            raw_bm25_score,

            normalized_bm25_score

        ) in zip(

            items,

            vector_similarities,

            normalized_vector,

            raw_bm25_scores,

            normalized_bm25

        ):

            item.hybrid_score = (

                settings.vector_weight * normalized_vector_score

                + settings.bm25_weight * normalized_bm25_score

            )

            item.vector_similarity = vector_similarity

            item.bm25_raw_score = raw_bm25_score

        logger.info(
            "Vector Weight : %.2f",
            settings.vector_weight
        )

        logger.info(
            "BM25 Weight   : %.2f",
            settings.bm25_weight
        )

        logger.info(
            "BM25 Hit Count : %d / %d",
            len(bm25_score_map),
            len(items)
        )

        logger.info("----------------------------------------")
        logger.info("Hybrid Search End")
        logger.info("----------------------------------------")

    #
    # ------------------------------------------------------
    # Phase17 : Chapterブースト
    # ------------------------------------------------------
    #
    # 受講生が現在学習中のchapterと一致するチャンクの
    # スコアに一定値を加算し、優先的に上位へ来るようにする。
    #
    # 完全一致フィルタではなく、他chapterのチャンクも
    # 検索対象に残すブースト方式とする（合意済みの方針）。
    #
    # Hybrid有効時 : hybrid_score に加算
    # Hybrid無効時 : distanceを減算（小さいほど上位のため）
    #
    # current_chapterが空文字列（進捗未登録）の場合は
    # 何もしない。
    #

    def _apply_chapter_boost(

        self,

        items: list[RetrievalItem],

        current_chapter: str

    ) -> None:

        if not current_chapter or not items:

            return

        boost_weight = settings.chapter_boost_weight

        if boost_weight <= 0:

            return

        boosted_count = 0

        for item in items:

            item_chapter = (

                item.metadata or {}

            ).get(

                "chapter",

                ""

            )

            if item_chapter != current_chapter:

                continue

            boosted_count += 1

            if settings.enable_hybrid_search:

                item.hybrid_score += boost_weight

            else:

                item.distance = max(

                    0.0,

                    item.distance - boost_weight

                )

        if boosted_count:

            logger.info(

                "Chapter Boost applied : chapter=%s "
                "boosted=%d/%d weight=%.2f",

                current_chapter,

                boosted_count,

                len(items),

                boost_weight

            )

    def _restore_from_cache(

        self,

        cached: dict

    ) -> RetrievalResult:

        items = [

            RetrievalItem(**item)

            for item in cached.get(

                "items",

                []

            )

        ]

        return RetrievalResult(

            query=cached["query"],

            total=cached["total"],

            elapsed_ms=cached["elapsed_ms"],

            items=items,

            cache_hit=True

        )

    def _serialize_for_cache(

        self,

        result: RetrievalResult

    ) -> dict:

        return {

            "query": result.query,

            "total": result.total,

            "elapsed_ms": result.elapsed_ms,

            "items": [

                item.model_dump()

                for item in result.items

            ]

        }

    def _search_single_collection(

        self,

        question: str,

        limit: int,

        collection_name: str,

        document_id: str | None = None,

        category: str | None = None,

        title: str | None = None,

        keywords: str | None = None,

        current_chapter: str = ""

    ) -> RetrievalResult:

        start = time.perf_counter()

        cache_key = None

        #
        # Phase17 : Chapterブーストが有効な場合、
        # 同じ質問でもcurrent_chapterによって並び順が
        # 変わるため、キャッシュキーにも含める。
        #

        if settings.enable_search_cache:

            cache_key = cache_service.build_key(

                question=question,

                limit=limit,

                document_id=document_id,

                category=category,

                title=title,

                keywords=keywords

            )

            cache_key = (

                f"{collection_name}:"
                f"{current_chapter}:"
                f"{cache_key}"

            )

            cached = cache_service.get(

                cache_key

            )

            if cached is not None:

                elapsed = int(
                    (
                        time.perf_counter() - start
                    ) * 1000
                )

                logger.info(
                    "----------------------------------------"
                )
                logger.info(
                    "Retrieval Cache Hit [%s] : %s",
                    collection_name,
                    cache_key
                )
                logger.info(
                    "Elapsed Time : %d ms",
                    elapsed
                )
                logger.info(
                    "----------------------------------------"
                )

                return self._restore_from_cache(

                    cached

                )

            logger.info(

                "Retrieval Cache Miss [%s] : %s",

                collection_name,

                cache_key

            )

        logger.info("----------------------------------------")
        logger.info("Vector Retrieval Start [%s]", collection_name)
        logger.info("----------------------------------------")

        logger.info(
            "Question : %s",
            question
        )

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

        chroma_start = time.perf_counter()

        result = chroma_service.query(
            embedding=embedding,
            candidate_size=settings.retrieval_candidate_size,
            where=where if where else None,
            collection_name=collection_name
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
                "No vector search results [%s].",
                collection_name
            )

            logger.info(
                "Elapsed Time : %d ms",
                elapsed
            )

            logger.info("----------------------------------------")
            logger.info("Vector Retrieval End [%s]", collection_name)
            logger.info("----------------------------------------")

            empty_result = RetrievalResult(
                query=question,
                total=0,
                elapsed_ms=elapsed,
                items=[]
            )

            if (

                settings.enable_search_cache

                and cache_key is not None

            ):

                cache_service.set(

                    cache_key,

                    self._serialize_for_cache(

                        empty_result

                    )

                )

            return empty_result

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

        if settings.enable_hybrid_search and items:

            self._apply_hybrid_score(
                question=question,
                items=items,
                collection_name=collection_name
            )

        #
        # Phase17 : Chapterブースト
        #
        # Hybrid合成後、ソート前に適用する。
        #

        if current_chapter:

            self._apply_chapter_boost(

                items=items,

                current_chapter=current_chapter

            )

        if settings.enable_hybrid_search:

            items.sort(

                key=lambda item: item.hybrid_score,

                reverse=True

            )

        else:

            items.sort(
                key=lambda item: item.distance
            )

        if limit > 0:

            items = items[:limit]

        logger.info("----------------------------------------")
        logger.info("Vector Retrieval Result [%s]", collection_name)
        logger.info("----------------------------------------")

        for index, item in enumerate(
            items,
            start=1
        ):

            logger.info(
                "[%d] distance=%.4f hybrid_score=%.4f",
                index,
                item.distance,
                item.hybrid_score
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
        logger.info("Vector Retrieval End [%s]", collection_name)
        logger.info("----------------------------------------")

        final_result = RetrievalResult(
            query=question,
            total=len(items),
            elapsed_ms=elapsed,
            items=items
        )

        if (

            settings.enable_search_cache

            and cache_key is not None

        ):

            cache_service.set(

                cache_key,

                self._serialize_for_cache(

                    final_result

                )

            )

            logger.info(

                "Retrieval Cache Set [%s] : %s (TTL=%ds)",

                collection_name,

                cache_key,

                settings.cache_ttl

            )

        return final_result

    def search(
        self,
        question: str,
        limit: int = 5,
        document_id: str | None = None,
        category: str | None = None,
        title: str | None = None,
        keywords: str | None = None,
        collection_name: str | None = None,
        current_chapter: str = ""
    ) -> RetrievalResult:

        start = time.perf_counter()

        if collection_name:

            resolved = collection_name

        else:

            resolved = collection_router_service.route(

                question

            )

        if resolved != collection_router_service.BOTH:

            return self._search_single_collection(

                question=question,

                limit=limit,

                collection_name=resolved,

                document_id=document_id,

                category=category,

                title=title,

                keywords=keywords,

                current_chapter=current_chapter

            )

        logger.info(

            "Collection Router -> both : "
            "searching java_training and instructor_ops"

        )

        result_java = self._search_single_collection(

            question=question,

            limit=limit,

            collection_name=settings.collection_java_training,

            document_id=document_id,

            category=category,

            title=title,

            keywords=keywords,

            current_chapter=current_chapter

        )

        result_ops = self._search_single_collection(

            question=question,

            limit=limit,

            collection_name=settings.collection_instructor_ops,

            document_id=document_id,

            category=category,

            title=title,

            keywords=keywords,

            current_chapter=current_chapter

        )

        merged_items = (

            result_java.items

            + result_ops.items

        )

        any_cache_hit = (

            result_java.cache_hit

            or result_ops.cache_hit

        )

        if not merged_items:

            elapsed = int(
                (
                    time.perf_counter() - start
                ) * 1000
            )

            return RetrievalResult(

                query=question,

                total=0,

                elapsed_ms=elapsed,

                items=[],

                cache_hit=any_cache_hit

            )

        if settings.enable_hybrid_search:

            merged_items.sort(

                key=lambda item: item.hybrid_score,

                reverse=True

            )

        else:

            merged_items.sort(

                key=lambda item: item.distance

            )

        if limit > 0:

            merged_items = merged_items[:limit]

        elapsed = int(
            (
                time.perf_counter() - start
            ) * 1000
        )

        logger.info(

            "Both collections merged : "
            "java_training=%d instructor_ops=%d -> %d "
            "(elapsed=%dms)",

            result_java.total,

            result_ops.total,

            len(merged_items),

            elapsed

        )

        return RetrievalResult(

            query=question,

            total=len(merged_items),

            elapsed_ms=elapsed,

            items=merged_items,

            cache_hit=any_cache_hit

        )


retrieval_service = RetrievalService()