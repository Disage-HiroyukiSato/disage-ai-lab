import re


class QueryNormalizer:

    def normalize(

        self,

        question: str

    ) -> str:

        #
        # 前後空白除去
        #

        text = question.strip()

        #
        # 全角スペース
        #

        text = text.replace(

            "　",

            " "

        )

        #
        # 小文字化
        #

        text = text.lower()

        #
        # 不要語除去
        #

        stop_words = [

            "について",

            "教えて",

            "とは",

            "ですか",

            "ください",

            "お願い",

            "知りたい"

        ]

        for word in stop_words:

            text = text.replace(

                word,

                ""

            )

        #
        # 記号除去
        #

        text = re.sub(

            r"[？?！!。、,]",

            "",

            text

        )

        #
        # 連続スペース除去
        #

        text = re.sub(

            r"\s+",

            " ",

            text

        )

        return text.strip()


query_normalizer = QueryNormalizer()