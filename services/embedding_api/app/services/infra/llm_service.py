import requests

from app.config import settings


class LlmService:

    def ask(

        self,

        prompt: str

    ) -> str:

        try:
            response = requests.post(

                f"{settings.llm_url}/completion",

                json={

                    "prompt": prompt,

                    "n_predict": settings.max_tokens,

                    "temperature": settings.temperature,

                    "top_p": settings.top_p,

                    "repeat_penalty": settings.repeat_penalty,

                    "stop": [

                        "</s>",

                        "<|im_end|>"

                    ]

                },

                timeout=300

            )
        except Exception as ex:

            raise LLMException(

                str(ex)

            )

        response.raise_for_status()

        body = response.json()

        return body["content"].strip()

    #
    # ------------------------------------------------------
    # Phase17 : Query Rewriting専用（軽量モデル）
    # ------------------------------------------------------
    #
    # メイン回答生成用のask()とは別のLLMエンドポイント
    # （llama-rewriterコンテナ）を叩く。
    #
    # Query Rewritingは短い応答で十分なため、n_predictを
    # 小さめに制限し、タイムアウトも短く設定する
    # （settings.llm_rewriter_timeout）。
    #
    # 呼び出し元（query_rewrite_service）で例外を
    # キャッチしてフォールバックする設計のため、
    # ここでは例外をそのまま送出する。
    #

    def ask_rewriter(

        self,

        prompt: str

    ) -> str:

        response = requests.post(

            f"{settings.llm_rewriter_url}/completion",

            json={

                "prompt": prompt,

                "n_predict": 128,

                "temperature": 0.1,

                "top_p": 0.9,

                "repeat_penalty": 1.1,

                "stop": [

                    "</s>",

                    "<|im_end|>"

                ]

            },

            timeout=settings.llm_rewriter_timeout

        )

        response.raise_for_status()

        body = response.json()

        return body["content"].strip()


llm_service = LlmService()