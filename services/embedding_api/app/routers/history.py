from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query

from app.services.conversation_service import conversation_service


router = APIRouter(

    prefix="/history",

    tags=[

        "History"

    ]

)


#
# ------------------------------------------------------
# Phase19 : セッション一覧
# ------------------------------------------------------
#
# student_id単位で、その受講生のセッション一覧を返す。
#
# 各セッションについて、開始/終了日時・発話数・
# 最初の質問プレビューを含む。
#

@router.get(

    "/sessions"

)

async def get_sessions(

    student_id: str = Query(

        ...,

        description="受講生ID"

    )

):

    sessions = conversation_service.get_sessions(

        student_id

    )

    return {

        "success": True,

        "student_id": student_id,

        "total": len(sessions),

        "sessions": sessions

    }


#
# ------------------------------------------------------
# Phase19 : セッション詳細
# ------------------------------------------------------
#
# 指定したsession_idの全会話（時系列）を返す。
#

@router.get(

    "/sessions/{session_id}"

)

async def get_session_detail(

    session_id: str

):

    messages = conversation_service.get_session_detail(

        session_id

    )

    if not messages:

        raise HTTPException(

            status_code=404,

            detail={

                "success": False,

                "message": (

                    "指定されたセッションが見つかりません、"
                    "または会話履歴が存在しません。"

                )

            }

        )

    return {

        "success": True,

        "session_id": session_id,

        "total": len(messages),

        "messages": messages

    }