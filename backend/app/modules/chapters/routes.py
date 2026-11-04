import uuid
from typing import Literal

from fastapi import APIRouter, Query

from app.core.dependencies import ActiveUser, DbSession
from app.modules.chapters.schemas import (
    ChapterListResponse,
    ChapterOut,
    ChapterResponse,
    CreateChapterRequest,
    ReorderChaptersRequest,
    UpdateChapterRequest,
)
from app.modules.chapters.service import ChapterService

router = APIRouter(tags=["chapters"])

_MAX_LIMIT = 200


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters",
    response_model=ChapterListResponse,
)
async def list_chapters(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
    folder_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=255),
    sort_by: Literal["display_order", "title", "updated_at"] = Query(default="display_order"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ChapterListResponse:
    service = ChapterService(db)
    chapters, total = await service.list_chapters(
        workspace_id=workspace_id,
        subject_id=subject_id,
        user_id=current_user.id,
        folder_id=folder_id,
        folder_filter_set=folder_id is not None,
        include_archived=include_archived,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return ChapterListResponse(
        data=[ChapterOut.model_validate(c) for c in chapters],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters",
    response_model=ChapterResponse,
    status_code=201,
)
async def create_chapter(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    data: CreateChapterRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> ChapterResponse:
    service = ChapterService(db)
    chapter = await service.create_chapter(
        workspace_id=workspace_id,
        subject_id=subject_id,
        user_id=current_user.id,
        title=data.title,
        folder_id=data.folder_id,
        description=data.description,
        display_order=data.display_order,
        chapter_status=data.status,
    )
    return ChapterResponse(data=ChapterOut.model_validate(chapter))


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters/reorder",
    status_code=200,
)
async def reorder_chapters(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    data: ReorderChaptersRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> dict[str, object]:
    """D-15: reorder chapters within a subject/folder in one transaction."""
    service = ChapterService(db)
    await service.reorder_chapters(
        workspace_id=workspace_id,
        subject_id=subject_id,
        user_id=current_user.id,
        chapter_ids=data.chapter_ids,
    )
    return {"success": True, "data": None}


@router.get(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters/{chapter_id}",
    response_model=ChapterResponse,
)
async def get_chapter(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    chapter_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> ChapterResponse:
    service = ChapterService(db)
    chapter = await service.get_chapter(
        chapter_id=chapter_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return ChapterResponse(data=ChapterOut.model_validate(chapter))


@router.patch(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters/{chapter_id}",
    response_model=ChapterResponse,
)
async def update_chapter(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    chapter_id: uuid.UUID,
    data: UpdateChapterRequest,
    current_user: ActiveUser,
    db: DbSession,
) -> ChapterResponse:
    service = ChapterService(db)
    chapter = await service.update_chapter(
        chapter_id=chapter_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
        title=data.title,
        description=data.description,
        folder_id=data.folder_id,
        folder_id_set=data.folder_id_set,
        display_order=data.display_order,
        chapter_status=data.status,
    )
    return ChapterResponse(data=ChapterOut.model_validate(chapter))


@router.delete(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters/{chapter_id}",
    status_code=204,
)
async def delete_chapter(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    chapter_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> None:
    service = ChapterService(db)
    await service.delete_chapter(
        chapter_id=chapter_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters/{chapter_id}/archive",
    response_model=ChapterResponse,
)
async def archive_chapter(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    chapter_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> ChapterResponse:
    service = ChapterService(db)
    chapter = await service.archive_chapter(
        chapter_id=chapter_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return ChapterResponse(data=ChapterOut.model_validate(chapter))


@router.post(
    "/workspaces/{workspace_id}/subjects/{subject_id}/chapters/{chapter_id}/restore",
    response_model=ChapterResponse,
)
async def restore_chapter(
    workspace_id: uuid.UUID,
    subject_id: uuid.UUID,
    chapter_id: uuid.UUID,
    current_user: ActiveUser,
    db: DbSession,
) -> ChapterResponse:
    service = ChapterService(db)
    chapter = await service.restore_chapter(
        chapter_id=chapter_id,
        subject_id=subject_id,
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    return ChapterResponse(data=ChapterOut.model_validate(chapter))
