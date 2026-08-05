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

                    chunks.append(

                        DocumentChunk(

                            chunk_id=str(uuid4()),

                            document_id=document_id,

                            chunk_no=chunk_no,

                            text=current,

                            metadata={

                                **metadata,

                                "document_id": document_id,

                                "chunk_no": chunk_no

                            }

                        )

                    )

                    chunk_no += 1

                while len(sentence) > settings.chunk_size:

                    part = sentence[

                        :settings.chunk_size

                    ]

                    chunks.append(

                        DocumentChunk(

                            chunk_id=str(uuid4()),

                            document_id=document_id,

                            chunk_no=chunk_no,

                            text=part,

                            metadata={

                                **metadata,

                                "document_id": document_id,

                                "chunk_no": chunk_no

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

            chunks.append(

                DocumentChunk(

                    chunk_id=str(uuid4()),

                    document_id=document_id,

                    chunk_no=chunk_no,

                    text=current,

                    metadata={

                        **metadata,

                        "document_id": document_id,

                        "chunk_no": chunk_no

                    }

                )

            )

        return chunks


chunk_service = ChunkService()