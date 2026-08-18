import logging
import re

from sentence_transformers import CrossEncoder

from app.config import settings
from app.models.retrieval_item import RetrievalItem

logger = logging.getLogger(__name__)


class RerankerService:

    def __init__(self):

        self.model = None

    def get_model(self) -> CrossEncoder:

        if self.model is None:

            logger.info("----------------------------------------")
            logger.info("Loading Reranker Model")
            logger.info(
                "Model : %s",
                settings.rerank_model
            )

            self.model = CrossEncoder(

                settings.rerank_model

            )

            logger.info("Reranker Model Loaded")
            logger.info("----------------------------------------")

        return self.model

    def rerank(

        self,

        question: str,

        items: list[RetrievalItem],

        limit: int

    ) -> list[RetrievalItem]:

        #
        # 候補なし
        #

        if not items:

            logger.info(

                "Reranker skipped (0 candidates)"

            )

            return []

        logger.info("----------------------------------------")
        logger.info("Reranker Start")
        logger.info("----------------------------------------")

        logger.info(

            "Candidate Count : %d",

            len(items)

        )

        model = self.get_model()

        #
        # Question × Document
        #

        pairs = [

            (

                question,

                item.document

            )

            for item in items

        ]

        #
        # Score
        #

        scores = model.predict(

            pairs,

            batch_size=16,

            show_progress_bar=False

        )

        #
        # score設定
        #

        for item, score in zip(

            items,

            scores

        ):

            item.score = float(score)

        #
        # score降順
        #

        items.sort(

            key=lambda x: x.score,

            reverse=True

        )

        logger.info(

            "Min Score : %.4f",

            settings.min_rerank_score

        )

        filtered_items = []

        #
        # 最低スコアでフィルタ
        #

        for item in items:

            if item.score >= settings.min_rerank_score:

                filtered_items.append(

                    item

                )

        logger.info(

            "Filtered : %d -> %d",

            len(items),

            len(filtered_items)

        )

        #
        # limit適用
        #

        if limit > 0:

            filtered_items = filtered_items[:limit]

        #
        # ログ出力
        #

        logger.info("----------------------------------------")
        logger.info("Reranker Result")
        logger.info("----------------------------------------")

        for index, item in enumerate(

            filtered_items,

            start=1

        ):

            logger.info(

                "[%d]",

                index

            )

            logger.info(

                "Score    : %.4f",

                item.score

            )

            logger.info(

                "Distance : %.4f",

                item.distance

            )

            logger.info(

                "Metadata : %s",

                item.metadata

            )

            preview = item.document.replace(

                "\n",

                " "

            )

            logger.info(

                preview[:120]

            )

            logger.info("----------------------------------------")

        logger.info(

            "Returned : %d",

            len(filtered_items)

        )

        logger.info(

            "Reranker Finished"

        )

        return filtered_items

    #
    # ------------------------------------------------------
    # 目次（ドットリーダー）チャンクの検出
    # ------------------------------------------------------
    #
    # PDF由来のチャンクには「92.6.クラス変数 .....102」のような
    # 目次ページ（本文ではなくページ番号の索引）が含まれることが
    # ある。これらはCrossEncoderが「単語の並び」だけで高い
    # 関連度スコアを付けてしまい、Answerability Gateの判断材料を
    # 汚染するため、Gate向け候補（rerank_relaxed）からのみ
    # 除外する。
    #
    # ChromaDB/BM25側のデータそのものは変更しない
    # （通常のHybrid検索・完全一致検索では目次チャンクが
    # ヒットすること自体は問題ないため）。
    #
    # 判定基準：
    #   - "." が3つ以上連続するドットリーダーパターンが
    #     文中に2箇所以上出現する
    #   - または、文字列全体に占める "." の比率が高い
    #     （目次特有の高密度なドット羅列）
    #
    # 注記：
    #   UI操作手順・コード断片・演習の出力例なども、
    #   質問によってはCrossEncoderのスコアリングを歪める
    #   ノイズになりうる。しかし、これらは正当な説明文との
    #   境界が曖昧で、ルールベースでの汎用検出は誤検出
    #   （正当な内容の除外）リスクの方が高いと判断し、
    #   意図的に対象外とした。代わりにTOP_N（Gate候補数）を
    #   増やすことで、フィルタしきれないノイズが混ざっても
    #   本文が埋もれにくくする方針とする。
    #

    DOT_LEADER_PATTERN = re.compile(

        r"\.{3,}"

    )

    MIN_DOT_LEADER_OCCURRENCES = 2

    DOT_RATIO_THRESHOLD = 0.15

    #
    # 極端に短いチャンク（数字だけの断片等）は目次と同様、
    # 誤検出リスクが低く実害も明確なため対象に含める。
    #

    MIN_MEANINGFUL_LENGTH = 10

    def _is_toc_like(

        self,

        text: str

    ) -> bool:

        if not text:

            return False

        occurrences = len(

            self.DOT_LEADER_PATTERN.findall(

                text

            )

        )

        if occurrences >= self.MIN_DOT_LEADER_OCCURRENCES:

            return True

        dot_count = text.count(

            "."

        )

        if len(text) > 0:

            dot_ratio = dot_count / len(text)

            if dot_ratio >= self.DOT_RATIO_THRESHOLD:

                return True

        return False

    def _is_too_short(

        self,

        text: str

    ) -> bool:

        return len(

            text.strip()

        ) < self.MIN_MEANINGFUL_LENGTH

    def _is_noise_chunk(

        self,

        text: str

    ) -> bool:

        if self._is_too_short(

            text

        ):

            return True

        if self._is_toc_like(

            text

        ):

            return True

        return False

    #
    # ------------------------------------------------------
    # 緩和版Rerank（Answerability Gate向け）
    # ------------------------------------------------------
    #
    # 通常のrerank()はmin_rerank_score未満を機械的に
    # 足切りするが、CrossEncoderが短い無意味な文字列
    # （目次のドットリーダー等）に高いスコアを付け、
    # 本来関連度の高いチャンクを押し出してしまうケースがある。
    #
    # Answerability Gateはスコアの高低ではなく「実際に
    # 質問へ答えているか」をLLMで判定するため、
    # min_rerank_score未満であっても上位K件を判断材料として
    # 渡すことで、Reranker単体のスコアリング誤りを
    # Gateがカバーできるようにする。
    #
    # ただし、目次（ドットリーダー）チャンクはCrossEncoderの
    # スコアリングを特に汚染しやすいため、緩和候補からは
    # 明示的に除外する。
    #
    # 最終的にLLMへ渡す資料はrerank()側のmin_rerank_score
    # フィルタを経たものだけであり、この緩和版はGateの
    # 判定材料を増やす目的にのみ使用する。
    #
    # rerank()実行後、items（呼び出し元が保持する元の
    # リスト）にはitem.scoreが設定済みのため、
    # この関数はスコア降順で並び替えて上位limit件を
    # 返すだけの軽量な実装とする（CrossEncoderの
    # 再実行はしない）。
    #

    def rerank_relaxed(

        self,

        scored_items: list[RetrievalItem],

        limit: int

    ) -> list[RetrievalItem]:

        if not scored_items:

            return []

        #
        # 目次らしきアイテムを除外してからスコア降順に並び替える
        #

        filtered = [

            item

            for item in scored_items

            if not self._is_noise_chunk(

                item.document

            )

        ]

        excluded_count = len(

            scored_items

        ) - len(

            filtered

        )

        if excluded_count:

            logger.info(

                "rerank_relaxed : excluded %d noise item(s) "
                "(TOC/low-density/fragmented/too-short)",

                excluded_count

            )

        sorted_items = sorted(

            filtered,

            key=lambda x: x.score,

            reverse=True

        )

        if limit > 0:

            return sorted_items[:limit]

        return sorted_items


reranker_service = RerankerService()