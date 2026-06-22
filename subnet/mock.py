"""Offline mock objects for running the validator without a chain.

`MockMetagraph` mirrors the handful of `bt.Metagraph` attributes the validator
loop touches, populated from the in-process mock miners.
"""

from app.miners.mock import MOCK_MINERS


class MockMetagraph:
    """Minimal stand-in for ``bittensor.Metagraph`` in offline dev mode."""

    def __init__(self) -> None:
        self.n = len(MOCK_MINERS)
        self.uids = list(range(self.n))
        self.hotkeys = [m.hotkey for m in MOCK_MINERS]
        self.axons = []  # no real axons offline; miners are queried in-process

    def sync(self, *args, **kwargs) -> None:  # noqa: D401 - no-op offline
        """No-op: there is no chain to resync against."""
