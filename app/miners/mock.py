"""Mock miners with fixed prediction values (spec MVP step 4).

Stand-ins for real Bittensor miners: each returns a constant expected yield
(tons/hectare) regardless of the task. Used by the validator workflow to
exercise the end-to-end task -> predict -> aggregate flow without a chain.
"""

from dataclasses import dataclass

from app.models.task import PredictionTask


@dataclass(frozen=True)
class MockMiner:
    hotkey: str
    uid: int
    fixed_yield: float

    def predict(self, task: PredictionTask) -> float:
        """Return this miner's fixed yield prediction for any task."""
        return self.fixed_yield


# Three mock miners with fixed predictions.
MOCK_MINERS: list[MockMiner] = [
    MockMiner(hotkey="miner_a", uid=1, fixed_yield=4.1),
    MockMiner(hotkey="miner_b", uid=2, fixed_yield=4.3),
    MockMiner(hotkey="miner_c", uid=3, fixed_yield=4.2),
]
