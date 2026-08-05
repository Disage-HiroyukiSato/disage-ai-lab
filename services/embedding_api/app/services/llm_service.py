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


llm_service = LlmService()