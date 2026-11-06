"""Dashboard read queries. Every query is scoped to the owner via workspaces.user_id (rule 3)."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, String, cast, func, literal, null, select, union_all
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.chapter import Chapter
from app.models.folder import Folder
from app.models.subject import Subject
from app.models.workspace import Workspace


@dataclass(frozen=True)
class WorkspaceOverviewRow:
    workspace: Workspace
    subject_count: int


@dataclass(frozen=True)
class RecentSubjectRow:
    subject: Subject
    workspace_name: str


@dataclass(frozen=True)
class ArchivedRow:
    item_type: str
    id: uuid.UUID
    name: str
    archived_at: datetime
    workspace_id: uuid.UUID
    workspace_name: str
    subject_id: uuid.UUID | None
    subject_name: str | None


class DashboardRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ---- counts -------------------------------------------------------------------------

    async def count_workspaces(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count(Workspace.id)).where(Workspace.user_id == user_id)
        return (await self._db.execute(stmt)).scalar_one()

    async def count_subjects(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(Subject.id))
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
        )
        return (await self._db.execute(stmt)).scalar_one()

    async def count_folders(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(Folder.id))
            .join(Subject, Folder.subject_id == Subject.id)
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
        )
        return (await self._db.execute(stmt)).scalar_one()

    async def chapter_status_counts(self, user_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(Chapter.status, func.count(Chapter.id))
            .join(Subject, Chapter.subject_id == Subject.id)
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
            .group_by(Chapter.status)
        )
        return dict((await self._db.execute(stmt)).tuples().all())

    # ---- activity -----------------------------------------------------------------------

    async def list_activity(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ActivityLog], int]:
        total = (
            await self._db.execute(
                select(func.count(ActivityLog.id)).where(ActivityLog.user_id == user_id)
            )
        ).scalar_one()
        rows = (
            (
                await self._db.execute(
                    select(ActivityLog)
                    .where(ActivityLog.user_id == user_id)
                    .order_by(ActivityLog.created_at.desc(), ActivityLog.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    async def entity_states(
        self, user_id: uuid.UUID, entities: list[tuple[str, uuid.UUID]]
    ) -> dict[tuple[str, uuid.UUID], str]:
        """Map (entity_type, id) -> 'active' | 'archived' for entities the user still owns.

        Entities that no longer exist (or are not owned) are simply absent from the result.
        """
        wanted: dict[str, set[uuid.UUID]] = defaultdict(set)
        for entity_type, entity_id in entities:
            wanted[entity_type].add(entity_id)

        queries: dict[str, Select[tuple[uuid.UUID, datetime | None]]] = {}
        if wanted["workspace"]:
            queries["workspace"] = select(Workspace.id, Workspace.archived_at).where(
                Workspace.user_id == user_id, Workspace.id.in_(wanted["workspace"])
            )
        if wanted["subject"]:
            queries["subject"] = (
                select(Subject.id, Subject.archived_at)
                .join(Workspace, Subject.workspace_id == Workspace.id)
                .where(Workspace.user_id == user_id, Subject.id.in_(wanted["subject"]))
            )
        if wanted["folder"]:
            queries["folder"] = (
                select(Folder.id, Folder.archived_at)
                .join(Subject, Folder.subject_id == Subject.id)
                .join(Workspace, Subject.workspace_id == Workspace.id)
                .where(Workspace.user_id == user_id, Folder.id.in_(wanted["folder"]))
            )
        if wanted["chapter"]:
            queries["chapter"] = (
                select(Chapter.id, Chapter.archived_at)
                .join(Subject, Chapter.subject_id == Subject.id)
                .join(Workspace, Subject.workspace_id == Workspace.id)
                .where(Workspace.user_id == user_id, Chapter.id.in_(wanted["chapter"]))
            )

        states: dict[tuple[str, uuid.UUID], str] = {}
        for entity_type, stmt in queries.items():
            for entity_id, archived_at in await self._db.execute(stmt):
                states[(entity_type, entity_id)] = "archived" if archived_at else "active"
        return states

    # ---- workspace overview / recent subjects ---------------------------------------------

    async def workspace_overview(
        self, user_id: uuid.UUID, *, limit: int
    ) -> tuple[list[WorkspaceOverviewRow], int]:
        """Non-archived workspaces with their non-archived subject counts."""
        total = (
            await self._db.execute(
                select(func.count(Workspace.id)).where(
                    Workspace.user_id == user_id, Workspace.archived_at.is_(None)
                )
            )
        ).scalar_one()
        stmt = (
            select(Workspace, func.count(Subject.id))
            .outerjoin(
                Subject,
                (Subject.workspace_id == Workspace.id) & Subject.archived_at.is_(None),
            )
            .where(Workspace.user_id == user_id, Workspace.archived_at.is_(None))
            .group_by(Workspace.id)
            .order_by(Workspace.is_default.desc(), Workspace.updated_at.desc(), Workspace.id)
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [WorkspaceOverviewRow(ws, count) for ws, count in rows], total

    async def recent_subjects(self, user_id: uuid.UUID, *, limit: int) -> list[RecentSubjectRow]:
        stmt = (
            select(Subject, Workspace.name)
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(
                Workspace.user_id == user_id,
                Workspace.archived_at.is_(None),
                Subject.archived_at.is_(None),
            )
            .order_by(Subject.updated_at.desc(), Subject.id)
            .limit(limit)
        )
        return [RecentSubjectRow(s, ws_name) for s, ws_name in (await self._db.execute(stmt))]

    # ---- archived -----------------------------------------------------------------------

    async def list_archived(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ArchivedRow], int]:
        no_uuid = cast(null(), PG_UUID(as_uuid=True))
        no_text = cast(null(), String)

        workspaces = select(
            literal("workspace").label("item_type"),
            Workspace.id.label("id"),
            Workspace.name.label("name"),
            Workspace.archived_at.label("archived_at"),
            Workspace.id.label("workspace_id"),
            Workspace.name.label("workspace_name"),
            no_uuid.label("subject_id"),
            no_text.label("subject_name"),
        ).where(Workspace.user_id == user_id, Workspace.archived_at.is_not(None))

        subjects = (
            select(
                literal("subject"),
                Subject.id,
                Subject.name,
                Subject.archived_at,
                Workspace.id,
                Workspace.name,
                no_uuid,
                no_text,
            )
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id, Subject.archived_at.is_not(None))
        )

        folders = (
            select(
                literal("folder"),
                Folder.id,
                Folder.name,
                Folder.archived_at,
                Workspace.id,
                Workspace.name,
                Subject.id,
                Subject.name,
            )
            .join(Subject, Folder.subject_id == Subject.id)
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id, Folder.archived_at.is_not(None))
        )

        chapters = (
            select(
                literal("chapter"),
                Chapter.id,
                Chapter.title,
                Chapter.archived_at,
                Workspace.id,
                Workspace.name,
                Subject.id,
                Subject.name,
            )
            .join(Subject, Chapter.subject_id == Subject.id)
            .join(Workspace, Subject.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id, Chapter.archived_at.is_not(None))
        )

        combined = union_all(workspaces, subjects, folders, chapters).subquery()
        total = (await self._db.execute(select(func.count()).select_from(combined))).scalar_one()
        rows = (
            await self._db.execute(
                select(combined)
                .order_by(combined.c.archived_at.desc(), combined.c.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [
            ArchivedRow(
                item_type=r.item_type,
                id=r.id,
                name=r.name,
                archived_at=r.archived_at,
                workspace_id=r.workspace_id,
                workspace_name=r.workspace_name,
                subject_id=r.subject_id,
                subject_name=r.subject_name,
            )
            for r in rows
        ], total
