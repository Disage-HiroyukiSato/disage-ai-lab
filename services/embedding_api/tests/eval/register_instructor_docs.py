"""

講師業務知識 一括登録スクリプト（Phase16）

data/documents/instructor_ops/ 配下のテキスト/PDFファイルを読み込み、

embedding_api の /documents エンドポイントへ
collection=instructor_ops として登録する。

register_java_documents.py と同様の構成だが、登録先コレクションが
instructor_ops である点、および .txt / .md ファイルも直接
登録対象とする点が異なる（FAQ・マニュアルはPDF化されていない
ケースも多いため）。

document_id はファイル名（拡張子除く）をそのまま使用する
（1ファイル = 1 document_id）。

category / keywords 等は、同ディレクトリの
documents_meta.json（ファイル名をキーとする辞書）から取得する。
定義が無いファイルはデフォルト値で登録する。

実行方法：

    python tests/eval/register_instructor_docs.py

    python tests/eval/register_instructor_docs.py \
        --dir data/documents/instructor_ops \
        --url http://localhost:8010

    # 特定の1ファイルのみ登録したい場合
    python tests/eval/register_instructor_docs.py \
        --file faq-001.pdf

"""

import argparse
import json
import sys

from pathlib import Path

import requests

try:

    import pdfplumber

except ImportError:

    pdfplumber = None


DEFAULT_DIR = "data/documents/instructor_ops"

DEFAULT_URL = "http://localhost:8010"

META_FILENAME = "documents_meta.json"

#
# 登録対象とする拡張子
#
# FAQ・マニュアルはPDF化されていないケースも多いため、
# テキストファイル・Markdownも直接登録対象とする。
#

SUPPORTED_EXTENSIONS = {

    ".pdf",

    ".txt",

    ".md"

}


#
# ------------------------------------------------------
# PDFテキスト抽出
# ------------------------------------------------------
#

def extract_pdf_text(

    pdf_path: Path

) -> str:

    if pdfplumber is None:

        raise RuntimeError(

            "pdfplumber がインストールされていません。"
            "pip install pdfplumber を実行してください。"

        )

    texts = []

    with pdfplumber.open(

        str(pdf_path)

    ) as pdf:

        for page_number, page in enumerate(

            pdf.pages,

            start=1

        ):

            page_text = page.extract_text()

            if not page_text:

                print(

                    f"[WARN] {pdf_path.name} "
                    f"page {page_number} : "
                    f"テキスト抽出結果が空です"
                    f"（スキャンPDFの可能性）",

                    file=sys.stderr

                )

                continue

            texts.append(

                page_text

            )

    return "\n\n".join(

        texts

    )


#
# ------------------------------------------------------
# テキスト/Markdownファイル読み込み
# ------------------------------------------------------
#

def extract_plain_text(

    file_path: Path

) -> str:

    return file_path.read_text(

        encoding="utf-8"

    )


def extract_text(

    file_path: Path

) -> str:

    suffix = file_path.suffix.lower()

    if suffix == ".pdf":

        return extract_pdf_text(

            file_path

        )

    return extract_plain_text(

        file_path

    )


#
# ------------------------------------------------------
# メタデータ定義読み込み
# ------------------------------------------------------
#

def load_meta_map(

    directory: Path

) -> dict:

    meta_path = directory / META_FILENAME

    if not meta_path.exists():

        print(

            f"[INFO] {META_FILENAME} が見つかりません。"
            f"全ファイルをデフォルトメタデータで登録します。"

        )

        return {}

    with meta_path.open(

        "r",

        encoding="utf-8"

    ) as fp:

        data = json.load(

            fp

        )

    data.pop(

        "_comment",

        None

    )

    return data


#
# ------------------------------------------------------
# 1ファイル登録
# ------------------------------------------------------
#

def register_file(

    base_url: str,

    file_path: Path,

    meta_map: dict

) -> bool:

    document_id = file_path.stem

    meta = meta_map.get(

        document_id,

        {}

    )

    try:

        text = extract_text(

            file_path

        )

    except Exception as ex:

        print(

            f"[NG] {document_id} : "
            f"テキスト抽出失敗 : {ex}",

            file=sys.stderr

        )

        return False

    if not text.strip():

        print(

            f"[NG] {document_id} : "
            f"抽出テキストが空です",

            file=sys.stderr

        )

        return False

    payload = {

        "document_id": document_id,

        "title": meta.get(

            "title",

            document_id

        ),

        "category": meta.get(

            "category",

            "InstructorOps"

        ),

        "keywords": meta.get(

            "keywords",

            ""

        ),

        "chapter": meta.get(

            "chapter",

            ""

        ),

        "section": meta.get(

            "section",

            ""

        ),

        "language": meta.get(

            "language",

            ""

        ),

        #
        # Phase16 : 複数コレクション対応
        #
        # 講師業務知識は常にinstructor_opsコレクションへ
        # 登録する。
        #

        "collection": "instructor_ops",

        "text": text

    }

    try:

        response = requests.post(

            f"{base_url}/documents",

            json=payload,

            timeout=300

        )

        response.raise_for_status()

        body = response.json()

        print(

            f"[OK] {document_id} "
            f"chunks={body.get('chunks')} "
            f"chars={len(text)}"

        )

        return True

    except Exception as ex:

        print(

            f"[NG] {document_id} : "
            f"登録APIエラー : {ex}",

            file=sys.stderr

        )

        return False


def main():

    parser = argparse.ArgumentParser(

        description="講師業務知識 一括登録"

    )

    parser.add_argument(

        "--dir",

        default=DEFAULT_DIR,

        help="対象ファイルが格納されたディレクトリ"

    )

    parser.add_argument(

        "--url",

        default=DEFAULT_URL,

        help="embedding_api のベースURL"

    )

    parser.add_argument(

        "--file",

        default=None,

        help="特定の1ファイルのみ登録する場合のファイル名"

    )

    args = parser.parse_args()

    directory = Path(

        args.dir

    )

    if not directory.exists():

        print(

            f"ディレクトリが存在しません : {directory}",

            file=sys.stderr

        )

        sys.exit(1)

    meta_map = load_meta_map(

        directory

    )

    if args.file:

        file_paths = [

            directory / args.file

        ]

    else:

        file_paths = sorted(

            path

            for path in directory.iterdir()

            if path.is_file()

            and path.suffix.lower() in SUPPORTED_EXTENSIONS

        )

    if not file_paths:

        print(

            "対象ファイルが見つかりません。"

        )

        sys.exit(1)

    print("----------------------------------------")
    print("講師業務知識 一括登録")
    print("----------------------------------------")
    print(f"Directory : {directory}")
    print(f"URL       : {args.url}")
    print(f"ファイル数 : {len(file_paths)}")
    print("----------------------------------------")

    success_count = 0

    for file_path in file_paths:

        if not file_path.exists():

            print(

                f"[NG] {file_path.name} : "
                f"ファイルが存在しません",

                file=sys.stderr

            )

            continue

        if register_file(

            args.url,

            file_path,

            meta_map

        ):

            success_count += 1

    print("----------------------------------------")
    print(

        f"登録結果 : {success_count} / {len(file_paths)}"

    )
    print("----------------------------------------")

    if success_count != len(file_paths):

        sys.exit(1)


if __name__ == "__main__":

    main()