"""Base miner neuron: serves an axon that answers prediction requests."""

import threading
import time
from typing import Tuple

import bittensor as bt

from subnet.base.neuron import BaseNeuron
from subnet.protocol import YieldPredictionSynapse


class BaseMinerNeuron(BaseNeuron):
    """Serves a `YieldPredictionSynapse` axon and keeps the metagraph synced.

    Subclasses implement `predict(synapse)` returning the filled synapse.
    """

    def __init__(self, config: bt.Config | None = None) -> None:
        super().__init__(config)

        if self.config.mock:
            self.axon = None
        else:
            self.axon = bt.Axon(wallet=self.wallet, config=self.config)
            self.axon.attach(
                forward_fn=self._forward,
                blacklist_fn=self._blacklist,
                priority_fn=self._priority,
            )

        self.step = 0
        self.should_exit = False
        self._thread: threading.Thread | None = None

    # --- to be implemented by subclasses ---
    def predict(self, synapse: YieldPredictionSynapse) -> YieldPredictionSynapse:
        raise NotImplementedError

    # --- axon handlers ---
    async def _forward(self, synapse: YieldPredictionSynapse) -> YieldPredictionSynapse:
        return self.predict(synapse)

    async def _blacklist(self, synapse: YieldPredictionSynapse) -> Tuple[bool, str]:
        dend = synapse.dendrite
        if dend is None or dend.hotkey is None:
            return True, "missing dendrite/hotkey"
        if dend.hotkey not in self.metagraph.hotkeys:
            return True, "unrecognized hotkey"
        return False, "ok"

    async def _priority(self, synapse: YieldPredictionSynapse) -> float:
        dend = synapse.dendrite
        if dend is None or dend.hotkey not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(dend.hotkey)
        return float(self.metagraph.S[uid])

    # --- run loop ---
    def run(self) -> None:
        self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
        self.axon.start()
        bt.logging.info(
            f"Miner axon serving on netuid {self.config.netuid} | uid {self.uid}"
        )
        while not self.should_exit:
            time.sleep(5)
            self.step += 1
            if self.step % 12 == 0:
                self.sync()

    def run_in_background(self) -> None:
        if self._thread is None:
            self.should_exit = False
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self.should_exit = True
        if self.axon is not None:
            self.axon.stop()
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None

    def __enter__(self) -> "BaseMinerNeuron":
        self.run_in_background()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
