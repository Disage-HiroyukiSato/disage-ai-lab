import re

from uuid import uuid4

from app.config import settings
from app.models.document import DocumentChunk


class ChunkService:

    #
    # ------------------------------------------------------
    # Phase15 : コードブロック検出パターン
    # ------------------------------------------------------
    #
    # 1. ```で囲まれたフェンス形式（Markdown由来のPDF抽出、
    #    または教材が元々Markdown管理されている場合）
    #
    # 2. インデントが4スペース以上、またはタブで開始する行が
    #    連続するブロック（PDFからテキスト抽出した際、
    #    ```記法が失われてインデントのみ残るケース向け）
    #

    FENCE_PATTERN = re.compile(

        r"```[a-zA-Z0-9_+-]*\n.*?```",

        re.DOTALL

    )

    INDENT_LINE_PATTERN = re.compile(

        r"^(?:[ ]{4,}|\t+)\S.*$"

    )

    #
    # 連続何行以上のインデント行でコードブロックと
    # みなすかの閾値。
    #
    # 1行だけのインデントは単なる字下げの可能性が
    # あるため、誤検知を避けるために閾値を設ける。
    #

    MIN_INDENT_BLOCK_LINES = 2

    #
    # ------------------------------------------------------
    # テキストを「コードブロック」と「通常テキスト」の
    # セグメントに分割する。
    # ------------------------------------------------------
    #
    # 戻り値: [(is_code: bool, text: str), ...]
    #
    # 元のテキストの順序を保ったまま、コード部分と
    # 非コード部分を交互に返す。
    #

    def _split_segments(

        self,

        text: str

    ) -> list[tuple[bool, str]]:

        segments: list[tuple[bool, str]] = []

        cursor = 0

        #
        # 1. まずフェンス（```）で囲まれたブロックを
        #    最優先で抽出する。
        #

        for match in self.FENCE_PATTERN.finditer(

            text

        ):

            start, end = match.span()

            if start > cursor:

                segments.append(

                    (

                        False,

                        text[cursor:start]

                    )

                )

            segments.append(

                (

                    True,

                    match.group()

                )

            )

            cursor = end

        if cursor < len(text):

            segments.append(

                (

                    False,

                    text[cursor:]

                )

            )

        if not segments:

            segments = [

                (

                    False,

                    text

                )

            ]

        #
        # 2. フェンスが無かった非コードセグメントに対して、
        #    インデント連続行をコードブロックとして
        #    追加検出する。
        #

        refined: list[tuple[bool, str]] = []

        for is_code, segment in segments:

            if is_code:

                refined.append(

                    (

                        is_code,

                        segment

                    )

                )

                continue

            refined.extend(

                self._split_by_indent(

                    segment

                )

            )

        return refined

    #
    # ------------------------------------------------------
    # インデント連続行をコードブロックとして検出する。
    # ------------------------------------------------------
    #

    def _split_by_indent(

        self,

        text: str

    ) -> list[tuple[bool, str]]:

        lines = text.split(

            "\n"

        )

        segments: list[tuple[bool, str]] = []

        buffer: list[str] = []

        buffer_is_indent = False

        def flush():

            if not buffer:

                return

            content = "\n".join(

                buffer

            )

            is_code = (

                buffer_is_indent

                and len(buffer)

                >= self.MIN_INDENT_BLOCK_LINES

            )

            segments.append(

                (

                    is_code,

                    content

                )

            )

        for line in lines:

            is_indent_line = bool(

                self.INDENT_LINE_PATTERN.match(

                    line

                )

            )

            if not buffer:

                buffer = [line]

                buffer_is_indent = is_indent_line

                continue

            if is_indent_line == buffer_is_indent:

                buffer.append(

                    line

                )

                continue

            flush()

            buffer = [line]

            buffer_is_indent = is_indent_line

        flush()

        return segments

    #
    # ------------------------------------------------------
    # 通常テキストの分割（既存ロジック）
    # ------------------------------------------------------
    #
    # 文単位でchunk_sizeに収まるようまとめる。
    #
    # コードブロックには適用しない。
    #

    def _split_text_segment(

        self,

        segment_text: str

    ) -> list[str]:

        chunks: list[str] = []

        current = ""

        paragraphs = [

            p.strip()

            for p in segment_text.split("\n")

            if p.strip()

        ]

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

                        current

                    )

                while len(sentence) > settings.chunk_size:

                    part = sentence[

                        :settings.chunk_size

                    ]

                    chunks.append(

                        part

                    )

                    sentence = sentence[

                        settings.chunk_size

                        - settings.chunk_overlap:

                    ]

                current = sentence

        if current:

            chunks.append(

                current

            )

        return chunks

    #
    # ------------------------------------------------------
    # コードブロックの分割
    # ------------------------------------------------------
    #
    # コードブロックは意味的なまとまりを保つため、
    # chunk_sizeを超えても基本的には分割しない。
    #
    # ただし極端に長いコードブロック（chunk_sizeの3倍超）は
    # Embeddingモデルの入力長制限を考慮し、行単位で分割する。
    #
    # 通常テキストのような文分割（句点区切り）は行わない。
    #

    CODE_MAX_MULTIPLIER = 3

    def _split_code_segment(

        self,

        segment_text: str

    ) -> list[str]:

        max_length = (

            settings.chunk_size
            * self.CODE_MAX_MULTIPLIER

        )

        if len(segment_text) <= max_length:

            return [

                segment_text

            ]

        #
        # 行単位で max_length に収まるようまとめる。
        #
        # コードは行の途中で切ると文法が壊れるため、
        # 行境界でのみ分割する。
        #

        lines = segment_text.split(

            "\n"

        )

        chunks: list[str] = []

        current_lines: list[str] = []

        current_length = 0

        for line in lines:

            line_length = len(line) + 1

            if (

                current_lines

                and current_length + line_length > max_length

            ):

                chunks.append(

                    "\n".join(

                        current_lines

                    )

                )

                current_lines = []

                current_length = 0

            current_lines.append(

                line

            )

            current_length += line_length

        if current_lines:

            chunks.append(

                "\n".join(

                    current_lines

                )

            )

        return chunks

    #
    # ------------------------------------------------------
    # コードブロックの言語推定
    # ------------------------------------------------------
    #
    # ```java のようなフェンス指定があれば優先的に採用する。
    #
    # 指定が無い場合は metadata の language
    # （登録時にAPIで指定された値）にフォールバックする。
    #

    FENCE_LANGUAGE_PATTERN = re.compile(

        r"^```([a-zA-Z0-9_+-]*)"

    )

    def _detect_language(

        self,

        segment_text: str,

        fallback_language: str

    ) -> str:

        match = self.FENCE_LANGUAGE_PATTERN.match(

            segment_text.strip()

        )

        if match and match.group(1):

            return match.group(1).lower()

        return fallback_language

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

        metadata.setdefault(

            "chapter",

            ""

        )

        metadata.setdefault(

            "section",

            ""

        )

        fallback_language = metadata.get(

            "language",

            ""

        )

        text = text.replace(

            "\r\n",

            "\n"

        )

        #
        # コード/非コードセグメントへ分割
        #

        segments = self._split_segments(

            text

        )

        chunks: list[DocumentChunk] = []

        chunk_no = 1

        for is_code, segment_text in segments:

            if not segment_text.strip():

                continue

            if is_code:

                parts = self._split_code_segment(

                    segment_text

                )

                content_type = "code"

                language = self._detect_language(

                    segment_text,

                    fallback_language

                )

            else:

                parts = self._split_text_segment(

                    segment_text

                )

                content_type = "text"

                language = ""

            for part in parts:

                if not part.strip():

                    continue

                chunk_id = str(

                    uuid4()

                )

                chunk_metadata = {

                    **metadata,

                    "document_id": document_id,

                    "chunk_no": chunk_no,

                    "chunk_id": chunk_id,

                    "content_type": content_type,

                    "language": language

                }

                chunks.append(

                    DocumentChunk(

                        chunk_id=chunk_id,

                        document_id=document_id,

                        chunk_no=chunk_no,

                        text=part,

                        metadata=chunk_metadata

                    )

                )

                chunk_no += 1

        return chunks


chunk_service = ChunkService()