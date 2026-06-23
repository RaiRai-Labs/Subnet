"""Challenge taxonomy + rolling rank history models (Phase 3).

- ``challenges``           — the crop × forecast-horizon taxonomy (one row per cell).
- ``challenge_rank_history`` — per-(challenge, round, miner) rank, the rolling-window
                               source data averaged when computing standings.
- ``best_miners``          — the current best miner per challenge (lowest rolling rank).

``challenge_id`` is the stable taxonomy id (e.g. ``"rice:30d"``) and is used as a
logical join key across the three tables.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class Challenge(Base):
    """One cell of the challenge taxonomy (crop × forecast-horizon)."""

    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(String, unique=True, nullable=False, index=True)  # "rice:30d"
    crop = Column(String, nullable=False)
    horizon_days = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False)  # difficulty weight

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChallengeRankHistory(Base):
    """A miner's rank in a single round of one challenge."""

    __tablename__ = "challenge_rank_history"
    __table_args__ = (
        # One rank per miner per round per challenge.
        UniqueConstraint(
            "challenge_id", "round", "miner_uid", name="uq_challenge_round_miner"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(String, nullable=False, index=True)
    round = Column(Integer, nullable=False, index=True)  # validator step

    miner_uid = Column(Integer, nullable=False, index=True)
    miner_hotkey = Column(String, nullable=True, index=True)

    rank = Column(Integer, nullable=False)  # 1 = best in this round
    score = Column(Float, nullable=True)    # the reward this rank was derived from

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BestMiner(Base):
    """Current best miner for a challenge (lowest rolling-average rank)."""

    __tablename__ = "best_miners"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(String, unique=True, nullable=False, index=True)

    miner_uid = Column(Integer, nullable=False)
    miner_hotkey = Column(String, nullable=True)
    avg_rank = Column(Float, nullable=False)   # rolling-average rank
    window = Column(Integer, nullable=False)   # number of rounds averaged

    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
