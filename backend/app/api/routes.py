from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse
from app.services.agent import (
    AgentServiceError,
    CopilotAgentService,
    get_agent_service,
)

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.app_env,
    )


@router.post("/agent/chat", response_model=ChatResponse, tags=["agent"])
async def chat(
    payload: ChatRequest,
    service: CopilotAgentService = Depends(get_agent_service),
) -> ChatResponse:
    try:
        result = await service.reply(payload.message, payload.thread_id)
    except AgentServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatResponse(
        reply=result.reply,
        thread_id=result.thread_id,
        provider=result.provider,
    )
