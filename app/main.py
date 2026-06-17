"""RaiRai Subnet Validator API entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import responses, tasks
from app.core.config import settings
from app.core.migrations import init_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting {} — creating DB schema if missing", settings.app_name)
    await init_models()
    yield
    logger.info("Shutting down {}", settings.app_name)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(responses.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": settings.app_name}
