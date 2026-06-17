"""Pydantic schemas for prediction tasks."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64, examples=["task_001"])
    farm_id: int | None = None
    crop: str = Field(..., min_length=1, max_length=80, examples=["rice"])
    province: str | None = Field(default=None, max_length=100, examples=["Chiang Mai"])
    field_size: float | None = Field(default=None, gt=0, description="Field size in hectares")
    ndvi: list[float] | None = Field(default=None, description="Historical NDVI series")
    weather: list[dict] | None = Field(default=None, description="Historical weather series")


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    farm_id: int | None
    crop: str
    province: str | None
    field_size: float | None
    ndvi: list[float] | None
    weather: list[dict] | None
    status: TaskStatus
    created_at: datetime
    closed_at: datetime | None
    scored_at: datetime | None
