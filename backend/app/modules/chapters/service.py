import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.repositories.chapter_repository import ChapterRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.workspace_repository import WorkspaceRepository


class ChapterService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._chapters = ChapterRepository(db)
        self._folders = FolderRepository(db)
        self._subjects = SubjectRepository(db)
        self._workspaces = WorkspaceRepository(db)

    async def _require_workspace(self, workspace_id: uuid.UUID, user_id: uuid.UUID):  # type: ignore[return]
        ws = await self._workspaces.get_for_user(workspace_id=workspace_id, user_id=user_id)
        if ws is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found."},
            )
        return ws

    async def _require_subject(self, subject_id: uuid.UUID, workspace_id: uuid.UUID):  # type: ignore[return]
        subj = await self._subjects.get_for_workspace(
            subject_id=subject_id, workspace_id=workspace_id
        )
        if subj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SUBJECT_NOT_FOUND", "message": "Subject not found."},
            )
        return subj

    async def _require_chapter(self, chapter_id: uuid.UUID, subject_id: uuid.UUID) -> Chapter:
        chapter = await self._chapters.get_for_subject(chapter_id=chapter_id, subject_id=subject_id)
        if chapter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CHAPTER_NOT_FOUND", "message": "Chapter not found."},
            )
        return chapter

    async def _validate_folder(self, folder_id: uuid.UUID | None, subject_id: uuid.UUID) -> None:
        if folder_id is not None:
            folder = await self._folders.get_for_subject(folder_id=folder_id, subject_id=subject_id)
            if folder is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "FOLDER_NOT_FOUND", "message": "Folder not found."},
                )

    async def list_chapters(
        self,
        *,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
        folder_filter_set: bool = False,
        include_archived: bool = False,
        q: str | None = None,
        sort_by: str = "display_order",
        sort_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Chapter], int]:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        return await self._chapters.list_for_subject(
            subject_id=subject_id,
            folder_id=folder_id,
            folder_filter_set=folder_filter_set,
            include_archived=include_archived,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    async def get_chapter(
        self,
        *,
        chapter_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Chapter:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        return await self._require_chapter(chapter_id, subject_id)

    async def create_chapter(
        self,
        *,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        folder_id: uuid.UUID | None = None,
        description: str | None = None,
        display_order: int = 0,
        chapter_status: str = "not_started",
    ) -> Chapter:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        await self._validate_folder(folder_id, subject_id)
        chapter = await self._chapters.create(
            subject_id=subject_id,
            title=title,
            folder_id=folder_id,
            description=description,
            display_order=display_order,
            status=chapter_status,
        )
        await self._db.commit()
        await self._db.refresh(chapter)
        return chapter

    async def update_chapter(
        self,
        *,
        chapter_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
        description: str | None = None,
        folder_id: uuid.UUID | None = None,
        folder_id_set: bool = False,
        display_order: int | None = None,
        chapter_status: str | None = None,
    ) -> Chapter:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        chapter = await self._require_chapter(chapter_id, subject_id)
        if folder_id_set:
            await self._validate_folder(folder_id, subject_id)
        chapter = await self._chapters.update(
            chapter,
            title=title,
            description=description,
            folder_id=folder_id,
            folder_id_set=folder_id_set,
            display_order=display_order,
            status=chapter_status,
        )
        await self._db.commit()
        await self._db.refresh(chapter)
        return chapter

    async def reorder_chapters(
        self,
        *,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        chapter_ids: list[uuid.UUID],
    ) -> None:
        """D-15: gap-free reorder within a subject."""
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        await self._chapters.bulk_reorder(subject_id=subject_id, chapter_ids=chapter_ids)
        await self._db.commit()

    async def archive_chapter(
        self,
        *,
        chapter_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Chapter:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        chapter = await self._require_chapter(chapter_id, subject_id)
        if chapter.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "ALREADY_ARCHIVED", "message": "Chapter is already archived."},
            )
        chapter = await self._chapters.archive(chapter)
        await self._db.commit()
        await self._db.refresh(chapter)
        return chapter

    async def restore_chapter(
        self,
        *,
        chapter_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Chapter:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        chapter = await self._chapters.get_for_subject(chapter_id=chapter_id, subject_id=subject_id)
        if chapter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CHAPTER_NOT_FOUND", "message": "Chapter not found."},
            )
        if chapter.archived_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "NOT_ARCHIVED", "message": "Chapter is not archived."},
            )
        chapter = await self._chapters.restore(chapter)
        await self._db.commit()
        await self._db.refresh(chapter)
        return chapter

    async def delete_chapter(
        self,
        *,
        chapter_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        chapter = await self._require_chapter(chapter_id, subject_id)
        await self._chapters.delete(chapter)
        await self._db.commit()
