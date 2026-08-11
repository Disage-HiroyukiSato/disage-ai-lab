import hashlib
import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:

    #
    # ------------------------------------------------------
    # Redis接続
    # ------------------------------------------------------
    #
    # 接続失敗時にアプリ全体が落ちないよう、
    # クライアント生成は遅延させ、失敗時はNoneのまま
    # キャッシュ無効として動作を継続する。
    #

    def __init__(self):

        self.client: redis.Redis | None = None

        self.connection_failed = False

    def _get_client(self) -> "redis.Redis | None":

        if self.client is not None:

            return self.client

        if self.connection_failed:

            return None

        try:

            self.client = redis.Redis(

                host=settings.redis_host,

                port=settings.redis_port,

                db=settings.redis_db,

                socket_timeout=2,

                socket_connect_timeout=2,

                decode_responses=True

            )

            #
            # 接続確認
            #

            self.client.ping()

            logger.info(

                "Redis connected : %s:%d db=%d",

                settings.redis_host,

                settings.redis_port,

                settings.redis_db

            )

        except Exception:

            logger.exception(

                "Redis connection failed. "
                "Search cache disabled for this process."

            )

            self.client = None

            self.connection_failed = True

        return self.client

    #
    # ------------------------------------------------------
    # Cache Key生成
    # ------------------------------------------------------
    #
    # question + limit + フィルタ条件（document_id等）を
    # 全て含めてハッシュ化する。
    #
    # 条件が1つでも異なれば別キャッシュとして扱う。
    #

    def build_key(

        self,

        question: str,

        limit: int,

        document_id: str | None = None,

        category: str | None = None,

        title: str | None = None,

        keywords: str | None = None

    ) -> str:

        payload = {

            "question": question,

            "limit": limit,

            "document_id": document_id,

            "category": category,

            "title": title,

            "keywords": keywords

        }

        serialized = json.dumps(

            payload,

            ensure_ascii=False,

            sort_keys=True

        )

        digest = hashlib.sha256(

            serialized.encode("utf-8")

        ).hexdigest()

        return f"{settings.cache_key_prefix}{digest}"

    #
    # ------------------------------------------------------
    # 取得
    # ------------------------------------------------------
    #

    def get(

        self,

        key: str

    ) -> dict | None:

        client = self._get_client()

        if client is None:

            return None

        try:

            raw = client.get(key)

        except Exception:

            logger.exception(

                "Cache get failed : %s",

                key

            )

            return None

        if raw is None:

            return None

        try:

            return json.loads(raw)

        except Exception:

            logger.exception(

                "Cache value decode failed : %s",

                key

            )

            return None

    #
    # ------------------------------------------------------
    # 保存
    # ------------------------------------------------------
    #

    def set(

        self,

        key: str,

        value: dict,

        ttl: int | None = None

    ) -> None:

        client = self._get_client()

        if client is None:

            return

        ttl = (

            ttl

            if ttl is not None

            else settings.cache_ttl

        )

        try:

            serialized = json.dumps(

                value,

                ensure_ascii=False

            )

            if ttl > 0:

                client.setex(

                    key,

                    ttl,

                    serialized

                )

            else:

                client.set(

                    key,

                    serialized

                )

        except Exception:

            logger.exception(

                "Cache set failed : %s",

                key

            )

    #
    # ------------------------------------------------------
    # 全削除（LRU的な運用はRedis側のmaxmemory-policyに委譲）
    # ------------------------------------------------------
    #
    # 文書登録・更新時に呼び出し、古い検索結果が
    # 残らないようにするためのユーティリティ。
    #
    # prefix配下の全キーを削除する。
    #

    def clear_all(self) -> int:

        client = self._get_client()

        if client is None:

            return 0

        deleted = 0

        try:

            pattern = f"{settings.cache_key_prefix}*"

            for key in client.scan_iter(

                match=pattern,

                count=100

            ):

                client.delete(key)

                deleted += 1

        except Exception:

            logger.exception(

                "Cache clear_all failed."

            )

        if deleted:

            logger.info(

                "Cache cleared : %d keys",

                deleted

            )

        return deleted


cache_service = CacheService()