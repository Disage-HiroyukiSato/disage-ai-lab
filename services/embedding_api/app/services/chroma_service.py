import chromadb

from app.config import settings


class ChromaService:

    def __init__(self):

        self.client = chromadb.HttpClient(

            host=settings.chroma_host,

            port=settings.chroma_port

        )

        self.collection = self.client.get_or_create_collection(

            name=settings.chroma_collection,

            metadata={

                "hnsw:space": "cosine"

            }

        )

    def add(

        self,

        chunk,

        embedding

    ):

        self.collection.add(

            ids=[

                chunk.chunk_id

            ],

            embeddings=[

                embedding

            ],

            documents=[

                chunk.text

            ],

            metadatas=[

                chunk.metadata

            ]

        )

    def query(

        self,

        embedding,

        candidate_size: int,

        where: dict | None = None

    ):

        kwargs = {

            "query_embeddings": [

                embedding

            ],

            "n_results": candidate_size

        }

        if where:

            kwargs["where"] = where

        return self.collection.query(

            **kwargs

        )


chroma_service = ChromaService()