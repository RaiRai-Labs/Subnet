"""Sentinel Hub satellite loader (Phase 4).

A real `SatelliteLoader` implementation backed by Sentinel Hub's Statistical API
over Sentinel-2 L2A. It computes NDVI / EVI / NDWI from surface reflectance via
an evalscript and returns the per-interval means — the same
``[{date, ndvi, evi, ndwi}, ...]`` contract the offline stub produces.

Auth is OAuth2 client-credentials; supply credentials via env
(``SH_CLIENT_ID`` / ``SH_CLIENT_SECRET``) or constructor args. Implemented on
stdlib ``urllib`` (no SDK dependency). Request building and response parsing are
split out so they can be unit-tested offline; only ``_fetch_token`` and
``indices`` touch the network.
"""

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
STATS_URL = "https://services.sentinel-hub.com/api/v1/statistics"

# Reflectance is 0..1 in Sentinel Hub evalscripts for S2L2A, so the EVI +1
# constant is correct as written. NDWI here is McFeeters (green/NIR).
_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B02", "B03", "B04", "B08", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "evi",  bands: 1, sampleType: "FLOAT32" },
      { id: "ndwi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  let evi = 2.5 * (s.B08 - s.B04) / (s.B08 + 6.0 * s.B04 - 7.5 * s.B02 + 1.0);
  let ndwi = (s.B03 - s.B08) / (s.B03 + s.B08);
  return { ndvi: [ndvi], evi: [evi], ndwi: [ndwi], dataMask: [s.dataMask] };
}
"""


class SentinelHubError(RuntimeError):
    """Raised on missing credentials or a malformed Sentinel Hub response."""


@dataclass
class SentinelHubLoader:
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str = TOKEN_URL
    stats_url: str = STATS_URL
    collection: str = "sentinel-2-l2a"
    interval: str = "P5D"            # aggregation interval (S2 revisit ~5 days)
    buffer_deg: float = 0.005        # ~500 m half-box around the point
    resolution_deg: float = 0.0001   # ~10 m
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.client_id = self.client_id or os.getenv("SH_CLIENT_ID")
        self.client_secret = self.client_secret or os.getenv("SH_CLIENT_SECRET")

    # --- offline-testable request/response helpers ---
    def _bbox(self, lat: float, lon: float) -> list[float]:
        d = self.buffer_deg
        return [lon - d, lat - d, lon + d, lat + d]

    def _build_request(self, lat: float, lon: float, start: date, end: date) -> dict:
        return {
            "input": {
                "bounds": {
                    "bbox": self._bbox(lat, lon),
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                    },
                },
                "data": [
                    {
                        "type": self.collection,
                        "dataFilter": {"mosaickingOrder": "leastCC"},
                    }
                ],
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{start.isoformat()}T00:00:00Z",
                    "to": f"{end.isoformat()}T23:59:59Z",
                },
                "aggregationInterval": {"of": self.interval},
                "resx": self.resolution_deg,
                "resy": self.resolution_deg,
                "evalscript": _EVALSCRIPT,
            },
        }

    @staticmethod
    def _parse(payload: dict) -> list[dict]:
        """Flatten the Statistical API response into per-interval index means."""

        def mean_of(outputs: dict, name: str):
            try:
                stats = outputs[name]["bands"]["B0"]["stats"]
            except (KeyError, TypeError):
                return None
            sample_count = stats.get("sampleCount", 0)
            no_data = stats.get("noDataCount", 0)
            if not sample_count or sample_count == no_data:
                return None
            value = stats.get("mean")
            return round(float(value), 4) if value is not None else None

        rows: list[dict] = []
        for item in payload.get("data", []):
            outputs = item.get("outputs") or {}
            ndvi = mean_of(outputs, "ndvi")
            if ndvi is None:  # interval had no valid acquisition — skip it
                continue
            rows.append(
                {
                    "date": (item.get("interval") or {}).get("from", "")[:10],
                    "ndvi": ndvi,
                    "evi": mean_of(outputs, "evi"),
                    "ndwi": mean_of(outputs, "ndwi"),
                }
            )
        return rows

    # --- network ---
    def _post(self, url: str, data: bytes, headers: dict) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    def _fetch_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise SentinelHubError("missing SH_CLIENT_ID / SH_CLIENT_SECRET")
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode()
        payload = self._post(
            self.token_url,
            body,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = payload.get("access_token")
        if not token:
            raise SentinelHubError("no access_token in Sentinel Hub token response")
        return token

    def indices(self, lat: float, lon: float, start: date, end: date) -> list[dict]:
        token = self._fetch_token()
        body = json.dumps(self._build_request(lat, lon, start, end)).encode()
        payload = self._post(
            self.stats_url,
            body,
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        return self._parse(payload)
