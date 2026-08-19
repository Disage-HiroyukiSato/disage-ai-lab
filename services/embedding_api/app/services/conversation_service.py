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


    #
    # ------------------------------------------------------
    # Phase19 : セッション一覧取得
    # ------------------------------------------------------
    #
    # student_id単位で、その受講生が持つセッションの一覧を
    # 取得する。各セッションについて、開始/終了日時、
    # 発話数、最初のuser発話（プレビュー用）を返す。
    #

    def get_sessions(

        self,

        student_id: str

    ) -> list[dict]:

        if not student_id:

            return []

        rows = db_service.fetch_all(

            "SELECT "
            "session_id, "
            "MIN(created_at) AS started_at, "
            "MAX(created_at) AS last_activity_at, "
            "COUNT(*) AS message_count, "
            "(SELECT content FROM conversation_history AS ch2 "
            " WHERE ch2.session_id = ch.session_id "
            " AND ch2.role = 'user' "
            " ORDER BY ch2.created_at ASC, ch2.id ASC "
            " LIMIT 1) AS first_question "
            "FROM conversation_history AS ch "
            "WHERE student_id = %s "
            "GROUP BY session_id "
            "ORDER BY MAX(created_at) DESC",

            (

                student_id,

            )

        )

        sessions = [

            {

                "session_id": row[0],

                "started_at": (

                    row[1].isoformat()

                    if row[1]

                    else None

                ),

                "last_activity_at": (

                    row[2].isoformat()

                    if row[2]

                    else None

                ),

                "message_count": row[3],

                "first_question": row[4] or ""

            }

            for row in rows

        ]

        logger.info(

            "Session list loaded : student_id=%s sessions=%d",

            student_id,

            len(sessions)

        )

        return sessions

    #
    # ------------------------------------------------------
    # Phase19 : セッション詳細取得
    # ------------------------------------------------------
    #
    # 指定されたsession_idの全会話を、古い順（時系列）で
    # 取得する。get_recent_turns()とは異なり、件数制限を
    # 設けず全件を返す（履歴閲覧用途のため）。
    #

    def get_session_detail(

        self,

        session_id: str

    ) -> list[dict]:

        if not session_id:

            return []

        rows = db_service.fetch_all(

            "SELECT role, content, is_off_topic, created_at "
            "FROM conversation_history "
            "WHERE session_id = %s "
            "ORDER BY created_at ASC, id ASC",

            (

                session_id,

            )

        )

        messages = [

            {

                "role": row[0],

                "content": row[1],

                "is_off_topic": row[2],

                "created_at": (

                    row[3].isoformat()

                    if row[3]

                    else None

                )

            }

            for row in rows

        ]

        logger.info(

            "Session detail loaded : session_id=%s messages=%d",

            session_id,

            len(messages)

        )

        return messages


conversation_service = ConversationService()