import json
import logging
import unicodedata

from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class OffTopicRouterService:

    #
    # ------------------------------------------------------
    # Phase17 : 教材外判定
    # ------------------------------------------------------
    #
    # collection_router_service.pyと同様のルールベース
    # （キーワード辞書）方式で、質問がJava教材の範囲内かを
    # 判定する。
    #
    # in_scopeキーワードに1つも一致しない場合、
    # 教材外の質問と判定する。
    #
    # 辞書ファイルが存在しない場合は、安全側に倒して
    # 常に「教材内」と判定する（誤って教材外ラベルを
    # 大量に付与しないため）。
    #

    def __init__(self):

        self.dictionary: dict[str, list[str]] = {}

        self.loaded = False

    def _load_dictionary(self) -> None:

        if self.loaded:

            return

        dictionary_path = Path(

            settings.off_topic_dictionary

        )

        if not dictionary_path.exists():

            logger.warning(

                "Off-topic dictionary not found : %s. "
                "All questions will be treated as in-scope.",

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

                "Off-topic dictionary loaded : %s (%d keywords)",

                dictionary_path,

                len(

                    data.get(
                        "in_scope",
                        []
                    )
                )

            )

        except Exception:

            logger.exception(

                "Failed to load off-topic dictionary."

            )

            self.dictionary = {}

        self.loaded = True

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
    # 戻り値 : True の場合、教材外の質問と判定
    #

    def is_off_topic(

        self,

        question: str

    ) -> bool:

        self._load_dictionary()

        in_scope_keywords = self.dictionary.get(

            "in_scope",

            []

        )

        #
        # 辞書が空（未定義）の場合は判定不能のため、
        # 教材外と誤判定しないよう常にFalseを返す。
        #

        if not in_scope_keywords:

            return False

        normalized = self._normalize(

            question

        )

        hit = any(

            self._normalize(keyword) in normalized

            for keyword in in_scope_keywords

        )

        result = not hit

        logger.info(

            "Off-topic Router : question=%s -> "
            "is_off_topic=%s",

            question,

            result

        )

        return result


off_topic_router_service = OffTopicRouterService()
