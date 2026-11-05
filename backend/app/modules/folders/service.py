import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folder import Folder
from app.repositories.activity_repository import ActivityRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.workspace_repository import WorkspaceRepository


class FolderService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._activity = ActivityRepository(db)
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

    async def _require_folder(self, folder_id: uuid.UUID, subject_id: uuid.UUID) -> Folder:
        folder = await self._folders.get_for_subject(folder_id=folder_id, subject_id=subject_id)
        if folder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "FOLDER_NOT_FOUND", "message": "Folder not found."},
            )
        return folder

    async def list_folders(
        self,
        *,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None = None,
        include_archived: bool = False,
        all_levels: bool = False,
    ) -> list[Folder]:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        return await self._folders.list_for_subject(
            subject_id=subject_id,
            parent_folder_id=parent_folder_id,
            include_archived=include_archived,
            all_levels=all_levels,
        )

    async def get_folder(
        self,
        *,
        folder_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Folder:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        return await self._require_folder(folder_id, subject_id)

    async def create_folder(
        self,
        *,
        workspace_id: uuid.UUID,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        parent_folder_id: uuid.UUID | None = None,
        description: str | None = None,
        display_order: int = 0,
    ) -> Folder:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)

        # Validate parent belongs to same subject
        if parent_folder_id is not None:
            parent = await self._folders.get_for_subject(
                folder_id=parent_folder_id, subject_id=subject_id
            )
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "FOLDER_NOT_FOUND", "message": "Parent folder not found."},
                )

        # D-14: check depth
        parent_depth = await self._folders.get_depth(parent_folder_id)
        if parent_depth >= self._folders.max_depth:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "FOLDER_DEPTH_EXCEEDED",
                    "message": f"Maximum folder depth of {self._folders.max_depth} exceeded.",
                },
            )

        # D-11: name uniqueness per parent
        if await self._folders.name_exists(
            subject_id=subject_id, name=name, parent_folder_id=parent_folder_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "FOLDER_NAME_CONFLICT",
                    "message": "A folder with this name already exists at this level.",
                },
            )

        folder = await self._folders.create(
            subject_id=subject_id,
            name=name,
            parent_folder_id=parent_folder_id,
            description=description,
            display_order=display_order,
        )
        await self._activity.record(
            user_id=user_id,
            action="created",
            entity_type="folder",
            entity_id=folder.id,
            entity_name=folder.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(folder)
        return folder

    async def update_folder(
        self,
        *,
        folder_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        display_order: int | None = None,
        parent_folder_id: uuid.UUID | None = None,
        parent_folder_id_set: bool = False,
    ) -> Folder:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        folder = await self._require_folder(folder_id, subject_id)

        moving = parent_folder_id_set and parent_folder_id != folder.parent_folder_id
        if moving:
            await self._validate_move(folder, parent_folder_id, subject_id)

        target_parent = parent_folder_id if moving else folder.parent_folder_id
        new_name = name if name is not None else folder.name
        if (name is not None and name != folder.name) or moving:
            if await self._folders.name_exists(
                subject_id=subject_id,
                name=new_name,
                parent_folder_id=target_parent,
                exclude_id=folder_id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "FOLDER_NAME_CONFLICT",
                        "message": "A folder with this name already exists at this level.",
                    },
                )

        folder = await self._folders.update(
            folder,
            name=name,
            description=description,
            display_order=display_order,
            parent_folder_id=parent_folder_id,
            parent_folder_id_set=moving,
        )
        await self._activity.record(
            user_id=user_id,
            action="updated",
            entity_type="folder",
            entity_id=folder.id,
            entity_name=folder.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(folder)
        return folder

    async def _validate_move(
        self, folder: Folder, new_parent_id: uuid.UUID | None, subject_id: uuid.UUID
    ) -> None:
        """D-14: same subject, never into itself or a descendant, subtree must fit in 3 levels."""
        if new_parent_id is None:
            return  # top level is always allowed; name uniqueness is checked by the caller
        parent = await self._folders.get_for_subject(folder_id=new_parent_id, subject_id=subject_id)
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "FOLDER_NOT_FOUND", "message": "Parent folder not found."},
            )
        if await self._folders.is_self_or_descendant(
            candidate_id=new_parent_id, folder_id=folder.id
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "FOLDER_INVALID_MOVE",
                    "message": "A folder cannot be moved into itself or one of its own subfolders.",
                },
            )
        parent_depth = await self._folders.get_depth(new_parent_id)
        subtree_height = await self._folders.get_subtree_height(folder.id)
        if parent_depth + subtree_height > self._folders.max_depth:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "FOLDER_DEPTH_EXCEEDED",
                    "message": (
                        f"Maximum folder depth of {self._folders.max_depth} exceeded: the folder "
                        "and its subfolders would not fit at that location."
                    ),
                },
            )

    async def archive_folder(
        self,
        *,
        folder_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Folder:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        folder = await self._require_folder(folder_id, subject_id)
        if folder.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "ALREADY_ARCHIVED", "message": "Folder is already archived."},
            )
        folder = await self._folders.archive(folder)
        await self._activity.record(
            user_id=user_id,
            action="archived",
            entity_type="folder",
            entity_id=folder.id,
            entity_name=folder.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(folder)
        return folder

    async def restore_folder(
        self,
        *,
        folder_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Folder:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        folder = await self._folders.get_for_subject(folder_id=folder_id, subject_id=subject_id)
        if folder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "FOLDER_NOT_FOUND", "message": "Folder not found."},
            )
        if folder.archived_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "NOT_ARCHIVED", "message": "Folder is not archived."},
            )
        if await self._folders.name_exists(
            subject_id=subject_id,
            name=folder.name,
            parent_folder_id=folder.parent_folder_id,
            exclude_id=folder_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "FOLDER_NAME_CONFLICT",
                    "message": "A folder with this name already exists. Rename before restoring.",
                },
            )
        folder = await self._folders.restore(folder)
        await self._activity.record(
            user_id=user_id,
            action="restored",
            entity_type="folder",
            entity_id=folder.id,
            entity_name=folder.name,
            workspace_id=workspace_id,
        )
        await self._db.commit()
        await self._db.refresh(folder)
        return folder

    async def delete_folder(
        self,
        *,
        folder_id: uuid.UUID,
        subject_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        cascade: bool = False,
    ) -> None:
        await self._require_workspace(workspace_id, user_id)
        await self._require_subject(subject_id, workspace_id)
        folder = await self._require_folder(folder_id, subject_id)
        # D-12: refuse delete if folder has children unless cascade=true
        if not cascade and await self._folders.has_children(folder_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "FOLDER_NOT_EMPTY",
                    "message": "Folder has children. Use ?cascade=true to delete all inside.",
                },
            )
        await self._activity.record(
            user_id=user_id,
            action="deleted",
            entity_type="folder",
            entity_id=folder.id,
            entity_name=folder.name,
            workspace_id=workspace_id,
        )
        await self._folders.delete(folder)
        await self._db.commit()
