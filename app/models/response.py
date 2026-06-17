"""Miner response and ground-truth models.

MinerResponse supports the commit-reveal flow (spec §10): a miner first commits
a hash, then reveals the prediction; the validator verifies the hash, scores
against ground truth (MAE, spec §8) and derives a rank score (spec §9).
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class MinerResponse(Base):
    __tablename__ = "miner_responses"
    __table_args__ = (
        # One response per miner per task.
        UniqueConstraint("task_id", "miner_hotkey", name="uq_task_miner"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer,
        ForeignKey("prediction_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Bittensor miner identity.
    miner_hotkey = Column(String, nullable=False, index=True)
    miner_uid = Column(Integer, nullable=True, index=True)

    # --- Commit phase ---
    commit_hash = Column(String, nullable=False)
    committed_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Reveal phase ---
    revealed = Column(Boolean, nullable=False, default=False)
    expected_yield = Column(Float, nullable=True)   # tons / hectare
    confidence = Column(Float, nullable=True)        # 0..1
    nonce = Column(String, nullable=True)            # salt used to verify the hash
    hash_valid = Column(Boolean, nullable=True)      # set when reveal is verified
    revealed_at = Column(DateTime(timezone=True), nullable=True)

    # --- Scoring (filled after ground truth arrives) ---
    mae = Column(Float, nullable=True)               # |expected_yield - actual_yield|
    score = Column(Float, nullable=True)             # 1 / (1 + MAE)
    weight = Column(Float, nullable=True)            # normalized weight submitted to consensus


class GroundTruth(Base):
    """Actual harvest yield reported by a farmer (spec §7)."""

    __tablename__ = "ground_truth"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer,
        ForeignKey("prediction_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="SET NULL"), index=True)

    actual_yield = Column(Float, nullable=False)     # tons / hectare
    verified = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
