import logging

from app.config import settings
from app.services.db_service import db_service

logger = logging.getLogger(__name__)


class ConversationService:

    #
    # ------------------------------------------------------
    # Phase17 : 会話履歴（Phase19前倒し実装分）
    # ------------------------------------------------------
    #
    # session_id単位で会話をPostgreSQLへ永続化する。
    #
    # マルチターン対話のプロンプト組み立て時は、
    # 直近N往復（settings.conversation_history_turns）のみを
    # 取得する。
    #

    def get_recent_turns(

        self,

        session_id: str | None,

        turns: int | None = None

    ) -> list[dict]:

        if not session_id:

            return []

        limit_turns = (

            turns

            if turns is not None

            else settings.conversation_history_turns

        )

        #
        # 1往復 = user + assistant の2レコードのため、
        # 取得件数は turns * 2 とする。
        #
        # created_at降順で直近分を取得し、
        # プロンプトへ渡す際は古い順に並び替える。
        #

        rows = db_service.fetch_all(

            "SELECT role, content, is_off_topic "
            "FROM conversation_history "
            "WHERE session_id = %s "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT %s",

            (

                session_id,

                limit_turns * 2

            )

        )

        if not rows:

            return []

        turns_list = [

            {

                "role": row[0],

                "content": row[1],

                "is_off_topic": row[2]

            }

            for row in rows

        ]

        #
        # created_at降順で取得したものを古い順に反転する。
        #

        turns_list.reverse()

        logger.info(

            "Conversation history loaded : "
            "session_id=%s turns=%d records=%d",

            session_id,

            limit_turns,

            len(turns_list)

        )

        return turns_list

    #
    # ------------------------------------------------------
    # 保存
    # ------------------------------------------------------
    #

    def append(

        self,

        session_id: str | None,

        student_id: str | None,

        role: str,

        content: str,

        is_off_topic: bool = False

    ) -> None:

        if not session_id:

            return

        success = db_service.execute(

            "INSERT INTO conversation_history "
            "(session_id, student_id, role, content, is_off_topic) "
            "VALUES (%s, %s, %s, %s, %s)",

            (

                session_id,

                student_id or "",

                role,

                content,

                is_off_topic

            )

        )

        if not success:

            logger.warning(

                "Failed to append conversation history : "
                "session_id=%s role=%s",

                session_id,

                role

            )


conversation_service = ConversationService()
