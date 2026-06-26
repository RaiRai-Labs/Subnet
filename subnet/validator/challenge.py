"""Challenge generation for the validator forward pass.

A challenge is drawn from the taxonomy (`challenge_spec.CHALLENGES`): a
``crop × forecast-horizon`` cell with its own difficulty weight. The generated
`Challenge` carries its `ChallengeSpec` so the forward pass can attribute scores
to the right challenge in the rolling rank history.

In offline/mock mode the validator both poses the task and knows the ground
truth, so it can score miners immediately. On a live subnet the ground truth
arrives later (a farmer's reported harvest) and scoring is deferred.
"""

import json
import os
import random
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta

from subnet.protocol import YieldPredictionSynapse
from subnet.validator.challenge_spec import CHALLENGES, ChallengeSpec

# MVP scope (spec §3): Thailand.
_PROVINCES = ["Chiang Mai", "Khon Kaen", "Ubon Ratchathani"]

# Hardcoded until the `challenges` DB table is ready.
# Swap this for a DB fetch once that table exists.
CHALLENGE_POOL = [
    {"crop": "rice",    "weight": 0.6},
    {"crop": "cassava", "weight": 0.4},
]


@dataclass
class Challenge:
    spec: ChallengeSpec
    synapse: YieldPredictionSynapse
    actual_yield: float       # known in mock mode; 0.0 in live mode (deferred)
    farm_id: int | None = None  # real farm id in live mode; None in mock mode

    @property
    def challenge_id(self) -> str:
        return self.spec.challenge_id


def generate_challenge(spec: ChallengeSpec | None = None) -> Challenge:
    """Build a synthetic yield-prediction task with a known true yield.

    Picks a random challenge from the taxonomy unless one is supplied.
    """
    spec = spec or random.choice(CHALLENGES)
    synapse = YieldPredictionSynapse(
        crop=spec.crop,
        province=random.choice(_PROVINCES),
        field_size=round(random.uniform(5.0, 30.0), 1),
        horizon_days=spec.horizon_days,
        ndvi=[round(random.uniform(0.2, 0.8), 2) for _ in range(5)],
        weather=[{"temp": 28, "rain": round(random.uniform(0, 10), 1)}],
    )
    actual_yield = round(random.uniform(3.5, 4.8), 2)
    return Challenge(spec=spec, synapse=synapse, actual_yield=actual_yield)


def generate_challenge_live(
    spec: ChallengeSpec | None = None,
    backend_url: str = "",
) -> Challenge:
    """Build a challenge from a real farm fetched from the backend API.

    Falls back to ``generate_challenge`` if the backend is unreachable,
    returns no farms, or the FeatureBuilder raises.
    """
    spec = spec or random.choice(CHALLENGES)

    if not backend_url:
        return generate_challenge(spec)

    try:
        url = f"{backend_url.rstrip('/')}/api/public/farms/challenge-pool"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            farms: list[dict] = json.load(resp)
    except Exception:
        return generate_challenge(spec)

    if not farms:
        return generate_challenge(spec)

    matching = [f for f in farms if f.get("crop") == spec.crop]
    farm = random.choice(matching or farms)

    end = date.today()

    try:
        from subnet.data.backend_satellite import BackendSatelliteLoader
        from subnet.data.features import FarmContext, FeatureBuilder

        planting_date_str = farm.get("planting_date")
        planting_date = (
            date.fromisoformat(planting_date_str) if planting_date_str else None
        )
        # Observation window: planting date → today (full growing season).
        # Horizon tells miners how far until harvest, not how much history to fetch.
        start = planting_date if planting_date else end - timedelta(days=180)
        ctx = FarmContext(
            crop=farm["crop"],
            latitude=farm["latitude"],
            longitude=farm["longitude"],
            province=farm.get("province"),
            field_size=farm.get("area_hectares"),
            planting_date=planting_date,
            horizon_days=spec.horizon_days,
        )
       
        # Falls back to StubSatelliteLoader if the endpoint is unreachable.
        satellite = BackendSatelliteLoader(farm_id=farm["farm_id"], backend_url=backend_url)
        synapse = FeatureBuilder(satellite=satellite).build(ctx, start, end)
    except Exception:
        return generate_challenge(spec)

    return Challenge(spec=spec, synapse=synapse, actual_yield=0.0, farm_id=farm["farm_id"])




