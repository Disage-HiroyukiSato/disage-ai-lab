import logging
import time

from app.config import settings

from app.models.retrieval_item import RetrievalItem
from app.models.retrieval_result import RetrievalResult

from app.services.embedding_service import embedding_service
from app.services.chroma_service import chroma_service
from app.services.bm25_service import bm25_service
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)


class RetrievalService:

    #
    # ------------------------------------------------------
    # Hybrid Search : Score正規化
    # ------------------------------------------------------
    #
    # Min-Maxで [0, 1] に正規化する。
    #
    # 候補が1件のみ、または全件同値の場合は
    # 全件 1.0 として扱う（差がつけられないため）。
    #

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

    #
    # ------------------------------------------------------
    # Hybrid Search : Vector + BM25 合成
    # ------------------------------------------------------
    #
    # items          : Vector検索結果（distance昇順ソート前）
    # question       : BM25検索に使用するquery文字列
    #
    # Vector distance（小さいほど良い）を類似度
    # （大きいほど良い）に変換したうえで正規化し、
    # BM25 scoreも正規化したうえで重み付き合成する。
    #
    # 正規化前の生値（bm25_raw_score / vector_similarity）も
    # 検索ログ分析（Phase14-6）用にitemへ保存する。
    #

    def _apply_hybrid_score(
        self,
        question: str,
        items: list[RetrievalItem]
    ) -> None:

        if not items:

            return

        logger.info("----------------------------------------")
        logger.info("Hybrid Search Start")
        logger.info("----------------------------------------")

        #
        # Vector類似度 (1 - distance) を正規化
        #

        vector_similarities = [

            1.0 - item.distance

            for item in items

        ]

        normalized_vector = self._normalize(

            vector_similarities

        )

        #
        # BM25検索
        #
        # candidate_size分だけ取得し、chunk_idで引けるように
        # マップ化する。
        #

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

        #
        # Vector側items の chunk_id と BM25 score を突き合わせる。
        #
        # chunk_idが取得できないitemは0.0として扱う。
        #

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

        #
        # 重み付き合成 + 内訳スコアの保存
        #

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

            #
            # 検索ログ分析用の内訳（正規化前の生値）
            #

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
    # Search Cache : キャッシュからRetrievalResultを復元
    # ------------------------------------------------------
    #

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

    #
    # ------------------------------------------------------
    # Search Cache : RetrievalResultをキャッシュ用dictへ変換
    # ------------------------------------------------------
    #

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

        #
        # Search Cache : キャッシュ確認
        #
        # ENABLE_SEARCH_CACHE=true の場合のみ、
        # Cache Keyを生成しRedisを参照する。
        #
        # Hitした場合はVector検索・BM25検索・Embedding生成を
        # 一切行わず、キャッシュ済み結果をそのまま返す。
        #

        cache_key = None

        if settings.enable_search_cache:

            cache_key = cache_service.build_key(

                question=question,

                limit=limit,

                document_id=document_id,

                category=category,

                title=title,

                keywords=keywords

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
                    "Retrieval Cache Hit : %s",
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

                "Retrieval Cache Miss : %s",

                cache_key

            )

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

            empty_result = RetrievalResult(
                query=question,
                total=0,
                elapsed_ms=elapsed,
                items=[]
            )

            #
            # 0件結果もキャッシュする
            #
            # 存在しない資料に対する質問が繰り返された場合、
            # 毎回Embedding生成〜Chroma検索を行うのは無駄なため。
            #

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
        # Hybrid Search
        #
        # ENABLE_HYBRID_SEARCH=true の場合のみ、
        # BM25 scoreを合成してhybrid_scoreを設定する。
        #

        if settings.enable_hybrid_search and items:

            self._apply_hybrid_score(
                question=question,
                items=items
            )

            #
            # Hybrid Score降順
            #

            items.sort(

                key=lambda item: item.hybrid_score,

                reverse=True

            )

        else:

            #
            # Distance昇順（従来通り）
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

        final_result = RetrievalResult(
            query=question,
            total=len(items),
            elapsed_ms=elapsed,
            items=items
        )

        #
        # Search Cache : 保存
        #

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

                "Retrieval Cache Set : %s (TTL=%ds)",

                cache_key,

                settings.cache_ttl

            )

        return final_result


retrieval_service = RetrievalService()