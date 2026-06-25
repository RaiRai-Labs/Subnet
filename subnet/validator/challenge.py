"""Challenge generation for the validator forward pass.

A challenge is drawn from the taxonomy (`challenge_spec.CHALLENGES`): a
``crop × forecast-horizon`` cell with its own difficulty weight. The generated
`Challenge` carries its `ChallengeSpec` so the forward pass can attribute scores
to the right challenge in the rolling rank history.

In offline/mock mode the validator both poses the task and knows the ground
truth, so it can score miners immediately. On a live subnet the ground truth
arrives later (a farmer's reported harvest) and scoring is deferred.
"""

import random
from dataclasses import dataclass

from subnet.protocol import YieldPredictionSynapse
from subnet.validator.challenge_spec import CHALLENGES, ChallengeSpec

# MVP scope (spec §3): Thailand.
_PROVINCES = ["Chiang Mai", "Khon Kaen", "Ubon Ratchathani"]


@dataclass
class Challenge:
    spec: ChallengeSpec
    synapse: YieldPredictionSynapse
    actual_yield: float  # hidden ground truth (dev only)

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
