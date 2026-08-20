import re

from uuid import uuid4

from app.config import settings
from app.models.document import DocumentChunk


class ChunkService:

    # ======================================================
    # Phase15 : コードブロック検出パターン
    # ======================================================
    #
    # 1. ```で囲まれたフェンス形式
    #
    # 2. インデントが4スペース以上、またはタブで開始する
    #    連続行
    #
    # ======================================================

    FENCE_PATTERN = re.compile(

        r"```[a-zA-Z0-9_+-]*\n.*?```",

        re.DOTALL

    )

    INDENT_LINE_PATTERN = re.compile(

        r"^(?:[ ]{4,}|\t+)\S.*$"

    )

    MIN_INDENT_BLOCK_LINES = 2

    # ======================================================
    # Page Reference
    # ======================================================
    #
    # 抽出済みテキストに含まれるページ境界を検出する。
    #
    # 想定形式：
    #
    #   === PAGE: 10 ===
    #   === PAGE: 10 ===
    #
    #   PAGE: 10
    #
    #   [PAGE 10]
    #
    #   [Page 10]
    #
    #   --- PAGE: 10 ---
    #
    # ページ境界そのものはchunk本文には含めない。
    #
    # ======================================================

    PAGE_MARKER_PATTERN = re.compile(

        r"""
        ^\s*
        (?:
            ={2,}\s*PAGE\s*[:：]?\s*(\d+(?:\s*[-~〜]\s*\d+)?)\s*={2,}
            |
            -{2,}\s*PAGE\s*[:：]?\s*(\d+(?:\s*[-~〜]\s*\d+)?)\s*-{2,}
            |
            PAGE\s*[:：]\s*(\d+(?:\s*[-~〜]\s*\d+)?)
            |
            \[\s*PAGE\s+(\d+(?:\s*[-~〜]\s*\d+)?)\s*\]
        )
        \s*$
        """,

        re.IGNORECASE | re.VERBOSE

    )

    # ======================================================
    # ページ境界を検出する。
    # ======================================================

    def _extract_page_reference(
        self,
        line: str
    ) -> str | None:

        match = self.PAGE_MARKER_PATTERN.match(
            line
        )

        if not match:

            return None

        for group in match.groups():

            if group is not None:

                page = group.strip()

                # --------------------------------------------------
                # 正式な表記
                # --------------------------------------------------

                if "-" in page:

                    page = page.replace(
                        " ",
                        ""
                    )

                if "~" in page:

                    page = page.replace(
                        " ",
                        ""
                    )

                    page = page.replace(
                        "~",
                        "-"
                    )

                if "〜" in page:

                    page = page.replace(
                        " ",
                        ""
                    )

                    page = page.replace(
                        "〜",
                        "-"
                    )

                return f"p.{page}"

        return None

    # ======================================================
    # Page Segment
    # ======================================================
    #
    # テキストをページ単位に分割する。
    #
    # 戻り値：
    #
    # [
    #     (
    #         "p.10",
    #         "10ページ目の本文..."
    #     ),
    #     (
    #         "p.11",
    #         "11ページ目の本文..."
    #     )
    # ]
    #
    # ページマーカーが存在しない場合は、
    # page_reference=None として全文を1セグメントとして扱う。
    #
    # ======================================================

    def _split_by_page(
        self,
        text: str
    ) -> list[tuple[str | None, str]]:

        lines = text.split(
            "\n"
        )

        segments: list[
            tuple[str | None, str]
        ] = []

        current_page: str | None = None

        current_lines: list[str] = []

        for line in lines:

            page_reference = (
                self._extract_page_reference(
                    line
                )
            )

            if page_reference is not None:

                if current_lines:

                    segments.append(
                        (
                            current_page,
                            "\n".join(
                                current_lines
                            )
                        )
                    )

                current_page = page_reference

                current_lines = []

                continue

            current_lines.append(
                line
            )

        if current_lines:

            segments.append(
                (
                    current_page,
                    "\n".join(
                        current_lines
                    )
                )
            )

        if not segments:

            return [
                (
                    None,
                    text
                )
            ]

        return segments

    # ======================================================
    # Metadata Page Reference
    # ======================================================
    #
    # APIから明示的にpage_referenceが指定されている場合、
    # ページマーカーがない箇所のフォールバックとして使用する。
    #
    # ページマーカーが存在する場合は、
    # マーカーから得られたページ情報を優先する。
    #
    # ======================================================

    def _normalize_page_reference(
        self,
        page_reference: str | None
    ) -> str | None:

        if page_reference is None:

            return None

        value = str(
            page_reference
        ).strip()

        if not value:

            return None

        # --------------------------------------------------
        # 既に p.12 形式
        # --------------------------------------------------

        if value.lower().startswith(
            "p."
        ):

            return value

        # --------------------------------------------------
        # 数字だけの場合
        # --------------------------------------------------

        if re.fullmatch(
            r"\d+(?:\s*[-~〜]\s*\d+)?",
            value
        ):

            value = value.replace(
                " ",
                ""
            )

            value = value.replace(
                "~",
                "-"
            )

            value = value.replace(
                "〜",
                "-"
            )

            return f"p.{value}"

        return value

    # ======================================================
    # 通常テキスト / コードセグメント
    # ======================================================

    def _split_segments(
        self,
        text: str
    ) -> list[tuple[bool, str]]:

        segments: list[
            tuple[bool, str]
        ] = []

        cursor = 0

        # --------------------------------------------------
        # 1. Markdownフェンス形式
        # --------------------------------------------------

        for match in self.FENCE_PATTERN.finditer(
            text
        ):

            start, end = match.span()

            if start > cursor:

                segments.append(
                    (
                        False,
                        text[
                            cursor:start
                        ]
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
                    text[
                        cursor:
                    ]
                )
            )

        if not segments:

            segments = [
                (
                    False,
                    text
                )
            ]

        # --------------------------------------------------
        # 2. インデントコードブロック
        # --------------------------------------------------

        refined: list[
            tuple[bool, str]
        ] = []

        for is_code, segment in segments:

            if is_code:

                refined.append(
                    (
                        True,
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

    # ======================================================
    # インデント連続行
    # ======================================================

    def _split_by_indent(
        self,
        text: str
    ) -> list[tuple[bool, str]]:

        lines = text.split(
            "\n"
        )

        segments: list[
            tuple[bool, str]
        ] = []

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

                buffer = [
                    line
                ]

                buffer_is_indent = (
                    is_indent_line
                )

                continue

            if (
                is_indent_line
                == buffer_is_indent
            ):

                buffer.append(
                    line
                )

                continue

            flush()

            buffer = [
                line
            ]

            buffer_is_indent = (
                is_indent_line
            )

        flush()

        return segments

    # ======================================================
    # 通常テキスト分割
    # ======================================================

    def _split_text_segment(
        self,
        segment_text: str
    ) -> list[str]:

        chunks: list[str] = []

        current = ""

        paragraphs = [

            p.strip()

            for p in segment_text.split(
                "\n"
            )

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

                while (
                    len(sentence)
                    > settings.chunk_size
                ):

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

    # ======================================================
    # コードブロック分割
    # ======================================================

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
                and
                current_length
                + line_length
                > max_length
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

    # ======================================================
    # コード言語推定
    # ======================================================

    FENCE_LANGUAGE_PATTERN = re.compile(
        r"^```([a-zA-Z0-9_+-]*)"
    )

    def _detect_language(
        self,
        segment_text: str,
        fallback_language: str
    ) -> str:

        match = (
            self.FENCE_LANGUAGE_PATTERN.match(
                segment_text.strip()
            )
        )

        if (
            match
            and match.group(1)
        ):

            return match.group(
                1
            ).lower()

        return fallback_language

    # ======================================================
    # Split
    # ======================================================

    def split(
        self,
        document_id: str,
        text: str,
        metadata: dict | None = None
    ) -> list[DocumentChunk]:

        metadata = dict(
            metadata or {}
        )

        # --------------------------------------------------
        # Default metadata
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Document-level page reference
        # --------------------------------------------------
        #
        # Document APIから
        #
        # page_reference="p.12"
        #
        # のように渡された場合のフォールバック。
        #
        # ==================================================

        document_page_reference = (
            self._normalize_page_reference(
                metadata.get(
                    "page_reference"
                )
            )
        )

        if document_page_reference:

            metadata[
                "page_reference"
            ] = document_page_reference

        # --------------------------------------------------
        # Language
        # --------------------------------------------------

        fallback_language = str(
            metadata.get(
                "language",
                ""
            )
        )

        text = text.replace(
            "\r\n",
            "\n"
        )

        # ==================================================
        # Page segmentation
        # ==================================================
        #
        # ページ単位に分けてから、
        # 各ページ内でコード/通常テキストを判定する。
        #
        # これにより、
        #
        # p.10 → chunk 1
        # p.10 → chunk 2
        # p.11 → chunk 3
        #
        # のようにページ情報をチャンクへ正確に引き継ぐ。
        #
        # ==================================================

        page_segments = (
            self._split_by_page(
                text
            )
        )

        chunks: list[
            DocumentChunk
        ] = []

        chunk_no = 1

        for (
            page_reference,
            page_text
        ) in page_segments:

            if not page_text.strip():

                continue

            # --------------------------------------------------
            # ページマーカーがある場合はそれを優先。
            #
            # ない場合はDocument metadataのpage_referenceを使用。
            # --------------------------------------------------

            effective_page_reference = (
                page_reference
                or document_page_reference
            )

            # --------------------------------------------------
            # ページ情報がページごとに正しく付与されるよう、
            # ページ単位でセグメント分割する。
            # --------------------------------------------------

            segments = (
                self._split_segments(
                    page_text
                )
            )

            for (
                is_code,
                segment_text
            ) in segments:

                if not segment_text.strip():

                    continue

                if is_code:

                    parts = (
                        self._split_code_segment(
                            segment_text
                        )
                    )

                    content_type = "code"

                    language = (
                        self._detect_language(
                            segment_text,
                            fallback_language
                        )
                    )

                else:

                    parts = (
                        self._split_text_segment(
                            segment_text
                        )
                    )

                    content_type = "text"

                    language = ""

                for part in parts:

                    if not part.strip():

                        continue

                    chunk_id = str(
                        uuid4()
                    )

                    # --------------------------------------------------
                    # Chunk metadata
                    # --------------------------------------------------

                    chunk_metadata = {
                        **metadata,

                        "document_id":
                            document_id,

                        "chunk_no":
                            chunk_no,

                        "chunk_id":
                            chunk_id,

                        "content_type":
                            content_type,

                        "language":
                            language
                    }

                    # --------------------------------------------------
                    # page_reference
                    # --------------------------------------------------
                    #
                    # ページ情報が存在する場合のみ設定。
                    #
                    # ページマーカーが存在する場合：
                    #     マーカーを優先
                    #
                    # マーカーがない場合：
                    #     Document metadataを使用
                    #
                    # --------------------------------------------------

                    if (
                        effective_page_reference
                        is not None
                    ):

                        chunk_metadata[
                            "page_reference"
                        ] = (
                            effective_page_reference
                        )

                    chunk = DocumentChunk(

                        chunk_id=chunk_id,

                        document_id=document_id,

                        chunk_no=chunk_no,

                        text=part,

                        metadata=chunk_metadata

                    )

                    chunks.append(
                        chunk
                    )

                    chunk_no += 1

        return chunks


chunk_service = ChunkService()