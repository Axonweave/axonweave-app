import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChapterStatusCounts(BaseModel):
    not_started: int
    in_progress: int
    completed: int


class DashboardStats(BaseModel):
    workspace_count: int
    subject_count: int
    folder_count: int
    chapter_count: int
    chapter_status: ChapterStatusCounts


class DashboardStatsResponse(BaseModel):
    success: bool = True
    data: DashboardStats


class ActivityItem(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    entity_name: str | None
    workspace_id: uuid.UUID | None
    created_at: datetime
    # 'active' -> still exists; 'archived' -> exists but archived; 'deleted' -> gone (no link)
    entity_status: Literal["active", "archived", "deleted"] = "deleted"

    model_config = {"from_attributes": True}


class ActivityResponse(BaseModel):
    success: bool = True
    data: list[ActivityItem]
    total: int


class WorkspaceOverviewItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_default: bool
    subject_count: int
    updated_at: datetime


class WorkspaceOverviewResponse(BaseModel):
    success: bool = True
    data: list[WorkspaceOverviewItem]
    total: int


class RecentSubjectItem(BaseModel):
    id: uuid.UUID
    name: str
    workspace_id: uuid.UUID
    workspace_name: str
    updated_at: datetime


class RecentSubjectsResponse(BaseModel):
    success: bool = True
    data: list[RecentSubjectItem]


ArchivedItemType = Literal["workspace", "subject", "folder", "chapter"]


class ArchivedItem(BaseModel):
    type: ArchivedItemType
    id: uuid.UUID
    name: str
    archived_at: datetime
    workspace_id: uuid.UUID
    workspace_name: str
    subject_id: uuid.UUID | None
    subject_name: str | None


class ArchivedResponse(BaseModel):
    success: bool = True
    data: list[ArchivedItem]
    total: int
