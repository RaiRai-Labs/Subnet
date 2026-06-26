"""Prediction task model.

A validator creates a PredictionTask from a farm's metadata + satellite/weather
features (spec §6, step 3) and distributes it to miners.
"""

import enum

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
)
from sqlalchemy.sql import func

from app.core.database import Base


class TaskStatus(str, enum.Enum):
    open = "open"             # created, accepting miner responses
    closed = "closed"        # no longer accepting responses (reveal phase)
    completed = "completed"  # miners queried, predictions aggregated
    scored = "scored"        # ground truth received and miners scored
    cancelled = "cancelled"  # farmer started a new season — stale tasks discarded


class PredictionTask(Base):
    __tablename__ = "prediction_tasks"

    id = Column(Integer, primary_key=True, index=True)
    # Human/network-facing task id, e.g. "task_001".
    task_id = Column(String, unique=True, nullable=False, index=True)

    farm_id = Column(Integer, index=True)  # backend farm ID — subnet has no farms table

    crop = Column(String, nullable=False)
    province = Column(String, nullable=True)
    field_size = Column(Float, nullable=True)     # hectares
    planting_date = Column(String, nullable=True) # ISO date string, snapshot at challenge time
    horizon_days = Column(Integer, nullable=True) # forecast horizon sent to miners

    # Feature payload sent to miners — full snapshot so the challenge is reproducible.
    ndvi = Column(JSON, nullable=True)    # NDVI time series
    evi = Column(JSON, nullable=True)     # EVI time series
    ndwi = Column(JSON, nullable=True)    # NDWI (moisture) time series
    weather = Column(JSON, nullable=True) # daily weather records

    status = Column(
        Enum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.open,
        index=True,
    )

    # Aggregate of miner predictions, filled by the validator workflow.
    average_prediction = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    scored_at = Column(DateTime(timezone=True), nullable=True)
