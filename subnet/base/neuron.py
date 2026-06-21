"""Base neuron: wallet, subtensor, metagraph wiring (chain or offline mock)."""

import bittensor as bt

from subnet.mock import MockMetagraph
from subnet.validator.config import get_config


class BaseNeuron:
    """Common setup shared by validators and miners.

    In ``--mock`` mode no chain connection is made: a `MockMetagraph` and the
    in-process mock miners stand in for the network so the loop runs offline.
    """

    def __init__(self, config: bt.Config | None = None) -> None:
        self.config = config or get_config()

        bt.logging.enable_info()

        if self.config.mock:
            self.wallet = None
            self.subtensor = None
            self.dendrite = None
            self.metagraph = MockMetagraph()
            self.uid = 0
            bt.logging.info("Neuron starting in MOCK mode (offline, no chain).")
        else:
            self.wallet = bt.Wallet(config=self.config)
            self.subtensor = bt.Subtensor(config=self.config)
            self.metagraph = self.subtensor.metagraph(self.config.netuid)
            self.dendrite = bt.Dendrite(wallet=self.wallet)
            self.uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(
                f"Neuron on netuid {self.config.netuid} | uid {self.uid} | "
                f"{self.subtensor.network}"
            )

    def sync(self) -> None:
        """Resync the metagraph from chain (no-op in mock mode)."""
        if not self.config.mock and self.subtensor is not None:
            self.metagraph.sync(subtensor=self.subtensor)
