"""

検索品質評価スクリプト

dataset.json の各質問について MultiQueryRetrievalService で検索を行い、

    - Recall@K
    - Precision@K
    - MRR (Mean Reciprocal Rank)

を算出する。

コンテナ内（embedding_api）で実行することを想定。

実行方法：

    docker compose exec embedding-api \
        python /app/tests/eval/evaluate.py

    docker compose exec embedding-api \
        python /app/tests/eval/evaluate.py --k 5

"""

import argparse
import json
import sys
from pathlib import Path

# app パッケージを import できるようにする
sys.path.append(

    str(

        Path(__file__).resolve().parents[2]

    )

)

from app.services.multi_query_retrieval_service import (  # noqa: E402
    multi_query_retrieval_service
)

DATASET_PATH = Path(__file__).parent / "dataset.json"


def load_dataset() -> dict:

    with open(

        DATASET_PATH,

        "r",

        encoding="utf-8"

    ) as fp:

        return json.load(fp)


def extract_document_ids(

    items

) -> list[str]:

    """

    RetrievalItem のリストから document_id のリストを抽出する。

    metadata に document_id が無い場合は None を除外する。

    """

    document_ids = []

    for item in items:

        metadata = item.metadata or {}

        document_id = metadata.get(

            "document_id"

        )

        if document_id:

            document_ids.append(

                str(document_id)

            )

    return document_ids


def evaluate_case(

    question: str,

    relevant_ids: list[str],

    k: int

) -> dict:

    """

    1件の質問を評価する。

    Returns:
        dict : recall, precision, reciprocal_rank, retrieved_ids

    """

    result = multi_query_retrieval_service.search(

        question=question,

        limit=k

    )

    retrieved_ids = extract_document_ids(

        result.items

    )

    relevant_set = set(

        relevant_ids

    )

    #
    # Hit判定
    #

    hits = [

        document_id

        for document_id in retrieved_ids

        if document_id in relevant_set

    ]

    #
    # Recall@K
    #
    # 正解集合のうち何割を上位K件で拾えたか
    #

    recall = (

        len(set(hits)) / len(relevant_set)

        if relevant_set else 0.0

    )

    #
    # Precision@K
    #
    # 取得したK件のうち何割が正解だったか
    #

    precision = (

        len(hits) / len(retrieved_ids)

        if retrieved_ids else 0.0

    )

    #
    # Reciprocal Rank
    #
    # 最初に正解が現れた順位の逆数
    #

    reciprocal_rank = 0.0

    for rank, document_id in enumerate(

        retrieved_ids,

        start=1

    ):

        if document_id in relevant_set:

            reciprocal_rank = 1.0 / rank

            break

    return {

        "recall": recall,

        "precision": precision,

        "reciprocal_rank": reciprocal_rank,

        "retrieved_ids": retrieved_ids

    }


def main():

    parser = argparse.ArgumentParser(

        description="検索品質評価 (Recall@K / Precision@K / MRR)"

    )

    parser.add_argument(

        "--k",

        type=int,

        default=5,

        help="評価対象の取得件数 (デフォルト:5)"

    )

    args = parser.parse_args()

    k = args.k

    dataset = load_dataset()

    cases = dataset.get(

        "cases",

        []

    )

    if not cases:

        print(

            "評価ケースが見つかりません。"

        )

        sys.exit(1)

    print("========================================")
    print("検索品質評価")
    print("========================================")
    print(f"K (取得件数)   : {k}")
    print(f"評価ケース数   : {len(cases)}")
    print("========================================")
    print("")

    recalls = []
    precisions = []
    reciprocal_ranks = []

    for index, case in enumerate(

        cases,

        start=1

    ):

        question = case["question"]

        relevant_ids = case[

            "relevant_document_ids"

        ]

        metrics = evaluate_case(

            question,

            relevant_ids,

            k

        )

        recalls.append(

            metrics["recall"]

        )

        precisions.append(

            metrics["precision"]

        )

        reciprocal_ranks.append(

            metrics["reciprocal_rank"]

        )

        print(

            f"[{index}/{len(cases)}] {question}"

        )

        print(

            f"  正解      : {relevant_ids}"

        )

        print(

            f"  取得結果  : {metrics['retrieved_ids']}"

        )

        print(

            f"  Recall@{k}    : {metrics['recall']:.3f}"

        )

        print(

            f"  Precision@{k} : {metrics['precision']:.3f}"

        )

        print(

            f"  RR        : {metrics['reciprocal_rank']:.3f}"

        )

        print("")

    #
    # 集計
    #

    mean_recall = (

        sum(recalls) / len(recalls)

        if recalls else 0.0

    )

    mean_precision = (

        sum(precisions) / len(precisions)

        if precisions else 0.0

    )

    mrr = (

        sum(reciprocal_ranks) / len(reciprocal_ranks)

        if reciprocal_ranks else 0.0

    )

    print("========================================")
    print("評価結果サマリ")
    print("========================================")
    print(

        f"Mean Recall@{k}    : {mean_recall:.3f}"

    )
    print(

        f"Mean Precision@{k} : {mean_precision:.3f}"

    )
    print(

        f"MRR             : {mrr:.3f}"

    )
    print("========================================")


if __name__ == "__main__":

    main()