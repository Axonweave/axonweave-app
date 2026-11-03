import uuid
from datetime import datetime

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

    model_config = {"from_attributes": True}


class ActivityResponse(BaseModel):
    success: bool = True
    data: list[ActivityItem]
    total: int
