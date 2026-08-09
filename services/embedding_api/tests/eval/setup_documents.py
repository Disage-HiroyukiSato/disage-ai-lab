"""

評価用ダミー文書登録スクリプト

dataset.json に定義された documents を
embedding_api の /documents エンドポイントへ登録する。

実行方法：

    python tests/eval/setup_documents.py

    python tests/eval/setup_documents.py --url http://localhost:8010

"""

import argparse
import json
import sys
from pathlib import Path

import requests

DATASET_PATH = Path(__file__).parent / "dataset.json"

DEFAULT_URL = "http://localhost:8010"


def load_dataset() -> dict:

    with open(

        DATASET_PATH,

        "r",

        encoding="utf-8"

    ) as fp:

        return json.load(fp)


def register_document(

    base_url: str,

    document: dict

) -> bool:

    try:

        response = requests.post(

            f"{base_url}/documents",

            json={

                "document_id": document["document_id"],

                "title": document.get("title", ""),

                "category": document.get("category", "General"),

                "keywords": document.get("keywords", ""),

                "text": document["text"]

            },

            timeout=60

        )

        response.raise_for_status()

        body = response.json()

        print(

            f"[OK] {document['document_id']} "
            f"chunks={body.get('chunks')}"

        )

        return True

    except Exception as ex:

        print(

            f"[NG] {document['document_id']} : {ex}",

            file=sys.stderr

        )

        return False


def main():

    parser = argparse.ArgumentParser(

        description="評価用ダミー文書登録"

    )

    parser.add_argument(

        "--url",

        default=DEFAULT_URL,

        help="embedding_api のベースURL"

    )

    args = parser.parse_args()

    dataset = load_dataset()

    documents = dataset.get(

        "documents",

        []

    )

    print("----------------------------------------")
    print("評価用ダミー文書登録")
    print("----------------------------------------")
    print(f"URL      : {args.url}")
    print(f"Documents: {len(documents)}")
    print("----------------------------------------")

    success_count = 0

    for document in documents:

        if register_document(

            args.url,

            document

        ):

            success_count += 1

    print("----------------------------------------")
    print(

        f"登録結果 : {success_count} / {len(documents)}"

    )
    print("----------------------------------------")

    if success_count != len(documents):

        sys.exit(1)


if __name__ == "__main__":

    main()