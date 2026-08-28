import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class QueryExpansionService:

    def __init__(self):

        self.dictionary = {}

        self.loaded = False

    def _load_dictionary(self) -> None:

        if self.loaded:

            return

        dictionary_path = Path(

            settings.query_dictionary

        )

        if not dictionary_path.exists():

            logger.warning(

                "Query dictionary not found : %s",

                dictionary_path

            )

            self.loaded = True

            self.dictionary = {}

            return

        try:

            with open(

                dictionary_path,

                "r",

                encoding="utf-8"

            ) as fp:

                self.dictionary = json.load(fp)

            logger.info(

                "Query dictionary loaded : %s (%d entries)",

                dictionary_path,

                len(self.dictionary)

            )

        except Exception:

            logger.exception(

                "Failed to load query dictionary."

            )

            self.dictionary = {}

        self.loaded = True

    def expand(

        self,

        question: str

    ) -> list[str]:

        #
        # Expansion無効
        #

        if not settings.enable_query_expansion:

            return [

                question

            ]

        self._load_dictionary()

        expanded = [

            question

        ]

        words = question.split()

        for word in words:

            synonyms = self.dictionary.get(

                word

            )

            if not synonyms:

                continue

            for synonym in synonyms:

                synonym = synonym.strip()

                if not synonym:

                    continue

                expanded.append(

                    question.replace(

                        word,

                        synonym

                    )

                )

        #
        # 重複除去
        #

        unique = []

        seen = set()

        for query in expanded:

            normalized = query.strip()

            if not normalized:

                continue

            if normalized in seen:

                continue

            seen.add(

                normalized

            )

            unique.append(

                normalized

            )

        #
        # 最大件数
        #

        if settings.expansion_limit > 0:

            unique = unique[

                :settings.expansion_limit

            ]

        logger.info(

            "Expanded Query Count : %d",

            len(unique)

        )

        for index, query in enumerate(

            unique,

            start=1

        ):

            logger.info(

                "[%d] %s",

                index,

                query

            )

        return unique


query_expansion_service = QueryExpansionService()