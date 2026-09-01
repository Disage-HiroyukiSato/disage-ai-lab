import requests
import logging

from app.config import settings
from app.core.exceptions import LLMException

logger = logging.getLogger(__name__)

class LlmService:

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

    def ask(

        self,

        prompt: str

    ) -> str:

        chatml_prompt = self._wrap_chatml(
            prompt
        )

        try:
            response = requests.post(

                f"{settings.llm_url}/completion",

                json={

                    "prompt": chatml_prompt,

                    "n_predict": settings.max_tokens,

                    "temperature": settings.temperature,

                    "top_p": settings.top_p,

                    "repeat_penalty": settings.repeat_penalty,

                    "stop": [

                        "</s>",

                        "<|im_end|>",

                        "<|im_start|>"

                    ]

                },

                timeout=300

            )

        except Exception as ex:

            raise LLMException(

                str(ex)

            )

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
    # rewriter用モデルはJSON抽出のみに使われ、
    # 長文の自由生成を行わないため、現時点では
    # chatmlラップによる終端制御は必須ではないが、
    # 同様の繰り返し不具合を避けるため、
    # stop条件に "<|im_start|>" も追加しておく。
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