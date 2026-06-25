"""Subnet wire protocol.

A validator sends a YieldPredictionSynapse describing a farm/crop prediction
task; a miner fills in `expected_yield` (tons/hectare) and `confidence` and
sends it back. This is the on-network message exchanged over axon/dendrite.
"""

from typing import Optional

import bittensor as bt


class YieldPredictionSynapse(bt.Synapse):
    # --- Request (set by the validator) ---
    crop: str
    province: Optional[str] = None
    field_size: Optional[float] = None          # hectares
    planting_date: Optional[str] = None         # ISO date, e.g. "2026-01-15"
    horizon_days: Optional[int] = None          # forecast horizon (days before harvest)

    # Satellite indices — historical series, one entry per scene
    ndvi: Optional[list[float]] = None          # Normalized Difference Vegetation Index
    evi: Optional[list[float]] = None           # Enhanced Vegetation Index
    ndwi: Optional[list[float]] = None          # Normalized Difference Water Index

    # Weather — daily records: {date, temp, rain, humidity, wind}
    weather: Optional[list[dict]] = None

    # --- Response (filled by the miner) ---
    expected_yield: Optional[float] = None       # tons / hectare
    confidence: Optional[float] = None           # 0..1

    def deserialize(self) -> Optional[float]:
        """Return the miner's predicted yield (the value validators score)."""
        return self.expected_yield
