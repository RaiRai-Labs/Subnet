"""Satellite loader backed by the FarmLink backend's farm_analysis table.

Calls GET /api/public/farms/{farm_id}/satellite-history on the backend and
returns the already-computed NDVI/EVI/moisture series — the same data the
farmer sees on their color-coded map. No Sentinel Hub credentials needed.

Falls back to StubSatelliteLoader if the backend is unreachable or returns
no rows for the requested date range.
"""

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import date

from subnet.data.satellite import SatelliteLoader, StubSatelliteLoader


@dataclass
class BackendSatelliteLoader:
    """Reads NDVI/EVI history from your backend's farm_analysis table.

    Implements the same ``indices()`` contract as every other SatelliteLoader
    so it drops straight into FeatureBuilder with no other changes.
    """

    farm_id: int
    backend_url: str
    timeout: float = 6.0
    _fallback: SatelliteLoader = field(default_factory=StubSatelliteLoader)

    def indices(self, lat: float, lon: float, start: date, end: date) -> list[dict]:
        """Fetch the farm_analysis rows for this farm from the backend.

        lat/lon are accepted to satisfy the SatelliteLoader protocol but are
        unused — the farm_id already identifies the exact field.
        Falls back to StubSatelliteLoader on any network or parse error.
        """
        try:
            url = (
                f"{self.backend_url.rstrip('/')}"
                f"/api/public/farms/{self.farm_id}/satellite-history"
                f"?start={start.isoformat()}&end={end.isoformat()}"
            )
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                rows: list[dict] = json.load(resp)

            if rows:
                return rows
        except Exception:
            pass

        return self._fallback.indices(lat, lon, start, end)
