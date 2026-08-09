import json
import logging
import math
import re
import threading
import unicodedata

from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class BM25Service:

    #
    # BM25 parameters
    #

    K1 = 1.5
    B = 0.75

    #
    # 日本語N-gram
    #

    NGRAM_SIZE = 2

    #
    # 永続化先
    #

    INDEX_PATH = Path(
        "/app/data/bm25/index.json"
    )

    def __init__(self):

        self.lock = threading.RLock()

        #
        # chunk_id -> document information
        #

        self.documents: dict[str, dict[str, Any]] = {}

        #
        # token -> document frequency
        #

        self.document_frequency: dict[str, int] = {}

        #
        # chunk_id -> token -> term frequency
        #

        self.term_frequencies: dict[
            str,
            dict[str, int]
        ] = {}

        #
        # Average document length
        #

        self.average_document_length = 0.0

        self._load()

    #
    # Tokenization
    #

    def _tokenize(
        self,
        text: str
    ) -> list[str]:

        if not text:

            return []

        text = unicodedata.normalize(
            "NFKC",
            text
        ).lower()

        tokens: list[str] = []

        #
        # 英数字・ASCII系の単語
        #

        latin_tokens = re.findall(
            r"[a-z0-9_]+",
            text
        )

        tokens.extend(
            latin_tokens
        )

        #
        # 日本語・CJK文字
        #
        # 2文字gramを生成する。
        #
        # 例:
        #
        # 「検索機能」
        #
        # -> 「検索」
        # -> 「索機」
        # -> 「機能」
        #

        cjk_chars = re.findall(
            r"[\u3040-\u30ff"
            r"\u3400-\u4dbf"
            r"\u4e00-\u9fff"
            r"\uf900-\ufaff"
            r"]",
            text
        )

        if len(cjk_chars) == 1:

            tokens.append(
                cjk_chars[0]
            )

        elif len(cjk_chars) >= 2:

            for index in range(
                len(cjk_chars) - 1
            ):

                tokens.append(
                    "".join(
                        cjk_chars[
                            index:index + self.NGRAM_SIZE
                        ]
                    )
                )

        #
        # 日本語文字列の位置関係をある程度維持するため、
        # 連続したCJK文字列についてもgramを生成する。
        #
        # 上記では全文からCJK文字だけを抜き出しているため、
        # 異なる単語をまたいでgramが生成される可能性がある。
        #
        # そのため、実際の検索用には連続CJK文字列単位でも
        # gramを追加する。
        #

        cjk_sequences = re.findall(
            r"[\u3040-\u30ff"
            r"\u3400-\u4dbf"
            r"\u4e00-\u9fff"
            r"\uf900-\ufaff"
            r"]+",
            text
        )

        for sequence in cjk_sequences:

            if len(sequence) == 1:

                tokens.append(
                    sequence
                )

                continue

            for index in range(
                len(sequence) - 1
            ):

                tokens.append(
                    sequence[
                        index:index + self.NGRAM_SIZE
                    ]
                )

        return tokens

    #
    # Index statistics
    #

    def _recalculate_statistics(self):

        document_count = len(
            self.documents
        )

        if document_count == 0:

            self.average_document_length = 0.0

            return

        total_length = sum(

            len(
                self.term_frequencies.get(
                    document_id,
                    {}
                )
            )

            for document_id
            in self.documents
        )

        self.average_document_length = (
            total_length
            / document_count
        )

    #
    # Add / Update
    #

    def add(
        self,
        chunk_id: str,
        text: str,
        metadata: dict[str, Any] | None = None
    ):

        if not chunk_id:

            raise ValueError(
                "chunk_id must not be empty"
            )

        if not text:

            raise ValueError(
                "text must not be empty"
            )

        metadata = metadata or {}

        with self.lock:

            #
            # 既存Chunkなら一旦削除
            #

            if chunk_id in self.documents:

                self._remove_internal(
                    chunk_id
                )

            tokens = self._tokenize(
                text
            )

            term_frequency: dict[
                str,
                int
            ] = {}

            for token in tokens:

                term_frequency[token] = (
                    term_frequency.get(
                        token,
                        0
                    )
                    + 1
                )

            self.documents[chunk_id] = {

                "text": text,

                "metadata": metadata

            }

            self.term_frequencies[
                chunk_id
            ] = term_frequency

            #
            # Document Frequency
            #

            for token in term_frequency:

                self.document_frequency[token] = (
                    self.document_frequency.get(
                        token,
                        0
                    )
                    + 1
                )

            self._recalculate_statistics()

            self._save()

            logger.debug(
                "BM25 index added: %s",
                chunk_id
            )

    #
    # Internal remove
    #

    def _remove_internal(
        self,
        chunk_id: str
    ):

        old_tf = self.term_frequencies.get(
            chunk_id,
            {}
        )

        for token in old_tf:

            if token not in self.document_frequency:

                continue

            self.document_frequency[token] -= 1

            if self.document_frequency[token] <= 0:

                del self.document_frequency[token]

        self.term_frequencies.pop(
            chunk_id,
            None
        )

        self.documents.pop(
            chunk_id,
            None
        )

    #
    # Remove
    #

    def remove(
        self,
        chunk_id: str
    ):

        with self.lock:

            if chunk_id not in self.documents:

                return

            self._remove_internal(
                chunk_id
            )

            self._recalculate_statistics()

            self._save()

            logger.debug(
                "BM25 index removed: %s",
                chunk_id
            )

    #
    # Search
    #

    def search(
        self,
        query: str,
        limit: int = 20
    ) -> list[dict[str, Any]]:

        if not query:

            return []

        query_tokens = self._tokenize(
            query
        )

        if not query_tokens:

            return []

        with self.lock:

            document_count = len(
                self.documents
            )

            if document_count == 0:

                return []

            average_length = (
                self.average_document_length
            )

            if average_length <= 0:

                return []

            #
            # Query token重複除去
            #

            query_tokens = list(
                dict.fromkeys(
                    query_tokens
                )
            )

            results = []

            for document_id in self.documents:

                term_frequency = (
                    self.term_frequencies.get(
                        document_id,
                        {}
                    )
                )

                document_length = sum(
                    term_frequency.values()
                )

                if document_length == 0:

                    continue

                score = 0.0

                for token in query_tokens:

                    tf = term_frequency.get(
                        token,
                        0
                    )

                    if tf == 0:

                        continue

                    df = self.document_frequency.get(
                        token,
                        0
                    )

                    if df == 0:

                        continue

                    #
                    # BM25 IDF
                    #

                    idf = math.log(
                        1.0
                        + (
                            document_count
                            - df
                            + 0.5
                        )
                        / (
                            df
                            + 0.5
                        )
                    )

                    denominator = (
                        tf
                        + self.K1
                        * (
                            1.0
                            - self.B
                            + self.B
                            * (
                                document_length
                                / average_length
                            )
                        )
                    )

                    score += (
                        idf
                        * (
                            tf
                            * (
                                self.K1
                                + 1.0
                            )
                        )
                        / denominator
                    )

                if score <= 0:

                    continue

                document = self.documents[
                    document_id
                ]

                results.append({

                    "chunk_id": document_id,

                    "document": document[
                        "text"
                    ],

                    "metadata": document[
                        "metadata"
                    ],

                    "score": float(score)

                })

            #
            # BM25 score降順
            #

            results.sort(

                key=lambda item: item[
                    "score"
                ],

                reverse=True

            )

            if limit > 0:

                results = results[:limit]

            return results

    #
    # Save
    #

    def _save(self):

        self.INDEX_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        data = {

            "version": 1,

            "documents": self.documents,

            "document_frequency": (
                self.document_frequency
            ),

            "term_frequencies": (
                self.term_frequencies
            ),

            "average_document_length": (
                self.average_document_length
            )

        }

        temporary_path = Path(
            str(
                self.INDEX_PATH
            ) + ".tmp"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False
            )

        temporary_path.replace(
            self.INDEX_PATH
        )

    #
    # Load
    #

    def _load(self):

        if not self.INDEX_PATH.exists():

            logger.info(
                "BM25 index does not exist. "
                "Starting with empty index."
            )

            return

        try:

            with self.INDEX_PATH.open(
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

            self.documents = data.get(
                "documents",
                {}
            )

            self.document_frequency = data.get(
                "document_frequency",
                {}
            )

            self.term_frequencies = data.get(
                "term_frequencies",
                {}
            )

            self.average_document_length = (
                data.get(
                    "average_document_length",
                    0.0
                )
            )

            logger.info(
                "BM25 index loaded: %d documents",
                len(
                    self.documents
                )
            )

        except Exception:

            logger.exception(
                "Failed to load BM25 index. "
                "Starting with empty index."
            )

            self.documents = {}

            self.document_frequency = {}

            self.term_frequencies = {}

            self.average_document_length = 0.0


bm25_service = BM25Service()