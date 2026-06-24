"""Feature builder (Phase 4).

Assembles a `YieldPredictionSynapse` (the task sent to miners) from farm metadata
plus the satellite and weather loaders. A live validator composes this instead of
the synthetic `subnet.validator.challenge.generate_challenge` path.

Weather is fetched over the network and degrades gracefully (empty series) if the
call fails, so a transient Open-Meteo outage never blocks a round; the satellite
stub is always available offline.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from subnet.data.satellite import SatelliteLoader, default_satellite_loader
from subnet.data.weather import WeatherLoader
from subnet.protocol import YieldPredictionSynapse


@dataclass
class FarmContext:
    crop: str
    latitude: float
    longitude: float
    province: Optional[str] = None
    field_size: Optional[float] = None      # hectares
    horizon_days: Optional[int] = None


class FeatureBuilder:
    def __init__(
        self,
        weather: Optional[WeatherLoader] = None,
        satellite: Optional[SatelliteLoader] = None,
    ) -> None:
        self.weather = weather or WeatherLoader()
        self.satellite = satellite or default_satellite_loader()

    def build(
        self, farm: FarmContext, start: date, end: date
    ) -> YieldPredictionSynapse:
        sat = self.satellite.indices(farm.latitude, farm.longitude, start, end)
        try:
            wx = self.weather.daily(farm.latitude, farm.longitude, start, end)
        except Exception:  # noqa: BLE001 - weather is best-effort; degrade to empty
            wx = []
        return YieldPredictionSynapse(
            crop=farm.crop,
            province=farm.province,
            field_size=farm.field_size,
            horizon_days=farm.horizon_days,
            ndvi=[s["ndvi"] for s in sat],
            weather=[{"temp": w["temp"], "rain": w["rain"]} for w in wx],
        )
