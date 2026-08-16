import json
import logging
import re
import unicodedata

from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class CollectionRouterService:

    #
    # ------------------------------------------------------
    # Phase16 : Collection Router
    # ------------------------------------------------------
    #
    # ルールベース（キーワード辞書）で、質問文から
    # 検索対象コレクションを判定する。
    #
    # 判定結果は3通り：
    #
    #   java_training  : Javaキーワードのみ命中
    #   instructor_ops : 講師業務キーワードのみ命中
    #   both           : 両方命中、または両方とも未命中
    #                    （取りこぼし防止のフォールバック）
    #

    BOTH = "both"

    def __init__(self):

        self.dictionary: dict[str, list[str]] = {}

        self.loaded = False

    def _load_dictionary(self) -> None:

        if self.loaded:

            return

        dictionary_path = Path(

            settings.collection_router_dictionary

        )

        if not dictionary_path.exists():

            logger.warning(

                "Collection router dictionary not found : %s "
                "Falling back to 'both' for all queries.",

                dictionary_path

            )

            self.dictionary = {}

            self.loaded = True

            return

        try:

            with open(

                dictionary_path,

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

            self.dictionary = data

            logger.info(

                "Collection router dictionary loaded : %s "
                "(%s)",

                dictionary_path,

                {
                    key: len(value)
                    for key, value in data.items()
                }

            )

        except Exception:

            logger.exception(

                "Failed to load collection router dictionary."

            )

            self.dictionary = {}

        self.loaded = True

    #
    # ------------------------------------------------------
    # 正規化
    # ------------------------------------------------------
    #
    # 全角/半角、大文字/小文字の表記ゆれを吸収する。
    #

    def _normalize(

        self,

        text: str

    ) -> str:

        return unicodedata.normalize(

            "NFKC",

            text

        ).lower()

    #
    # ------------------------------------------------------
    # 判定
    # ------------------------------------------------------
    #
    # 戻り値 : "java_training" | "instructor_ops" | "both"
    #

    def route(

        self,

        question: str

    ) -> str:

        self._load_dictionary()

        if not self.dictionary:

            return self.BOTH

        normalized = self._normalize(

            question

        )

        java_keywords = self.dictionary.get(

            settings.collection_java_training,

            []

        )

        instructor_keywords = self.dictionary.get(

            settings.collection_instructor_ops,

            []

        )

        java_hit = any(

            self._normalize(keyword) in normalized

            for keyword in java_keywords

        )

        instructor_hit = any(

            self._normalize(keyword) in normalized

            for keyword in instructor_keywords

        )

        if java_hit and instructor_hit:

            decision = self.BOTH

        elif java_hit:

            decision = settings.collection_java_training

        elif instructor_hit:

            decision = settings.collection_instructor_ops

        else:

            #
            # どちらのキーワードにも一致しない場合は
            # 取りこぼし防止のため両方検索する。
            #

            decision = self.BOTH

        logger.info(

            "Collection Router : question=%s "
            "java_hit=%s instructor_hit=%s -> %s",

            question,

            java_hit,

            instructor_hit,

            decision

        )

        return decision


collection_router_service = CollectionRouterService()