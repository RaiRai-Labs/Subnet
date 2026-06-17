"""Pydantic schemas for the miner commit-reveal flow and ground truth."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommitRequest(BaseModel):
    """Commit phase — miner submits only a hash (spec §10)."""

    task_id: str = Field(..., examples=["task_001"])
    miner_hotkey: str = Field(..., min_length=1)
    miner_uid: int | None = None
    commit_hash: str = Field(..., min_length=1, examples=["abc123"])


class RevealRequest(BaseModel):
    """Reveal phase — miner reveals the prediction and the nonce."""

    task_id: str = Field(..., examples=["task_001"])
    miner_hotkey: str = Field(..., min_length=1)
    expected_yield: float = Field(..., gt=0, description="Tons per hectare")
    confidence: float = Field(..., ge=0.0, le=1.0)
    nonce: str = Field(..., min_length=1, description="Salt used when building the commit hash")


class GroundTruthRequest(BaseModel):
    """Farmer reports actual harvest yield (spec §7)."""

    task_id: str = Field(..., examples=["task_001"])
    farm_id: int | None = None
    actual_yield: float = Field(..., gt=0, description="Tons per hectare")


class MinerResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    miner_hotkey: str
    miner_uid: int | None
    commit_hash: str
    revealed: bool
    expected_yield: float | None
    confidence: float | None
    hash_valid: bool | None
    mae: float | None
    score: float | None
    weight: float | None
    committed_at: datetime
    revealed_at: datetime | None
