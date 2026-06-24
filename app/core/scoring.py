"""Scoring helpers (spec §8 / §9 / §10)."""

import hashlib
import math


def build_commit_hash(expected_yield: float, confidence: float, nonce: str) -> str:
    """Recreate a miner's commit hash for reveal verification.

    Convention: sha256 of "expected_yield:confidence:nonce".
    """
    payload = f"{expected_yield}:{confidence}:{nonce}"
    return hashlib.sha256(payload.encode()).hexdigest()


def mean_absolute_error(prediction: float, actual: float) -> float:
    """MAE for a single prediction (spec §8)."""
    return abs(prediction - actual)


def root_mean_square_error(prediction: float, actual: float) -> float:
    """RMSE for a single prediction. Penalises large errors more than MAE."""
    return math.sqrt((prediction - actual) ** 2)


def dual_metric_error(prediction: float, actual: float) -> float:
    """Combined error signal: (RMSE + MAE) / 2. Lower is better.

    Used as the input to competition_rank — not converted to a score directly.
    RMSE's squaring makes large misses hurt more; MAE keeps the scale interpretable.
    """
    mae = mean_absolute_error(prediction, actual)
    rmse = root_mean_square_error(prediction, actual)
    return (rmse + mae) / 2


def competition_rank(errors: list[float]) -> list[float]:
    """Rank miners by error (ascending). Rank 1 = best (lowest error).

    Ties receive the average of the ranks they would otherwise occupy,
    e.g. two miners tied for first both get rank 1.5.
    """
    n = len(errors)
    if n == 0:
        return []

    sorted_indices = sorted(range(n), key=lambda i: errors[i])
    ranks = [0.0] * n

    i = 0
    while i < n:
        j = i
        while j < n and errors[sorted_indices[j]] == errors[sorted_indices[i]]:
            j += 1
        # Ranks are 1-based; miners in positions i..j-1 share the average.
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[sorted_indices[k]] = avg_rank
        i = j

    return ranks


def winner_take_most(
    ranks: list[float],
    winner_share: float = 0.9,
) -> list[float]:
    """Convert competition ranks into Yuma-Consensus weights.

    Rank-1 miner(s) receive `winner_share` of the total weight pool.
    The remaining (1 - winner_share) is split among others inversely
    proportional to their rank (higher rank = smaller slice).

    If multiple miners share rank 1 (tie), `winner_share` is divided
    equally among them.
    """
    n = len(ranks)
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    best_rank = min(ranks)
    weights = [0.0] * n

    winner_indices = [i for i, r in enumerate(ranks) if r == best_rank]
    loser_indices = [i for i, r in enumerate(ranks) if r != best_rank]

    per_winner = winner_share / len(winner_indices)
    for i in winner_indices:
        weights[i] = per_winner

    if loser_indices:
        remainder = 1.0 - winner_share
        inv_ranks = [1.0 / ranks[i] for i in loser_indices]
        total_inv = sum(inv_ranks)
        for i, inv in zip(loser_indices, inv_ranks):
            weights[i] = remainder * (inv / total_inv)

    return weights


def aggregate_challenge_weights(
    per_challenge_rewards: list[list[float]],
    challenge_weights: list[float],
) -> list[float]:
    """Combine per-challenge winner-take-most rewards into final miner weights.

    per_challenge_rewards: one list of miner rewards per challenge (each sums to 1).
    challenge_weights: importance weight for each challenge (must sum to 1).

    Returns one weight per miner, summing to 1.
    """
    if not per_challenge_rewards:
        return []

    n_miners = len(per_challenge_rewards[0])
    final = [0.0] * n_miners

    for rewards, cw in zip(per_challenge_rewards, challenge_weights):
        for i, r in enumerate(rewards):
            final[i] += cw * r

    # Normalise to guard against floating-point drift.
    total = sum(final)
    if total <= 0:
        return [0.0] * n_miners
    return [w / total for w in final]


def normalize_weights(scores: list[float]) -> list[float]:
    """Normalize raw scores into weights summing to 1 (for Yuma Consensus).

    Kept for backwards-compatibility with the commit-reveal API scoring path.
    New validator forward pass uses winner_take_most instead.
    """
    total = sum(scores)
    if total <= 0:
        return [0.0 for _ in scores]
    return [s / total for s in scores]
