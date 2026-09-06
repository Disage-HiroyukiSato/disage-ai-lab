import json
import logging
import json
from contextlib import contextmanager

import requests

from app.config import settings
from app.core.exceptions import LLMException

logger = logging.getLogger(__name__)

class LlmService:
    @staticmethod
    def _read_tokens(response):
        """Parse llama.cpp /completion SSE; never accept a truncated answer."""
        data_lines = []
        for line in response.iter_lines(chunk_size=1, decode_unicode=False):
            line = line.decode("utf-8") if isinstance(line, bytes) else line
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
                continue
            if line != "" or not data_lines:
                continue
            raw = "\n".join(data_lines)
            data_lines.clear()
            if raw == "[DONE]":
                return
            event = json.loads(raw)
            if event.get("error"):
                raise LLMException("Upstream generation failed")
            content = event.get("content", "")
            if not isinstance(content, str):
                raise LLMException("Invalid upstream content")
            if content:
                yield content
            if event.get("stop"):
                return
        raise LLMException("Upstream stream ended without a terminal event")

    @contextmanager
    def stream(self, prompt):
        # Retain the existing raw completion API, ChatML and sampling settings.
        with requests.post(
            f"{settings.llm_url}/completion",
            json={
                "prompt": self._wrap_chatml(prompt),
                "n_predict": settings.max_tokens,
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "repeat_penalty": settings.repeat_penalty,
                "stop": ["</s>", "<|im_end|>", "<|im_start|>"],
                "stream": True,
            },
            stream=True,
            timeout=(10, 60),
        ) as response:
            response.raise_for_status()
            yield self._read_tokens(response)

    # ======================================================
    # Chat Template (chatml)
    # ======================================================
    #
    # llama-cppは --chat-template chatml で起動しているが、
    # ask()はllama.cppの/completion（raw補完API）を
    # 直接叩いているため、chatml形式のプロンプトへ
    # 明示的にラップしないと、モデルが
    # 会話の終端（<|im_end|>）を認識できない。
    #
    # 終端を認識できないと、stop=["</s>", "<|im_end|>"]が
    # 一度も出現せず、n_predict上限まで生成が続き、
    # 結果として同じ内容を繰り返す不具合が発生する
    # （実際に発生した障害）。
    #
    # /v1/chat/completions（OpenAI互換API）を使えば
    # サーバー側がテンプレートを適用してくれるが、
    # 既存の/completion運用・タイムアウト設計を
    # 変更しないため、ここでプロンプト側を
    # chatml形式に整形する。
    #
    # ======================================================
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
