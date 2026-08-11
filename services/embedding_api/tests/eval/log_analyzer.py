"""

検索ログ分析スクリプト

search_log_service が出力した JSON Lines ログ
（/app/data/search_log/*.jsonl）を集計し、

    - Hit率
    - 検索失敗分析（no_retrieval / rerank_filtered の内訳）
    - Rerank分析（順位変動の平均・分布）
    - Cache Hit率

を算出する。

コンテナ内（embedding_api）で実行することを想定。

実行方法：

    docker compose exec embedding-api \
        python /app/tests/eval/log_analyzer.py

    docker compose exec embedding-api \
        python /app/tests/eval/log_analyzer.py --date 2026-08-11

    docker compose exec embedding-api \
        python /app/tests/eval/log_analyzer.py --all

"""

import argparse
import json
import sys

from pathlib import Path

LOG_DIR = Path(

    "/app/data/search_log"

)


def load_records(

    date: str | None,

    use_all: bool

) -> list[dict]:

    if not LOG_DIR.exists():

        return []

    if use_all:

        paths = sorted(

            LOG_DIR.glob(

                "*.jsonl"

            )

        )

    elif date:

        paths = [

            LOG_DIR / f"{date}.jsonl"

        ]

    else:

        #
        # 指定なしの場合は最新ファイルのみ
        #

        candidates = sorted(

            LOG_DIR.glob(

                "*.jsonl"

            )

        )

        paths = (

            [candidates[-1]]

            if candidates

            else []

        )

    records = []

    for path in paths:

        if not path.exists():

            continue

        with path.open(

            "r",

            encoding="utf-8"

        ) as file:

            for line in file:

                line = line.strip()

                if not line:

                    continue

                try:

                    records.append(

                        json.loads(

                            line

                        )

                    )

                except json.JSONDecodeError:

                    continue

    return records


def summarize(

    records: list[dict]

) -> None:

    if not records:

        print(

            "対象ログが見つかりません。"

        )

        return

    total = len(
        records
    )

    #
    # Hit率
    #

    hit_count = sum(

        1

        for r in records

        if r.get("hit")

    )

    #
    # 検索失敗分析
    #

    failure_counts: dict[str, int] = {}

    for r in records:

        reason = r.get(

            "failure_reason",

            "unknown"

        )

        failure_counts[reason] = (

            failure_counts.get(
                reason,
                0
            )
            + 1
        )

    #
    # Cache Hit率
    #

    cache_hit_count = sum(

        1

        for r in records

        if r.get("cache_hit")

    )

    #
    # Rerank分析
    #
    # rank_deltaが記録されているitemのみ対象。
    #
    # rank_delta > 0 : Rerankで順位が上がった
    # rank_delta < 0 : Rerankで順位が下がった
    # rank_delta == 0: 変化なし
    #

    rank_deltas = []

    for r in records:

        for detail in r.get(
            "rerank_detail",
            []
        ):

            delta = detail.get(
                "rank_delta"
            )

            if delta is not None:

                rank_deltas.append(
                    delta
                )

    #
    # 処理時間平均
    #

    elapsed_totals = [

        r.get(
            "elapsed_ms",
            {}
        ).get(
            "total",
            0
        )

        for r in records

    ]

    elapsed_retrievals = [

        r.get(
            "elapsed_ms",
            {}
        ).get(
            "retrieval",
            0
        )

        for r in records

    ]

    print("========================================")
    print("検索ログ分析")
    print("========================================")
    print(f"対象レコード数     : {total}")
    print("")

    print("----------------------------------------")
    print("Hit率")
    print("----------------------------------------")
    print(
        f"Hit         : {hit_count} / {total} "
        f"({hit_count / total * 100:.1f}%)"
    )
    print("")

    print("----------------------------------------")
    print("検索失敗分析")
    print("----------------------------------------")

    for reason, count in sorted(

        failure_counts.items(),

        key=lambda x: -x[1]

    ):

        print(
            f"{reason:<18} : {count:>5} "
            f"({count / total * 100:.1f}%)"
        )

    print("")

    print("----------------------------------------")
    print("Search Cache")
    print("----------------------------------------")
    print(
        f"Cache Hit   : {cache_hit_count} / {total} "
        f"({cache_hit_count / total * 100:.1f}%)"
    )
    print("")

    print("----------------------------------------")
    print("Rerank分析（順位変動）")
    print("----------------------------------------")

    if rank_deltas:

        improved = sum(

            1

            for d in rank_deltas

            if d > 0

        )

        worsened = sum(

            1

            for d in rank_deltas

            if d < 0

        )

        unchanged = sum(

            1

            for d in rank_deltas

            if d == 0

        )

        average_delta = (

            sum(rank_deltas)
            / len(rank_deltas)
        )

        print(
            f"対象件数           : {len(rank_deltas)}"
        )

        print(
            f"順位上昇           : {improved}"
        )

        print(
            f"順位下降           : {worsened}"
        )

        print(
            f"変化なし           : {unchanged}"
        )

        print(
            f"平均順位変動        : {average_delta:+.2f}"
        )

    else:

        print(
            "Rerank詳細データがありません。"
        )

    print("")

    print("----------------------------------------")
    print("処理時間")
    print("----------------------------------------")

    if elapsed_totals:

        print(

            f"平均Total Time      : "
            f"{sum(elapsed_totals) / total:.1f} ms"

        )

    if elapsed_retrievals:

        print(

            f"平均Retrieval Time  : "
            f"{sum(elapsed_retrievals) / total:.1f} ms"

        )

    print("========================================")


def main():

    parser = argparse.ArgumentParser(

        description="検索ログ分析 (Hit率 / 検索失敗分析 / Rerank分析)"

    )

    parser.add_argument(

        "--date",

        type=str,

        default=None,

        help="対象日付 (YYYY-MM-DD)。省略時は最新ファイルのみ。"

    )

    parser.add_argument(

        "--all",

        action="store_true",

        help="全期間のログを対象とする。"

    )

    args = parser.parse_args()

    records = load_records(

        date=args.date,

        use_all=args.all

    )

    summarize(

        records

    )

    if not records:

        sys.exit(1)


if __name__ == "__main__":

    main()