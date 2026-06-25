"""Open-Meteo weather loader (Phase 4).

Pulls daily historical weather (temperature / rainfall / wind) for a lat-lon over
a date range from Open-Meteo's archive API. Open-Meteo is keyless and free for
non-commercial use, so no credentials are required.

Uses stdlib ``urllib`` (no extra dependency, works from the sync neuron loop).
URL building and response parsing are split out so they can be unit-tested
offline; ``daily()`` is the only method that touches the network.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date


def _at(seq, i):
    """Safe positional lookup into an Open-Meteo parallel array."""
    return seq[i] if seq is not None and i < len(seq) else None


@dataclass
class WeatherLoader:
    base_url: str = "https://archive-api.open-meteo.com/v1/archive"
    timeout: float = 15.0
    daily_vars: tuple[str, ...] = field(
        default_factory=lambda: (
            "temperature_2m_mean",
            "precipitation_sum",
            "wind_speed_10m_max",
        )
    )

    def _build_url(self, lat: float, lon: float, start: date, end: date) -> str:
        query = urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": ",".join(self.daily_vars),
                "timezone": "UTC",
            }
        )
        return f"{self.base_url}?{query}"

    @staticmethod
    def _parse(payload: dict) -> list[dict]:
        """Flatten Open-Meteo's parallel daily arrays into per-day records."""
        daily = payload.get("daily") or {}
        times = daily.get("time") or []
        rows: list[dict] = []
        for i, day in enumerate(times):
            rows.append(
                {
                    "date": day,
                    "temp": _at(daily.get("temperature_2m_mean"), i),
                    "rain": _at(daily.get("precipitation_sum"), i),
                    "wind": _at(daily.get("wind_speed_10m_max"), i),
                }
            )
        return rows

    def daily(self, lat: float, lon: float, start: date, end: date) -> list[dict]:
        """Fetch daily weather records for ``[start, end]`` (network call)."""
        url = self._build_url(lat, lon, start, end)
        req = urllib.request.Request(url, headers={"User-Agent": "rairai-subnet/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.load(resp)
        return self._parse(payload)
