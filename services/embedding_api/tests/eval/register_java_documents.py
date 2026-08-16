"""

Java教材PDF 一括登録スクリプト（Phase15）

data/documents/java/*.pdf を読み込み、pdfplumberでテキスト抽出した上で

embedding_api の /documents エンドポイントへ登録する。

document_id はファイル名（拡張子除く）をそのまま使用する
（1PDF = 1 document_id）。

chapter / section / category / keywords / language は、
同ディレクトリの documents_meta.json（ファイル名をキーとする
辞書）から取得する。定義が無いPDFはデフォルト値で登録する。

実行方法：

    python tests/eval/register_java_documents.py

    python tests/eval/register_java_documents.py \
        --dir data/documents/java \
        --url http://localhost:8010

    # 特定の1ファイルのみ登録したい場合
    python tests/eval/register_java_documents.py \
        --file java-training-001.pdf

"""

import argparse
import json
import sys

from pathlib import Path

import requests

try:

    import pdfplumber

except ImportError:

    print(

        "pdfplumber がインストールされていません。"
        "pip install pdfplumber を実行してください。",

        file=sys.stderr

    )

    sys.exit(1)


DEFAULT_DIR = "data/documents/java"

DEFAULT_URL = "http://localhost:8010"

META_FILENAME = "documents_meta.json"


#
# ------------------------------------------------------
# PDFテキスト抽出
# ------------------------------------------------------
#
# pdfplumberでページ単位にテキストを抽出し、
# ページ間はダブル改行で連結する。
#
# レイアウト崩れによりコードのインデントが失われる
# ケースがあるが、chunk_service側のインデント検出
# ロジックがある程度カバーする。
#

def extract_pdf_text(

    pdf_path: Path

) -> str:

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
            f"全PDFをデフォルトメタデータで登録します。"

        )

        return {}

    with meta_path.open(

        "r",

        encoding="utf-8"

    ) as fp:

        data = json.load(

            fp

        )

    #
    # コメント用キーは除外
    #

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

def register_pdf(

    base_url: str,

    pdf_path: Path,

    meta_map: dict

) -> bool:

    document_id = pdf_path.stem

    meta = meta_map.get(

        document_id,

        {}

    )

    try:

        text = extract_pdf_text(

            pdf_path

        )

    except Exception as ex:

        print(

            f"[NG] {document_id} : "
            f"PDFテキスト抽出失敗 : {ex}",

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

            "Java"

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

            "java"

        ),

        #
        # Phase16 : 複数コレクション対応
        #
        # Java教材は常にjava_trainingコレクションへ
        # 登録する。
        #

        "collection": "java_training",

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

        description="Java教材PDF 一括登録"

    )

    parser.add_argument(

        "--dir",

        default=DEFAULT_DIR,

        help="PDFファイルが格納されたディレクトリ"

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

        pdf_paths = [

            directory / args.file

        ]

    else:

        pdf_paths = sorted(

            directory.glob(

                "*.pdf"

            )

        )

    if not pdf_paths:

        print(

            "対象PDFファイルが見つかりません。"

        )

        sys.exit(1)

    print("----------------------------------------")
    print("Java教材PDF 一括登録")
    print("----------------------------------------")
    print(f"Directory : {directory}")
    print(f"URL       : {args.url}")
    print(f"PDF数     : {len(pdf_paths)}")
    print("----------------------------------------")

    success_count = 0

    for pdf_path in pdf_paths:

        if not pdf_path.exists():

            print(

                f"[NG] {pdf_path.name} : "
                f"ファイルが存在しません",

                file=sys.stderr

            )

            continue

        if register_pdf(

            args.url,

            pdf_path,

            meta_map

        ):

            success_count += 1

    print("----------------------------------------")
    print(

        f"登録結果 : {success_count} / {len(pdf_paths)}"

    )
    print("----------------------------------------")

    if success_count != len(pdf_paths):

        sys.exit(1)


if __name__ == "__main__":

    main()