import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject import Subject
from app.repositories.activity_repository import ActivityRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.workspace_repository import WorkspaceRepository


class SubjectService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._activity = ActivityRepository(db)
        self._subjects = SubjectRepository(db)
        self._workspaces = WorkspaceRepository(db)

    async def _require_workspace(self, workspace_id: uuid.UUID, user_id: uuid.UUID):  # type: ignore[return]
        """Return workspace or 404 — ownership is enforced here."""
        ws = await self._workspaces.get_for_user(workspace_id=workspace_id, user_id=user_id)
        if ws is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found."},
            )
        return ws

    async def _require_subject(self, subject_id: uuid.UUID, workspace_id: uuid.UUID) -> Subject:
        """Return subject scoped to workspace or 404."""
        subject = await self._subjects.get_for_workspace(
            subject_id=subject_id, workspace_id=workspace_id
        )
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SUBJECT_NOT_FOUND", "message": "Subject not found."},
            )
        return subject

    async def list_subjects(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        include_archived: bool = False,
        q: str | None = None,
        sort_by: str = "name",
        sort_dir: str = "asc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Subject], int]:
        await self._require_workspace(workspace_id, user_id)
        return await self._subjects.list_for_workspace(
            workspace_id=workspace_id,
            include_archived=include_archived,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    async def get_subject(
        self, *, subject_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Subject:
        await self._require_workspace(workspace_id, user_id)
        return await self._require_subject(subject_id, workspace_id)

    async def create_subject(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None = None,
        colour: str | None = None,
        icon: str | None = None,
    ) -> Subject:
        await self._require_workspace(workspace_id, user_id)
        if await self._subjects.name_exists(workspace_id=workspace_id, name=name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SUBJECT_NAME_CONFLICT",
                    "message": "A subject with this name already exists in this workspace.",
                },
            )
        subject = await self._subjects.create(
            workspace_id=workspace_id,
            name=name,
            description=description,
            colour=colour,
            icon=icon,
        )
        await self._activity.record(
            user_id=user_id,
            action="created",
            entity_type="subject",
            entity_id=subject.id,
            entity_name=subject.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(subject)
        return subject

    async def update_subject(
        self,
        *,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        colour: str | None = None,
        icon: str | None = None,
    ) -> Subject:
        await self._require_workspace(workspace_id, user_id)
        subject = await self._require_subject(subject_id, workspace_id)

        if name is not None and name != subject.name:
            if await self._subjects.name_exists(
                workspace_id=workspace_id, name=name, exclude_id=subject_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "SUBJECT_NAME_CONFLICT",
                        "message": "A subject with this name already exists in this workspace.",
                    },
                )

        subject = await self._subjects.update(
            subject,
            name=name,
            description=description,
            colour=colour,
            icon=icon,
        )
        await self._activity.record(
            user_id=user_id,
            action="updated",
            entity_type="subject",
            entity_id=subject.id,
            entity_name=subject.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(subject)
        return subject

    async def archive_subject(
        self, *, subject_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Subject:
        await self._require_workspace(workspace_id, user_id)
        subject = await self._require_subject(subject_id, workspace_id)
        if subject.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "ALREADY_ARCHIVED", "message": "Subject is already archived."},
            )
        subject = await self._subjects.archive(subject)
        await self._activity.record(
            user_id=user_id,
            action="archived",
            entity_type="subject",
            entity_id=subject.id,
            entity_name=subject.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(subject)
        return subject

    async def restore_subject(
        self, *, subject_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Subject:
        await self._require_workspace(workspace_id, user_id)
        # Allow lookup of archived subjects for restore
        subject = await self._subjects.get_for_workspace(
            subject_id=subject_id, workspace_id=workspace_id
        )
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SUBJECT_NOT_FOUND", "message": "Subject not found."},
            )
        if subject.archived_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "NOT_ARCHIVED", "message": "Subject is not archived."},
            )
        # Check name conflict on restore (D-11)
        if await self._subjects.name_exists(
            workspace_id=workspace_id, name=subject.name, exclude_id=subject_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "SUBJECT_NAME_CONFLICT",
                    "message": "A subject with this name already exists. Rename before restoring.",
                },
            )
        subject = await self._subjects.restore(subject)
        await self._activity.record(
            user_id=user_id,
            action="restored",
            entity_type="subject",
            entity_id=subject.id,
            entity_name=subject.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(subject)
        return subject

    async def delete_subject(
        self, *, subject_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        await self._require_workspace(workspace_id, user_id)
        subject = await self._require_subject(subject_id, workspace_id)
        await self._activity.record(
            user_id=user_id,
            action="deleted",
            entity_type="subject",
            entity_id=subject.id,
            entity_name=subject.name,
            workspace_id=workspace_id,
        )
        await self._subjects.delete(subject)
        await self._db.commit()
