"""Challenge taxonomy (Phase 3).

The validator no longer poses one undifferentiated task. The prediction space is
partitioned into a grid of challenges — ``crop × forecast-horizon`` — each
carrying its own difficulty weight. Longer forecast horizons are harder to
predict, so they weigh more: sustained skill on the hard challenges should drive
a miner's standing more than a single lucky easy prediction.

This module is pure data (no chain, no DB) so it is safe to import from both the
neuron layer and the Postgres persistence layer.
"""

from dataclasses import dataclass

# MVP scope (spec §3): Thailand, rice + cassava.
CROPS: list[str] = ["rice", "cassava"]

# Forecast horizon (days before harvest) → difficulty weight.
# Longer horizon == harder == higher weight (mirrors Zeus TIME_WINDOW_WEIGHTS).
HORIZON_WEIGHTS: dict[int, float] = {7: 1.0, 30: 2.0, 90: 3.0}


@dataclass(frozen=True)
class ChallengeSpec:
    """One cell of the challenge grid."""

    challenge_id: str       # stable id, e.g. "rice:30d"
    crop: str
    horizon_days: int
    weight: float           # difficulty weight (used when aggregating across challenges)


def _build_taxonomy() -> list[ChallengeSpec]:
    return [
        ChallengeSpec(
            challenge_id=f"{crop}:{horizon}d",
            crop=crop,
            horizon_days=horizon,
            weight=weight,
        )
        for crop in CROPS
        for horizon, weight in HORIZON_WEIGHTS.items()
    ]


# The full crop × horizon grid (2 crops × 3 horizons = 6 challenges).
CHALLENGES: list[ChallengeSpec] = _build_taxonomy()
CHALLENGES_BY_ID: dict[str, ChallengeSpec] = {c.challenge_id: c for c in CHALLENGES}
