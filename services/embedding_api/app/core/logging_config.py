import logging
import sys

from app.config import settings


LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(message)s"
)


def setup_logging():

    logging.basicConfig(

        level=getattr(

            logging,

            settings.log_level.upper(),

            logging.INFO

        ),

        format=LOG_FORMAT,

        stream=sys.stdout,

        force=True

    )

    #
    # uvicornのログ形式も統一
    #

    logging.getLogger("uvicorn").handlers = logging.getLogger().handlers

    logging.getLogger("uvicorn.access").handlers = logging.getLogger().handlers