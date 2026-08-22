from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.services.agent import close_agent_service

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await close_agent_service()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Matdathon AI 에이전트 웹의 FastAPI 백엔드",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": settings.app_name, "docs": "/docs"}
