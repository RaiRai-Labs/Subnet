"""ORM models.

Importing every model here ensures they are registered on ``Base.metadata``
before ``create_all`` runs at startup.
"""

from app.core.database import Base
from app.models.challenge import BestMiner, Challenge, ChallengeRankHistory
from app.models.farm import Farm, FarmUserLink
from app.models.farm_analysis import FarmAnalysis
from app.models.response import GroundTruth, MinerResponse
from app.models.task import PredictionTask, TaskStatus

__all__ = [
    "Base",
    "Farm",
    "FarmUserLink",
    "FarmAnalysis",
    "PredictionTask",
    "TaskStatus",
    "MinerResponse",
    "GroundTruth",
    "Challenge",
    "ChallengeRankHistory",
    "BestMiner",
]
