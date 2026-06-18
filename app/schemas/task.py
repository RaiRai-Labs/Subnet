"""Pydantic schemas for prediction tasks."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    """Inbound farm + crop prediction data. The task_id is generated server-side."""

    farm_id: int | None = None
    crop: str = Field(..., min_length=1, max_length=80, examples=["rice"])
    province: str | None = Field(default=None, max_length=100, examples=["Chiang Mai"])
    field_size: float | None = Field(default=None, gt=0, description="Field size in hectares")
    ndvi: list[float] | None = Field(default=None, description="Historical NDVI series")
    weather: list[dict] | None = Field(default=None, description="Historical weather series")


class TaskAccepted(BaseModel):
    """Confirmation returned when a prediction task is accepted (spec MVP step 3)."""

    task_id: str
    status: TaskStatus
    message: str = "Prediction task accepted"


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
    average_prediction: float | None
    created_at: datetime
    closed_at: datetime | None
    completed_at: datetime | None
    scored_at: datetime | None


class MinerPrediction(BaseModel):
    miner_hotkey: str
    expected_yield: float


class ValidationResult(BaseModel):
    """Result of the validator workflow (spec MVP step 5)."""

    task_id: str
    status: TaskStatus
    predictions: list[MinerPrediction]
    average_prediction: float
