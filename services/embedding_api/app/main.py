from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.handlers import (
    disage_exception_handler,
    unexpected_exception_handler
)

from app.core.exceptions import DisageException

from app.config import settings

from app.routers.health import router as health_router
from app.routers.embedding import router as embedding_router
from app.routers.document import router as document_router
from app.routers.retrieval import router as retrieval_router
from app.routers.query import router as query_router
from app.routers.web import router as web_router
from app.core.logging_config import setup_logging

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("========================================")
    print(" DisageAI Embedding API")
    print("========================================")
    print(f"Embedding Model : {settings.embedding_model}")
    print(f"Chroma Host     : {settings.chroma_host}")
    print(f"Chroma Port     : {settings.chroma_port}")
    print(f"Collection      : {settings.chroma_collection}")
    print("========================================")
    print("Embedding API Started")

    yield

    print("Embedding API Stopped")


app = FastAPI(

    title="DisageAI Embedding API",

    version="1.0.0",

    lifespan=lifespan

)

app.add_exception_handler(

    DisageException,

    disage_exception_handler

)

app.add_exception_handler(

    Exception,

    unexpected_exception_handler

)

app.include_router(

    health_router

)

app.include_router(

    embedding_router

)

app.include_router(

    document_router

)

app.include_router(

    retrieval_router

)

app.include_router(

    query_router

)

app.mount(

    "/static",

    StaticFiles(

        directory=BASE_DIR / "static"

    ),

    name="static"

)

templates = Jinja2Templates(

    directory=BASE_DIR / "templates"

)

app.include_router(

    web_router

)