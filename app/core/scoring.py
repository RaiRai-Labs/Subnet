"""Scoring helpers (spec §8 / §9 / §10)."""

import hashlib


def build_commit_hash(expected_yield: float, confidence: float, nonce: str) -> str:
    """Recreate a miner's commit hash for reveal verification.

    Convention: sha256 of "expected_yield:confidence:nonce".
    """
    payload = f"{expected_yield}:{confidence}:{nonce}"
    return hashlib.sha256(payload.encode()).hexdigest()


def mean_absolute_error(prediction: float, actual: float) -> float:
    """MAE for a single prediction (spec §8)."""
    return abs(prediction - actual)


def rank_score(mae: float) -> float:
    """Convert MAE to a rank score (spec §9): score = 1 / (1 + MAE)."""
    return 1.0 / (1.0 + mae)


def normalize_weights(scores: list[float]) -> list[float]:
    """Normalize raw scores into weights summing to 1 (for Yuma Consensus)."""
    total = sum(scores)
    if total <= 0:
        return [0.0 for _ in scores]
    return [s / total for s in scores]
