from sentence_transformers import SentenceTransformer

import logging

from app.config import settings
from app.core.exceptions import EmbeddingException
from app.services.chunk_service import chunk_service
from app.services.chroma_service import chroma_service
from app.services.bm25_service import get_bm25_service

logger = logging.getLogger(__name__)


class EmbeddingService:

    def __init__(self):

        self.model = None

    def get_model(self):

        if self.model is None:

            logger.info("----------------------------------------")
            logger.info("Loading Embedding Model...")
            logger.info(settings.embedding_model)

            try:

                self.model = SentenceTransformer(

                    settings.embedding_model

                )

            except Exception as ex:

                raise EmbeddingException(

                    f"Embedding model load failed : {ex}"

                )

            logger.info("Embedding Model Loaded")
            logger.info("----------------------------------------")

        return self.model

    def register(

        self,

        document_id: str,

        text: str,

        metadata: dict | None = None,

        collection_name: str | None = None

    ):

        #
        # Phase16 : 複数コレクション対応
        #
        # collection_name未指定時は既存の
        # settings.chroma_collection（java_training想定）
        # へ登録する後方互換動作とする。
        #

        target_collection = (

            collection_name

            or settings.chroma_collection

        )

        bm25_service = get_bm25_service(

            target_collection

        )

        model = self.get_model()

        #
        # 既存チャンクの削除（更新扱い）
        #
        # 同一document_idで再登録された場合、
        # 古いチャンクをVector Index（ChromaDB）と
        # BM25 Indexの両方から削除してから
        # 新規チャンクを登録する。
        #
        # これを行わないと、古い内容と新しい内容が
        # 検索結果に重複して出現してしまう。
        #

        try:

            chroma_service.delete_by_document_id(

                document_id,

                collection_name=target_collection

            )

        except Exception:

            logger.exception(

                "Chroma delete_by_document_id failed : "
                "%s (collection=%s)",

                document_id,

                target_collection

            )

        try:

            removed_count = bm25_service.remove_by_document_id(

                document_id

            )

            if removed_count:

                logger.info(

                    "Existing BM25 chunks removed "
                    "(re-register) : %s (%d chunks, "
                    "collection=%s)",

                    document_id,

                    removed_count,

                    target_collection

                )

        except Exception:

            logger.exception(

                "BM25 remove_by_document_id failed : "
                "%s (collection=%s)",

                document_id,

                target_collection

            )

        #
        # 新規チャンク生成・登録
        #

        chunks = chunk_service.split(

            document_id=document_id,

            text=text,

            metadata=metadata

        )

        for chunk in chunks:

            #
            # Vector Index登録
            #

            embedding = model.encode(

                chunk.text,

                normalize_embeddings=True

            ).tolist()

            chroma_service.add(

                chunk,

                embedding,

                collection_name=target_collection

            )

            #
            # BM25 Index登録
            #
            # Vector Indexと同じchunkを、同じタイミングで
            # BM25側にも登録する。
            #
            # 片方だけ登録される不整合を避けるため、
            # register()内でまとめて実行する。
            #

            if settings.enable_hybrid_search:

                try:

                    bm25_service.add(

                        chunk_id=chunk.chunk_id,

                        text=chunk.text,

                        metadata=chunk.metadata

                    )

                except Exception:

                    logger.exception(

                        "BM25 index registration failed : "
                        "%s (collection=%s)",

                        chunk.chunk_id,

                        target_collection

                    )

        return len(chunks)

    def embedding(

        self,

        text

    ):

        model = self.get_model()

        return model.encode(

            text,

            normalize_embeddings=True

        ).tolist()


embedding_service = EmbeddingService()