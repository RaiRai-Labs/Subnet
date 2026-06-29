"""Unit tests for Phase 4 ground-truth verification (spec §7)."""

from subnet.data.ground_truth import (
    CONSISTENCY_TOLERANCE,
    expected_yield_from_ndvi,
    verify_ground_truth,
)


def test_expected_yield_from_ndvi_none_when_empty():
    assert expected_yield_from_ndvi(None) is None
    assert expected_yield_from_ndvi([]) is None


def test_expected_yield_from_ndvi_anchor():
    # 3 + 3*mean([0.5, 0.5]) = 4.5
    assert expected_yield_from_ndvi([0.5, 0.5]) == 4.5


def test_out_of_range_rejected():
    ok, reason = verify_ground_truth(-1.0)
    assert ok is False
    assert "range" in reason


def test_range_ok_without_ndvi_passes():
    ok, reason = verify_ground_truth(4.0)
    assert ok is True
    assert "no NDVI" in reason


def test_consistent_with_ndvi_passes():
    # NDVI 0.5 → expected 4.5; report 4.5 is spot on.
    ok, reason = verify_ground_truth(4.5, ndvi=[0.5])
    assert ok is True
    assert reason == "ok"


def test_inconsistent_with_ndvi_rejected():
    # Lush field (NDVI 0.8 → expected 5.4) claiming ~0 yield is rejected.
    ok, reason = verify_ground_truth(0.1, ndvi=[0.8])
    assert ok is False
    assert "inconsistent" in reason


def test_tolerance_boundary_inclusive():
    # expected 4.5; report exactly tolerance away should still pass (<=).
    ok, _ = verify_ground_truth(4.5 + CONSISTENCY_TOLERANCE, ndvi=[0.5])
    assert ok is True
    ok, _ = verify_ground_truth(4.5 + CONSISTENCY_TOLERANCE + 0.01, ndvi=[0.5])
    assert ok is False
