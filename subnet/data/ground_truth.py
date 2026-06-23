"""Ground-truth verification (Phase 4, spec §7).

A farmer-reported harvest only counts as truth if it passes two checks:

1. Range check — the value is a finite yield within the plausible band.
2. Satellite-consistency — the reported yield is broadly consistent with the
   field's NDVI. Using the same NDVI→yield anchor the miner baseline uses
   (``3 + 3·mean_ndvi``), a report that is implausibly far from what the
   vegetation index implies is rejected (e.g. a lush field claiming ~0 yield).
"""

from statistics import fmean
from typing import Optional

from subnet.validator.anti_gaming import MAX_YIELD, MIN_YIELD, is_valid_prediction

# NDVI → yield anchor (matches neurons/miner.py baseline).
NDVI_YIELD_INTERCEPT = 3.0
NDVI_YIELD_SLOPE = 3.0
# How far a report may sit from the NDVI-implied yield before it's rejected (t/ha).
CONSISTENCY_TOLERANCE = 2.0


def expected_yield_from_ndvi(ndvi: Optional[list]) -> Optional[float]:
    vals = [float(v) for v in (ndvi or []) if isinstance(v, (int, float))]
    if not vals:
        return None
    return NDVI_YIELD_INTERCEPT + NDVI_YIELD_SLOPE * fmean(vals)


def verify_ground_truth(
    actual_yield: float,
    ndvi: Optional[list] = None,
    tolerance: float = CONSISTENCY_TOLERANCE,
) -> tuple[bool, str]:
    """Return ``(is_verified, reason)`` for a reported harvest yield."""
    if not is_valid_prediction(actual_yield):
        return False, f"yield outside plausible range [{MIN_YIELD}, {MAX_YIELD}]"

    expected = expected_yield_from_ndvi(ndvi)
    if expected is None:
        return True, "range ok (no NDVI to cross-check)"
    if abs(actual_yield - expected) > tolerance:
        return (
            False,
            f"inconsistent with NDVI (expected ~{expected:.2f}, got {actual_yield:.2f})",
        )
    return True, "ok"
