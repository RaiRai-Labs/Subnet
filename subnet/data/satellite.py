"""Satellite index loader (Phase 4).

`SatelliteLoader` is the provider-agnostic interface the feature builder depends
on. `StubSatelliteLoader` is a deterministic offline implementation (no account,
no network) that produces plausible NDVI/EVI/NDWI series so the whole pipeline
runs end-to-end today. A real provider (Sentinel Hub or Google Earth Engine)
implements the same `indices()` contract and drops in once credentials exist.
"""

import hashlib
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, runtime_checkable


def _unit_hash(*parts) -> float:
    """Deterministic float in [0, 1) from the given parts (stable across runs)."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0x100000000


@runtime_checkable
class SatelliteLoader(Protocol):
    def indices(
        self, lat: float, lon: float, start: date, end: date
    ) -> list[dict]:
        """Return [{date, ndvi, evi, ndwi}, ...] over ``[start, end]``."""
        ...


@dataclass
class StubSatelliteLoader:
    """Deterministic synthetic NDVI/EVI/NDWI — offline dev, no provider."""

    step_days: int = 5

    def indices(self, lat: float, lon: float, start: date, end: date) -> list[dict]:
        out: list[dict] = []
        day = start
        while day <= end:
            key = (round(lat, 3), round(lon, 3), day.isoformat())
            ndvi = round(0.2 + 0.6 * _unit_hash(*key), 3)          # 0.20 .. 0.80
            evi = round(ndvi * 0.85, 3)
            ndwi = round(0.5 * _unit_hash("ndwi", *key) - 0.1, 3)  # -0.10 .. 0.40
            out.append(
                {"date": day.isoformat(), "ndvi": ndvi, "evi": evi, "ndwi": ndwi}
            )
            day += timedelta(days=self.step_days)
        return out


def default_satellite_loader() -> SatelliteLoader:
    """Real provider when credentials are present, else the offline stub.

    Lets the pipeline auto-upgrade to Sentinel Hub once ``SH_CLIENT_ID`` /
    ``SH_CLIENT_SECRET`` are set, with no code change.
    """
    if os.getenv("SH_CLIENT_ID") and os.getenv("SH_CLIENT_SECRET"):
        from subnet.data.sentinelhub import SentinelHubLoader

        return SentinelHubLoader()
    return StubSatelliteLoader()
