"""Unit tests for Phase 3/4 rolling rank history + liveness."""

from subnet.validator.rank_history import RankTracker


def test_rolling_average_over_rounds():
    rt = RankTracker(window=10)
    rt.record("rice:30d", 0, {1: 1, 2: 3})
    rt.record("rice:30d", 1, {1: 3, 2: 1})
    # uid1: (1+3)/2 = 2.0 ; uid2: (3+1)/2 = 2.0
    assert rt.rolling_ranks("rice:30d") == {1: 2.0, 2: 2.0}


def test_window_truncates_old_rounds():
    rt = RankTracker(window=2)
    rt.record("c", 0, {1: 10})   # falls out of the window
    rt.record("c", 1, {1: 2})
    rt.record("c", 2, {1: 4})
    # Only the last 2 rounds retained: (2+4)/2 = 3.0
    assert rt.rolling_ranks("c") == {1: 3.0}


def test_best_miner_lowest_average():
    rt = RankTracker()
    rt.record("c", 0, {1: 1, 2: 2, 3: 3})
    rt.record("c", 1, {1: 1, 2: 2, 3: 3})
    assert rt.best_miner("c") == 1


def test_best_miner_recency_tiebreak():
    rt = RankTracker()
    # Both average to 2.0, but uid2 ranked better (1) in the most recent round.
    rt.record("c", 0, {1: 1, 2: 3})
    rt.record("c", 1, {1: 3, 2: 1})
    assert rt.best_miner("c") == 2


def test_best_miner_none_when_empty():
    assert RankTracker().best_miner("nope") is None


def test_mark_absent_drops_after_allowed_strikes():
    rt = RankTracker(allowed_absence=3)
    rt.record("c", 0, {1: 1})
    assert rt.mark_absent("c", [1]) == set()      # strike 1
    assert rt.mark_absent("c", [1]) == set()      # strike 2
    dropped = rt.mark_absent("c", [1])            # strike 3 → dropped
    assert dropped == {1}
    assert rt.rolling_ranks("c") == {}            # history gone


def test_responding_resets_absence():
    rt = RankTracker(allowed_absence=2)
    rt.record("c", 0, {1: 1})
    rt.mark_absent("c", [1])                       # strike 1
    rt.record("c", 1, {1: 2})                      # responds → resets
    assert rt.mark_absent("c", [1]) == set()       # only strike 1 again
    assert 1 in rt.rolling_ranks("c")


def test_challenges_are_isolated():
    rt = RankTracker()
    rt.record("rice:7d", 0, {1: 1})
    rt.record("cassava:90d", 0, {1: 5})
    assert rt.rolling_ranks("rice:7d") == {1: 1.0}
    assert rt.rolling_ranks("cassava:90d") == {1: 5.0}
