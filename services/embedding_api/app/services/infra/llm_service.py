import json
import logging

import requests

from app.config import settings
from app.core.exceptions import LLMException

logger = logging.getLogger(__name__)


class LlmService:

    SYSTEM_PROMPT = (
        "あなたはJava研修受講生向けのAI学習アシスタントです。"
    )

    def _wrap_chatml(
        self,
        prompt: str
    ) -> str:

        return (
            f"<|im_start|>system\n{self.SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def _completion_payload(
        self,
        prompt: str,
        *,
        stream: bool
    ) -> dict:

        return {
            "prompt": self._wrap_chatml(prompt),
            "n_predict": settings.max_tokens,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "repeat_penalty": settings.repeat_penalty,
            "stop": [
                "</s>",
                "<|im_end|>",
                "<|im_start|>"
            ],
            "stream": stream
        }

    def ask(
        self,
        prompt: str
    ) -> str:

        try:
            response = requests.post(
                f"{settings.llm_url}/completion",
                json=self._completion_payload(
                    prompt,
                    stream=False
                ),
                timeout=300
            )
        except Exception as ex:
            raise LLMException(str(ex)) from ex

        logger.info(
            "LLM Status : %d",
            response.status_code
        )
        logger.info(
            "LLM Response : %s",
            response.text[:1000]
        )
        logger.info(
            "LLM URL : %s",
            settings.llm_url
        )

        response.raise_for_status()
        body = response.json()
        return body["content"].strip()

    def ask_stream(
        self,
        prompt: str
    ):
        """Yield llama.cpp completion text fragments as they arrive."""

        try:
            with requests.post(
                f"{settings.llm_url}/completion",
                json=self._completion_payload(
                    prompt,
                    stream=True
                ),
                timeout=(10, 300),
                stream=True
            ) as response:

                response.raise_for_status()

                for raw_line in response.iter_lines(
                    decode_unicode=True
                ):
                    if not raw_line:
                        continue

                    line = raw_line.strip()

                    if line.startswith("data:"):
                        line = line[5:].strip()

                    if not line or line == "[DONE]":
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug(
                            "Ignored non-JSON LLM stream line: %s",
                            line[:200]
                        )
                        continue

                    content = payload.get("content")
                    if content:
                        yield content

                    if payload.get("stop") is True:
                        break

        except Exception as ex:
            raise LLMException(str(ex)) from ex

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
                    "<|im_end|>",
                    "<|im_start|>"
                ]
            },
            timeout=settings.llm_rewriter_timeout
        )

        response.raise_for_status()
        body = response.json()
        return body["content"].strip()


llm_service = LlmService()
