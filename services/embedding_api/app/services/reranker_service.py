import logging

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


reranker_service = RerankerService()