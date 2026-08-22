from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.prompts import router as prompts_router
from app.api.routes import router
from app.core.config import get_settings
from app.database import get_database
from app.repositories.prompts import get_prompt_repository
from app.services.agent import close_agent_service
from app.services.prompts import close_prompt_service

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_database().initialize()
    get_prompt_repository().recover_interrupted()
    try:
        yield
    finally:
        await close_prompt_service()
        await close_agent_service()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="OnMyWay 프롬프트 실행 보드의 FastAPI 백엔드",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

app.include_router(router)
app.include_router(prompts_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": settings.app_name, "docs": "/docs"}
