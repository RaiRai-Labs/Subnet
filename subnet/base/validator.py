"""Base validator neuron: scoring state, run loop, and weight setting."""

import threading
import time

import bittensor as bt
import numpy as np

from app.core.scoring import normalize_weights
from subnet.base.neuron import BaseNeuron


class BaseValidatorNeuron(BaseNeuron):
    """Maintains per-miner EMA scores and periodically sets weights.

    Subclasses implement `forward()` (build a task, query miners, score them,
    and call `update_scores`).
    """

    def __init__(self, config: bt.Config | None = None) -> None:
        super().__init__(config)

        # EMA of rewards, indexed by miner uid.
        self.scores = np.zeros(self.metagraph.n, dtype=np.float64)

        self.step = 0
        self.should_exit = False
        self._thread: threading.Thread | None = None

    # --- to be implemented by subclasses ---
    def forward(self) -> None:
        raise NotImplementedError

    # --- scoring ---
    def update_scores(self, rewards: list[float], uids: list[int]) -> None:
        alpha = self.config.neuron.moving_average_alpha
        for uid, reward in zip(uids, rewards):
            self.scores[uid] = alpha * reward + (1 - alpha) * self.scores[uid]

    def set_weights(self) -> None:
        weights = normalize_weights(self.scores.tolist())
        if self.config.mock or self.subtensor is None:
            bt.logging.info(
                "[mock] would set weights: "
                + ", ".join(
                    f"uid{u}={w:.3f}" for u, w in zip(self.metagraph.uids, weights)
                )
            )
            return

        self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.config.netuid,
            uids=self.metagraph.uids,
            weights=weights,
            wait_for_inclusion=False,
        )
        bt.logging.info("Weights set on chain.")

    # --- run loop ---
    def run(self) -> None:
        bt.logging.info("Validator run loop started.")
        while not self.should_exit:
            self.forward()
            self.step += 1

            if self.step % self.config.neuron.epoch_length == 0:
                self.set_weights()

            self.sync()
            time.sleep(self.config.neuron.forward_interval)

    # --- background thread / context manager ---
    def run_in_background(self) -> None:
        if self._thread is None:
            self.should_exit = False
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self.should_exit = True
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None

    def __enter__(self) -> "BaseValidatorNeuron":
        self.run_in_background()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
