from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.prompts import router as prompts_router
from app.api.routes import router
from app.core.config import get_settings
from app.database import get_database
from app.repositories.prompts import get_prompt_repository
from app.services.agent import AgentServiceProvider

settings = get_settings()

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
}


async def add_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    agent_service_provider = AgentServiceProvider()
    app.state.agent_service_provider = agent_service_provider
    try:
        agent_service_provider.get()
        get_database().initialize()
        get_prompt_repository().recover_interrupted()
        yield
    finally:
        await agent_service_provider.close()
        del app.state.agent_service_provider


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
app.add_middleware(BaseHTTPMiddleware, dispatch=add_security_headers)

app.include_router(router)
app.include_router(prompts_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": settings.app_name, "docs": "/docs"}
