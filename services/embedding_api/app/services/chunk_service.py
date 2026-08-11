import re

from uuid import uuid4

from app.config import settings
from app.models.document import DocumentChunk


class ChunkService:

    def split(

        self,

        document_id: str,

        text: str,

        metadata: dict | None = None

    ) -> list[DocumentChunk]:

        metadata = metadata or {}

        metadata.setdefault(

            "title",

            document_id

        )

        metadata.setdefault(

            "category",

            "General"

        )

        metadata.setdefault(

            "keywords",

            ""

        )

        chunks = []

        chunk_no = 1

        text = text.replace(

            "\r\n",

            "\n"

        )

        paragraphs = [

            p.strip()

            for p in text.split("\n")

            if p.strip()

        ]

        current = ""

        for paragraph in paragraphs:

            sentences = re.split(

                r'(?<=[。！？.!?])',

                paragraph

            )

            for sentence in sentences:

                sentence = sentence.strip()

                if not sentence:

                    continue

                if (

                    len(current)

                    + len(sentence)

                    <= settings.chunk_size

                ):

                    current += sentence

                    continue

                if current:

                    chunk_id = str(uuid4())

                    chunks.append(

                        DocumentChunk(

                            chunk_id=chunk_id,

                            document_id=document_id,

                            chunk_no=chunk_no,

                            text=current,

                            metadata={

                                **metadata,

                                "document_id": document_id,

                                "chunk_no": chunk_no,

                                #
                                # BM25 Index側との突き合わせに使用する。
                                #
                                # RetrievalService._apply_hybrid_score()で
                                # Vector検索結果とBM25検索結果を
                                # chunk_id単位で紐付けるため必須。
                                #

                                "chunk_id": chunk_id

                            }

                        )

                    )

                    chunk_no += 1

                while len(sentence) > settings.chunk_size:

                    part = sentence[

                        :settings.chunk_size

                    ]

                    chunk_id = str(uuid4())

                    chunks.append(

                        DocumentChunk(

                            chunk_id=chunk_id,

                            document_id=document_id,

                            chunk_no=chunk_no,

                            text=part,

                            metadata={

                                **metadata,

                                "document_id": document_id,

                                "chunk_no": chunk_no,

                                "chunk_id": chunk_id

                            }

                        )

                    )

                    chunk_no += 1

                    sentence = sentence[

                        settings.chunk_size

                        - settings.chunk_overlap:

                    ]

                current = sentence

        if current:

            chunk_id = str(uuid4())

            chunks.append(

                DocumentChunk(

                    chunk_id=chunk_id,

                    document_id=document_id,

                    chunk_no=chunk_no,

                    text=current,

                    metadata={

                        **metadata,

                        "document_id": document_id,

                        "chunk_no": chunk_no,

                        "chunk_id": chunk_id

                    }

                )

            )

        return chunks


chunk_service = ChunkService()