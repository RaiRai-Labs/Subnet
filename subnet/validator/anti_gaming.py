"""Anti-gaming guards (Phase 4).

Two protections applied during the validator forward pass:

- **Shape / sanity penalties** — a malformed or out-of-range prediction is
  treated as a non-response (worst reward), so a miner cannot farm reward with
  garbage or absurd values.
- **Collusion detection** — miners whose prediction streams track each other too
  closely across recent rounds are likely copying. The newer-registered hotkey
  of each colluding pair is penalized; the original is left alone.

Pure logic, no chain or DB — safe to unit-test and to import into the neuron.
"""

import math
from collections import deque

# Plausible yield range for the MVP crops, tons/hectare (spec §3: rice/cassava
# in Thailand sit well inside this). Anything outside is treated as malformed.
MIN_YIELD = 0.0
MAX_YIELD = 50.0


def is_valid_prediction(value) -> bool:
    """True if a prediction is a finite number within the plausible yield range."""
    if value is None or isinstance(value, bool):
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(v):  # NaN / ±inf
        return False
    return MIN_YIELD <= v <= MAX_YIELD


class CollusionDetector:
    """Flags miners with suspiciously similar prediction streams.

    Keeps a rolling window of each miner's recent predictions. Two miners are
    deemed colluding when, over at least ``min_samples`` shared rounds, their
    mean absolute prediction difference is ``<= threshold``. The newer of the
    pair (higher registration order) is flagged for penalty.
    """

    def __init__(
        self, window: int = 20, threshold: float = 0.02, min_samples: int = 5
    ) -> None:
        self.window = window
        self.threshold = threshold
        self.min_samples = min_samples
        self._preds: dict[int, deque] = {}  # uid -> deque[(round, value)]

    def record(self, round_no: int, predictions: dict[int, float]) -> None:
        """Append this round's valid predictions, keyed by miner uid."""
        for uid, value in predictions.items():
            dq = self._preds.setdefault(uid, deque(maxlen=self.window))
            dq.append((round_no, value))

    def _mean_abs_diff(self, a: int, b: int) -> float | None:
        """Mean abs prediction diff over rounds both answered (None if too few)."""
        rounds_a = dict(self._preds[a])
        rounds_b = dict(self._preds[b])
        common = rounds_a.keys() & rounds_b.keys()
        if len(common) < self.min_samples:
            return None
        return sum(abs(rounds_a[r] - rounds_b[r]) for r in common) / len(common)

    def detect(self, registration_order: dict[int, int]) -> set[int]:
        """Return uids to penalize.

        ``registration_order`` maps uid → an ordering where a *higher* value
        means *newer* registration (e.g. block_at_registration, or uid as a
        proxy offline). The newer miner of each colluding pair is flagged.
        """
        flagged: set[int] = set()
        uids = sorted(self._preds)
        for i, a in enumerate(uids):
            for b in uids[i + 1:]:
                diff = self._mean_abs_diff(a, b)
                if diff is not None and diff <= self.threshold:
                    newer = (
                        a
                        if registration_order.get(a, a) > registration_order.get(b, b)
                        else b
                    )
                    flagged.add(newer)
        return flagged
