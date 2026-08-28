import logging

import psycopg2

from psycopg2 import pool

from app.config import settings

logger = logging.getLogger(__name__)


class DbService:

    #
    # ------------------------------------------------------
    # Phase17 : PostgreSQL接続プール
    # ------------------------------------------------------
    #
    # 接続失敗時にアプリ全体が落ちないよう、
    # プール生成は遅延させ、失敗時はNoneのまま
    # 呼び出し側で機能を無効化して動作を継続する
    # （cache_service.pyのRedis接続と同様の設計）。
    #

    def __init__(self):

        self._pool: "pool.SimpleConnectionPool | None" = None

        self.connection_failed = False

    def _get_pool(self) -> "pool.SimpleConnectionPool | None":

        if self._pool is not None:

            return self._pool

        if self.connection_failed:

            return None

        try:

            self._pool = psycopg2.pool.SimpleConnectionPool(

                1,

                10,

                host=settings.postgres_host,

                port=settings.postgres_port,

                dbname=settings.postgres_db,

                user=settings.postgres_user,

                password=settings.postgres_password,

                connect_timeout=3

            )

            logger.info(

                "PostgreSQL connection pool created : %s:%d/%s",

                settings.postgres_host,

                settings.postgres_port,

                settings.postgres_db

            )

        except Exception:

            logger.exception(

                "PostgreSQL connection failed. "
                "Progress/Conversation features disabled "
                "for this process."

            )

            self._pool = None

            self.connection_failed = True

        return self._pool

    #
    # ------------------------------------------------------
    # クエリ実行（SELECT）
    # ------------------------------------------------------
    #

    def fetch_all(

        self,

        query: str,

        params: tuple = ()

    ) -> list[tuple]:

        db_pool = self._get_pool()

        if db_pool is None:

            return []

        connection = None

        try:

            connection = db_pool.getconn()

            with connection.cursor() as cursor:

                cursor.execute(

                    query,

                    params

                )

                return cursor.fetchall()

        except Exception:

            logger.exception(

                "PostgreSQL fetch_all failed : %s",

                query

            )

            return []

        finally:

            if connection is not None:

                db_pool.putconn(

                    connection

                )

    #
    # ------------------------------------------------------
    # クエリ実行（INSERT/UPDATE等、更新系）
    # ------------------------------------------------------
    #

    def execute(

        self,

        query: str,

        params: tuple = ()

    ) -> bool:

        db_pool = self._get_pool()

        if db_pool is None:

            return False

        connection = None

        try:

            connection = db_pool.getconn()

            with connection.cursor() as cursor:

                cursor.execute(

                    query,

                    params

                )

            connection.commit()

            return True

        except Exception:

            logger.exception(

                "PostgreSQL execute failed : %s",

                query

            )

            if connection is not None:

                connection.rollback()

            return False

        finally:

            if connection is not None:

                db_pool.putconn(

                    connection

                )


db_service = DbService()
