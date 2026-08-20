import logging

from app.config import settings
from app.services.db_service import db_service

logger = logging.getLogger(__name__)


class ConversationService:

    #
    # ------------------------------------------------------
    # Phase17 : 会話履歴
    # ------------------------------------------------------
    #
    # session_id単位で会話をPostgreSQLへ永続化する。
    #
    # 会話履歴にはuser / assistantの両方を保存する。
    #
    # 用途に応じて、以下の2種類の取得方法を提供する。
    #
    # 1. get_recent_turns()
    #    Query Rewrite等、会話全体の文脈が必要な処理で使用する。
    #
    # 2. get_recent_questions()
    #    最終回答生成時に使用する。
    #    過去のassistant回答本文をLLMへ再投入せず、
    #    受講生の質問だけを会話文脈として渡す。
    #
    # これにより、
    #
    #   過去のassistant回答
    #          ↓
    #   最終Promptへ再投入
    #          ↓
    #   同じ回答を再生成
    #
    # というループを防止する。
    #

    # ------------------------------------------------------
    # 会話全体を取得
    # ------------------------------------------------------

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
        # 1往復 = user + assistant の2レコード。
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

    # ------------------------------------------------------
    # 受講生の質問だけを取得
    # ------------------------------------------------------
    #
    # 最終回答生成用。
    #
    # assistantの過去回答本文は取得しない。
    #
    # これにより、過去の回答内容が今回の回答生成時の
    # 「回答テンプレート」や「回答根拠」として再利用される
    # ことを防ぐ。
    #
    # ただし、過去の受講生質問は残すことで、
    #
    #   「それについて」
    #   「上の内容」
    #   「この場合」
    #
    # のような会話上の文脈を維持できる。
    #

    def get_recent_questions(
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
        # assistantレコードを除外し、
        # userレコードだけを取得する。
        #
        # 1質問 = 1レコードなので、
        # turnsそのものをLIMITに使用する。
        #

        rows = db_service.fetch_all(
            "SELECT role, content, is_off_topic "
            "FROM conversation_history "
            "WHERE session_id = %s "
            "AND role = 'user' "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT %s",
            (
                session_id,
                limit_turns
            )
        )

        if not rows:
            return []

        questions = [
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

        questions.reverse()

        logger.info(
            "Conversation questions loaded : "
            "session_id=%s questions=%d",
            session_id,
            len(questions)
        )

        return questions

    # ------------------------------------------------------
    # 保存
    # ------------------------------------------------------

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