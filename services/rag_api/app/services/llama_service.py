import httpx

from app.config import settings


class LlamaService:

    def __init__(self):

        self.base_url = settings.llm_url

        self.timeout = settings.api_timeout

    async def chat_completion(self, payload: dict):

        try:

            async with httpx.AsyncClient(timeout=self.timeout) as client:

                response = await client.post(

                    f"{self.base_url}/v1/chat/completions",

                    json=payload

                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as ex:

            raise RuntimeError(

                f"llama.cpp API Error : {ex}"

            ) from ex

    async def models(self):

        try:

            async with httpx.AsyncClient(timeout=30) as client:

                response = await client.get(

                    f"{self.base_url}/v1/models"

                )

                response.raise_for_status()

                return response.json()

        except httpx.HTTPError as ex:

            raise RuntimeError(

                f"llama.cpp API Error : {ex}"

            ) from ex


llama_service = LlamaService()