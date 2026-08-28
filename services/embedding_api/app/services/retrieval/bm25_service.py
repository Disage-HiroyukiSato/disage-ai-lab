import json
import logging
import math
import re
import threading
import unicodedata

from pathlib import Path
from typing import Any

from app.config import settings


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
    # ------------------------------------------------------
    # Phase16 : コレクション別インデックスファイル
    # ------------------------------------------------------
    #
    # コレクションごとに完全に独立したインスタンス・
    # インデックスファイルを持つ。
    #
    # 例:
    #   /app/data/bm25/index_java_training.json
    #   /app/data/bm25/index_instructor_ops.json
    #
    # コンストラクタでcollection_nameを受け取り、
    # ファイル名に反映する。
    #

    INDEX_DIR = Path(

        "/app/data/bm25"

    )

    def __init__(

        self,

        collection_name: str = "default"

    ):

        self.collection_name = collection_name

        self.index_path = (

            self.INDEX_DIR

            / f"index_{collection_name}.json"

        )

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

        #
        # document_id -> chunk_id一覧（逆引きインデックス）
        #
        # 同一document_idの再登録（更新）時に、
        # 該当document_idの全chunk_idを高速に列挙して
        # 削除できるようにするための索引。
        #
        # _load()時にdocumentsから再構築する。
        #

        self.document_id_index: dict[
            str,
            set[str]
        ] = {}

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
    # document_id逆引きインデックス : 登録
    #

    def _index_add(

        self,

        chunk_id: str,

        metadata: dict[str, Any]

    ) -> None:

        document_id = metadata.get(
            "document_id"
        )

        if not document_id:

            return

        document_id = str(
            document_id
        )

        if document_id not in self.document_id_index:

            self.document_id_index[document_id] = set()

        self.document_id_index[document_id].add(
            chunk_id
        )

    #
    # document_id逆引きインデックス : 削除
    #

    def _index_remove(

        self,

        chunk_id: str,

        metadata: dict[str, Any] | None

    ) -> None:

        if not metadata:

            return

        document_id = metadata.get(
            "document_id"
        )

        if not document_id:

            return

        document_id = str(
            document_id
        )

        chunk_ids = self.document_id_index.get(
            document_id
        )

        if not chunk_ids:

            return

        chunk_ids.discard(
            chunk_id
        )

        if not chunk_ids:

            del self.document_id_index[document_id]

    #
    # document_id逆引きインデックス : 再構築
    #

    def _rebuild_document_id_index(self) -> None:

        self.document_id_index = {}

        for chunk_id, document in self.documents.items():

            metadata = document.get(
                "metadata",
                {}
            )

            self._index_add(
                chunk_id,
                metadata
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

            for token in term_frequency:

                self.document_frequency[token] = (
                    self.document_frequency.get(
                        token,
                        0
                    )
                    + 1
                )

            self._index_add(
                chunk_id,
                metadata
            )

            self._recalculate_statistics()

            self._save()

            logger.debug(
                "BM25 index added [%s]: %s",
                self.collection_name,
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

        old_document = self.documents.get(
            chunk_id
        )

        old_metadata = (

            old_document.get(
                "metadata"
            )

            if old_document

            else None

        )

        self._index_remove(
            chunk_id,
            old_metadata
        )

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
                "BM25 index removed [%s]: %s",
                self.collection_name,
                chunk_id
            )

    #
    # document_id単位での削除
    #

    def remove_by_document_id(

        self,

        document_id: str

    ) -> int:

        if not document_id:

            return 0

        with self.lock:

            chunk_ids = self.document_id_index.get(

                document_id,

                set()

            )

            target_chunk_ids = list(
                chunk_ids
            )

            if not target_chunk_ids:

                return 0

            for chunk_id in target_chunk_ids:

                self._remove_internal(
                    chunk_id
                )

            self._recalculate_statistics()

            self._save()

            logger.info(

                "BM25 index removed by document_id [%s] : "
                "%s (%d chunks)",

                self.collection_name,

                document_id,

                len(target_chunk_ids)

            )

            return len(
                target_chunk_ids
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

        self.index_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        data = {

            "version": 1,

            "collection_name": self.collection_name,

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
                self.index_path
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
            self.index_path
        )

    #
    # Load
    #

    def _load(self):

        if not self.index_path.exists():

            logger.info(
                "BM25 index does not exist [%s]. "
                "Starting with empty index.",
                self.collection_name
            )

            return

        try:

            with self.index_path.open(
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

            self._rebuild_document_id_index()

            logger.info(
                "BM25 index loaded [%s]: %d documents",
                self.collection_name,
                len(
                    self.documents
                )
            )

        except Exception:

            logger.exception(
                "Failed to load BM25 index [%s]. "
                "Starting with empty index.",
                self.collection_name
            )

            self.documents = {}

            self.document_frequency = {}

            self.term_frequencies = {}

            self.average_document_length = 0.0

            self.document_id_index = {}


#
# ------------------------------------------------------
# Phase16 : コレクション別インスタンス
# ------------------------------------------------------
#
# bm25_service                : 後方互換用のデフォルトインスタンス
#                                （java_training用の別名としても機能）
# bm25_service_java_training   : Java研修教材（Phase15）
# bm25_service_instructor_ops  : 講師業務知識（Phase16）
#
# collection_nameからインスタンスを引けるよう、
# レジストリ（辞書）も提供する。
#

bm25_service_java_training = BM25Service(

    collection_name=settings.collection_java_training

)

bm25_service_instructor_ops = BM25Service(

    collection_name=settings.collection_instructor_ops

)

#
# 後方互換 : Phase15までのコードが `bm25_service` を
# 直接importしているため、java_training用インスタンスを
# デフォルトとして同名で公開する。
#

bm25_service = bm25_service_java_training

_bm25_registry: dict[str, BM25Service] = {

    settings.collection_java_training: bm25_service_java_training,

    settings.collection_instructor_ops: bm25_service_instructor_ops

}


def get_bm25_service(

    collection_name: str

) -> BM25Service:

    if collection_name not in _bm25_registry:

        logger.warning(

            "Unknown collection_name for BM25, "
            "creating new index : %s",

            collection_name

        )

        _bm25_registry[collection_name] = BM25Service(

            collection_name=collection_name

        )

    return _bm25_registry[collection_name]