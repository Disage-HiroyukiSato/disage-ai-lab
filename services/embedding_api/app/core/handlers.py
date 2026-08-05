import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import DisageException


logger = logging.getLogger(__name__)


async def disage_exception_handler(

    request: Request,

    exc: DisageException

):

    logger.error(

        "%s : %s",

        request.url.path,

        exc.message

    )

    return JSONResponse(

        status_code=exc.status_code,

        content={

            "success": False,

            "message": exc.message

        }

    )


async def unexpected_exception_handler(

    request: Request,

    exc: Exception

):

    logger.exception(exc)

    return JSONResponse(

        status_code=500,

        content={

            "success": False,

            "message": "Internal Server Error"

        }

    )