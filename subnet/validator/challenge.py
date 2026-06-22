"""Challenge generation for the validator forward pass.

In offline/mock mode the validator both poses the task and knows the ground
truth, so it can score miners immediately. On a live subnet the ground truth
arrives later (a farmer's reported harvest) and scoring is deferred.
"""

import random
from dataclasses import dataclass

from subnet.protocol import YieldPredictionSynapse

# MVP scope (spec §3): Thailand, rice + cassava.
_CROPS = ["rice", "cassava"]
_PROVINCES = ["Chiang Mai", "Khon Kaen", "Ubon Ratchathani"]


@dataclass
class Challenge:
    synapse: YieldPredictionSynapse
    actual_yield: float  # hidden ground truth (dev only)


def generate_challenge() -> Challenge:
    """Build a synthetic yield-prediction task with a known true yield."""
    crop = random.choice(_CROPS)
    synapse = YieldPredictionSynapse(
        crop=crop,
        province=random.choice(_PROVINCES),
        field_size=round(random.uniform(5.0, 30.0), 1),
        ndvi=[round(random.uniform(0.2, 0.8), 2) for _ in range(5)],
        weather=[{"temp": 28, "rain": round(random.uniform(0, 10), 1)}],
    )
    actual_yield = round(random.uniform(3.5, 4.8), 2)
    return Challenge(synapse=synapse, actual_yield=actual_yield)
