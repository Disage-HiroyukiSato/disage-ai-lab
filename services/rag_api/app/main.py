from fastapi import FastAPI

from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.routers.models import router as models_router


app = FastAPI(

    title="DisageAI RAG API",

    version="1.0.0"

)

app.include_router(health_router)

app.include_router(chat_router)

app.include_router(models_router)