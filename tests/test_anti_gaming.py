"""Unit tests for Phase 4 anti-gaming guards."""

from subnet.validator.anti_gaming import (
    MAX_YIELD,
    MIN_YIELD,
    CollusionDetector,
    is_valid_prediction,
)


# ── is_valid_prediction ─────────────────────────────────────────────────────────

def test_valid_in_range():
    assert is_valid_prediction(4.2) is True
    assert is_valid_prediction(MIN_YIELD) is True
    assert is_valid_prediction(MAX_YIELD) is True


def test_numeric_string_is_valid():
    # float("4.0") succeeds, so a numeric string is accepted.
    assert is_valid_prediction("4.0") is True


def test_out_of_range_rejected():
    assert is_valid_prediction(-0.1) is False
    assert is_valid_prediction(MAX_YIELD + 0.1) is False


def test_none_and_bool_rejected():
    # None is not a prediction; bool is an int subclass we must not accept.
    assert is_valid_prediction(None) is False
    assert is_valid_prediction(True) is False
    assert is_valid_prediction(False) is False


def test_non_finite_rejected():
    assert is_valid_prediction(float("nan")) is False
    assert is_valid_prediction(float("inf")) is False
    assert is_valid_prediction(float("-inf")) is False


def test_non_numeric_rejected():
    assert is_valid_prediction("abc") is False
    assert is_valid_prediction([4.0]) is False


# ── CollusionDetector ───────────────────────────────────────────────────────────

def _feed(detector, preds_by_round):
    for round_no, preds in enumerate(preds_by_round):
        detector.record(round_no, preds)


def test_identical_streams_flag_the_newer_miner():
    det = CollusionDetector(window=20, threshold=0.02, min_samples=5)
    # uid 1 and uid 2 predict identically for 6 rounds; uid 3 is unrelated.
    _feed(det, [{1: 4.0, 2: 4.0, 3: 1.0 + r} for r in range(6)])
    # uid 2 registered later (higher order) → uid 2 is penalized, not uid 1.
    flagged = det.detect(registration_order={1: 100, 2: 200, 3: 50})
    assert flagged == {2}


def test_newer_is_decided_by_registration_order_not_uid():
    det = CollusionDetector(min_samples=5)
    _feed(det, [{1: 4.0, 2: 4.0} for _ in range(6)])
    # Flip the ordering: uid 1 is the newer registrant → uid 1 is flagged.
    flagged = det.detect(registration_order={1: 999, 2: 10})
    assert flagged == {1}


def test_divergent_streams_not_flagged():
    det = CollusionDetector(threshold=0.02, min_samples=5)
    _feed(det, [{1: 4.0, 2: 4.0 + 0.5} for _ in range(6)])  # diff 0.5 >> 0.02
    assert det.detect(registration_order={1: 1, 2: 2}) == set()


def test_too_few_shared_rounds_not_flagged():
    det = CollusionDetector(threshold=0.02, min_samples=5)
    _feed(det, [{1: 4.0, 2: 4.0} for _ in range(4)])  # only 4 < min_samples
    assert det.detect(registration_order={1: 1, 2: 2}) == set()


def test_only_overlapping_rounds_count_toward_min_samples():
    det = CollusionDetector(threshold=0.02, min_samples=5)
    # uid 1 answers rounds 0-5, uid 2 only rounds 0-2 → 3 shared < 5.
    det.record(0, {1: 4.0, 2: 4.0})
    det.record(1, {1: 4.0, 2: 4.0})
    det.record(2, {1: 4.0, 2: 4.0})
    det.record(3, {1: 4.0})
    det.record(4, {1: 4.0})
    det.record(5, {1: 4.0})
    assert det.detect(registration_order={1: 1, 2: 2}) == set()
