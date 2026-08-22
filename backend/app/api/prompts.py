from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from app.repositories.prompts import PromptNotFoundError, PromptStateConflictError
from app.schemas.prompt import PromptCreate, PromptRead, PromptUpdate
from app.services.prompts import PromptService, get_prompt_service

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


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


@router.get("", response_model=list[PromptRead])
def list_prompts(
    service: PromptService = Depends(get_prompt_service),
) -> list[PromptRead]:
    return service.list_prompts()


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
def execute_prompt(
    prompt_id: str,
    background_tasks: BackgroundTasks,
    service: PromptService = Depends(get_prompt_service),
) -> PromptRead:
    try:
        prompt = service.queue_execution(prompt_id)
    except (PromptNotFoundError, PromptStateConflictError) as error:
        raise_prompt_http_error(error)

    background_tasks.add_task(service.run_execution, prompt_id)
    return prompt
