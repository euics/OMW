from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
import json

from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.repositories.prompts import PromptNotFoundError, PromptStateConflictError
from app.schemas.prompt import (
    PromptBoard,
    PromptCreate,
    PromptPage,
    PromptRead,
    PromptStatus,
    PromptUpdate,
)
from app.services.prompts import PromptService, get_prompt_service

router = APIRouter(prefix="/api/prompts", tags=["prompts"])
settings = get_settings()
execution_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.execute_rate_limit,
    window_seconds=settings.execute_rate_window_seconds,
)


def enforce_execution_rate_limit(request: Request) -> None:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.rsplit(",", 1)[-1].strip()
    if not client_ip and request.client:
        client_ip = request.client.host

    allowed, retry_after = execution_rate_limiter.allow(client_ip or "unknown")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="실행 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(retry_after)},
        )


def raise_prompt_http_error(error: Exception) -> None:
    if isinstance(error, PromptNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="프롬프트를 찾을 수 없습니다.",
        ) from error
    if isinstance(error, PromptStateConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    raise error


def _sse_event(event: object) -> str:
    payload = event.model_dump(by_alias=True) if hasattr(event, "model_dump") else event
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/board", response_model=PromptBoard)
def get_prompt_board(
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    service: PromptService = Depends(get_prompt_service),
) -> PromptBoard:
    return service.get_board(page_size)


@router.get("", response_model=PromptPage)
def list_prompts(
    prompt_status: PromptStatus = Query(alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    service: PromptService = Depends(get_prompt_service),
) -> PromptPage:
    return service.list_prompts(prompt_status, page, page_size)


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptCreate,
    service: PromptService = Depends(get_prompt_service),
) -> PromptRead:
    return service.create_prompt(payload)


@router.patch("/{prompt_id}", response_model=PromptRead)
def update_prompt(
    prompt_id: str,
    payload: PromptUpdate,
    service: PromptService = Depends(get_prompt_service),
) -> PromptRead:
    try:
        return service.update_prompt(prompt_id, payload)
    except (PromptNotFoundError, PromptStateConflictError) as error:
        raise_prompt_http_error(error)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(
    prompt_id: str,
    service: PromptService = Depends(get_prompt_service),
) -> Response:
    try:
        service.delete_prompt(prompt_id)
    except (PromptNotFoundError, PromptStateConflictError) as error:
        raise_prompt_http_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{prompt_id}/execute",
    response_model=PromptRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def execute_prompt(
    prompt_id: str,
    request: Request,
    service: PromptService = Depends(get_prompt_service),
) -> PromptRead:
    enforce_execution_rate_limit(request)
    try:
        prompt = await service.start_execution(prompt_id)
    except (PromptNotFoundError, PromptStateConflictError) as error:
        raise_prompt_http_error(error)
    return prompt


@router.post(
    "/{prompt_id}/cancel",
    response_model=PromptRead,
    status_code=status.HTTP_200_OK,
)
async def cancel_prompt(
    prompt_id: str,
    service: PromptService = Depends(get_prompt_service),
) -> PromptRead:
    try:
        return await service.cancel_execution(prompt_id)
    except (PromptNotFoundError, PromptStateConflictError) as error:
        raise_prompt_http_error(error)


@router.get("/{prompt_id}/events")
async def stream_prompt_events(
    prompt_id: str,
    service: PromptService = Depends(get_prompt_service),
) -> StreamingResponse:
    try:
        service.get_prompt(prompt_id)
    except PromptNotFoundError as error:
        raise_prompt_http_error(error)

    async def event_stream():
        async for event in service.stream_prompt_events(prompt_id):
            yield _sse_event(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
