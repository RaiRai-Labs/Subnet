"""Real-data pipeline (Phase 4): weather, satellite, features, ground truth.

Loaders pull the inputs a validator challenge is built from:

- `weather.WeatherLoader`        — Open-Meteo daily history (keyless).
- `satellite.StubSatelliteLoader` — deterministic NDVI/EVI/NDWI offline stub
                                     behind the `SatelliteLoader` interface; a real
                                     provider (Sentinel Hub / GEE) slots in later.
- `features.FeatureBuilder`      — assembles a `YieldPredictionSynapse` from farm
                                     metadata + weather + satellite.
- `ground_truth.verify_ground_truth` — range + NDVI-consistency check (spec §7).
"""
