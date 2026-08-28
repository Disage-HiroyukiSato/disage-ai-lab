import logging

from app.services.infra.db_service import db_service

logger = logging.getLogger(__name__)


class ProgressService:

    #
    # ------------------------------------------------------
    # Phase17 : 進捗管理（参照専用）
    # ------------------------------------------------------
    #
    # student_progressテーブルは外部の進捗管理システムが
    # 更新する前提のため、このサービスは参照（SELECT）のみ
    # 提供する。RAG側からのINSERT/UPDATEは行わない。
    #

    def get_current_chapter(

        self,

        student_id: str | None

    ) -> str:

        if not student_id:

            return ""

        rows = db_service.fetch_all(

            "SELECT current_chapter "
            "FROM student_progress "
            "WHERE student_id = %s",

            (

                student_id,

            )

        )

        if not rows:

            logger.info(

                "No progress record for student_id=%s. "
                "Chapter boost disabled for this request.",

                student_id

            )

            return ""

        current_chapter = rows[0][0] or ""

        logger.info(

            "Progress lookup : student_id=%s "
            "current_chapter=%s",

            student_id,

            current_chapter

        )

        return current_chapter


progress_service = ProgressService()
