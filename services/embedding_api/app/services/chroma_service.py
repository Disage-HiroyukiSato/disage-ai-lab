import chromadb

from app.config import settings


class ChromaService:

    #
    # ------------------------------------------------------
    # Phase16 : 複数コレクション対応
    # ------------------------------------------------------
    #
    # java_training  : Java研修教材（Phase15）
    # instructor_ops : 講師業務知識（FAQ・マニュアル等、Phase16）
    #
    # コレクションはget_or_create_collectionで遅延生成し、
    # collection_name -> Collectionオブジェクトの辞書で
    # キャッシュする。
    #

    def __init__(self):

        self.client = chromadb.HttpClient(

            host=settings.chroma_host,

            port=settings.chroma_port

        )

        self._collections: dict = {}

        #
        # 後方互換 : 既存の単一コレクション運用のための
        # デフォルトコレクション。
        #
        # Phase15までのコードが settings.chroma_collection を
        # 前提にしている場合でも動作するよう残す。
        #

        self.collection = self._get_or_create(

            settings.chroma_collection

        )

    def _get_or_create(

        self,

        collection_name: str

    ):

        if collection_name in self._collections:

            return self._collections[collection_name]

        collection = self.client.get_or_create_collection(

            name=collection_name,

            metadata={

                "hnsw:space": "cosine"

            }

        )

        self._collections[collection_name] = collection

        return collection

    def add(

        self,

        chunk,

        embedding,

        collection_name: str | None = None

    ):

        collection = self._get_or_create(

            collection_name

            or settings.chroma_collection

        )

        collection.add(

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

        where: dict | None = None,

        collection_name: str | None = None

    ):

        collection = self._get_or_create(

            collection_name

            or settings.chroma_collection

        )

        kwargs = {

            "query_embeddings": [

                embedding

            ],

            "n_results": candidate_size

        }

        if where:

            kwargs["where"] = where

        return collection.query(

            **kwargs

        )

    #
    # ------------------------------------------------------
    # document_id単位での削除
    # ------------------------------------------------------
    #
    # 同一document_idの再登録（更新）時に、古いチャンクを
    # 一括削除するために使用する。
    #
    # ChromaDBのwhere句でdocument_idを指定して削除する。
    #
    # 該当データが存在しない場合もエラーにはならない
    # （Chroma側の仕様）。
    #

    def delete_by_document_id(

        self,

        document_id: str,

        collection_name: str | None = None

    ) -> None:

        collection = self._get_or_create(

            collection_name

            or settings.chroma_collection

        )

        collection.delete(

            where={

                "document_id": document_id

            }

        )

    def count(

        self,

        collection_name: str | None = None

    ) -> int:

        collection = self._get_or_create(

            collection_name

            or settings.chroma_collection

        )

        return collection.count()


chroma_service = ChromaService()