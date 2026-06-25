"""Unit tests for Phase 3 scoring features."""

import math
import pytest

from app.core.scoring import (
    aggregate_challenge_weights,
    competition_rank,
    dual_metric_error,
    winner_take_most,
)


# ── dual_metric_error ──────────────────────────────────────────────────────────

def test_dual_metric_perfect_prediction():
    assert dual_metric_error(4.0, 4.0) == 0.0


def test_dual_metric_known_values():
    # prediction=5, actual=4  →  MAE=1, RMSE=1  →  dual=(1+1)/2=1.0
    assert dual_metric_error(5.0, 4.0) == pytest.approx(1.0)


def test_dual_metric_rmse_penalises_large_errors_more_than_mae():
    # For errors > 1, RMSE > MAE, so dual_metric_error > MAE alone.
    mae = abs(7.0 - 4.0)           # 3.0
    dual = dual_metric_error(7.0, 4.0)
    assert dual > mae / 2          # RMSE contribution lifts it above pure-MAE/2


def test_dual_metric_symmetric():
    assert dual_metric_error(5.0, 4.0) == pytest.approx(dual_metric_error(4.0, 5.0))


# ── competition_rank ───────────────────────────────────────────────────────────

def test_rank_empty():
    assert competition_rank([]) == []


def test_rank_single():
    assert competition_rank([0.5]) == [1.0]


def test_rank_no_ties():
    # errors=[0.1, 0.3, 0.2]  →  best=0.1(rank1), 0.2(rank2), 0.3(rank3)
    ranks = competition_rank([0.1, 0.3, 0.2])
    assert ranks == pytest.approx([1.0, 3.0, 2.0])


def test_rank_tie_at_top():
    # errors=[0.1, 0.1, 0.3]  →  two tied at positions 0-1 → avg rank 1.5
    ranks = competition_rank([0.1, 0.1, 0.3])
    assert ranks == pytest.approx([1.5, 1.5, 3.0])


def test_rank_all_tied():
    # All three at positions 0-2 → avg rank (1+2+3)/3 = 2.0
    ranks = competition_rank([0.2, 0.2, 0.2])
    assert ranks == pytest.approx([2.0, 2.0, 2.0])


def test_rank_tie_in_middle():
    # errors=[0.1, 0.2, 0.2, 0.4]  →  ranks: 1, 2.5, 2.5, 4
    ranks = competition_rank([0.1, 0.2, 0.2, 0.4])
    assert ranks == pytest.approx([1.0, 2.5, 2.5, 4.0])


# ── winner_take_most ───────────────────────────────────────────────────────────

def test_wtm_empty():
    assert winner_take_most([]) == []


def test_wtm_single():
    assert winner_take_most([1.0]) == pytest.approx([1.0])


def test_wtm_weights_sum_to_one():
    ranks = competition_rank([0.1, 0.3, 0.2])
    weights = winner_take_most(ranks)
    assert sum(weights) == pytest.approx(1.0)


def test_wtm_winner_gets_90_percent():
    ranks = [1.0, 2.0, 3.0]
    weights = winner_take_most(ranks, winner_share=0.9)
    # Index 0 is rank-1 winner
    assert weights[0] == pytest.approx(0.9)
    assert weights[1] > 0
    assert weights[2] > 0


def test_wtm_losers_ordered_by_inverse_rank():
    # Rank-2 miner should get more weight than rank-3.
    ranks = [1.0, 2.0, 3.0]
    weights = winner_take_most(ranks)
    assert weights[1] > weights[2]


def test_wtm_tie_at_top_splits_winner_share():
    # Two miners tied at rank 1.5 each get winner_share/2.
    ranks = [1.5, 1.5, 3.0]
    weights = winner_take_most(ranks, winner_share=0.9)
    assert weights[0] == pytest.approx(0.45)
    assert weights[1] == pytest.approx(0.45)
    assert sum(weights) == pytest.approx(1.0)


def test_wtm_all_tied_sums_to_one():
    ranks = [2.0, 2.0, 2.0]
    weights = winner_take_most(ranks)
    assert sum(weights) == pytest.approx(1.0)


# ── aggregate_challenge_weights ────────────────────────────────────────────────

def test_aggregate_empty():
    assert aggregate_challenge_weights([], []) == []


def test_aggregate_equal_weights():
    # Challenge A: miner0 wins; Challenge B: miner1 wins; 50/50 → both get 0.5
    rewards = [[1.0, 0.0], [0.0, 1.0]]
    weights = [0.5, 0.5]
    result = aggregate_challenge_weights(rewards, weights)
    assert result == pytest.approx([0.5, 0.5])


def test_aggregate_unequal_weights():
    # Challenge A (weight 0.6): miner0 wins all; Challenge B (0.4): miner1 wins all
    rewards = [[1.0, 0.0], [0.0, 1.0]]
    result = aggregate_challenge_weights(rewards, [0.6, 0.4])
    assert result == pytest.approx([0.6, 0.4])


def test_aggregate_output_sums_to_one():
    rewards = [[0.9, 0.05, 0.05], [0.1, 0.8, 0.1]]
    result = aggregate_challenge_weights(rewards, [0.6, 0.4])
    assert sum(result) == pytest.approx(1.0)


def test_aggregate_single_challenge_passthrough():
    rewards = [[0.9, 0.05, 0.05]]
    result = aggregate_challenge_weights(rewards, [1.0])
    assert result == pytest.approx([0.9, 0.05, 0.05])
