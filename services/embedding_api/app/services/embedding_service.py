from sentence_transformers import SentenceTransformer

import logging

from app.config import settings
from app.core.exceptions import EmbeddingException
from app.services.chunk_service import chunk_service
from app.services.chroma_service import chroma_service
from app.services.bm25_service import bm25_service

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

        metadata: dict | None = None

    ):

        model = self.get_model()

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

                embedding

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

                        "BM25 index registration failed : %s",

                        chunk.chunk_id

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