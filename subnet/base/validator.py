"""Base validator neuron: scoring state, run loop, and weight setting."""

import asyncio
import threading
import time

import bittensor as bt
import numpy as np

from app.core.scoring import normalize_weights
from subnet import __spec_version__
from subnet.base.neuron import BaseNeuron
from subnet.validator.rank_history import RankTracker


class _AsyncRunner:
    """Runs coroutines on one dedicated background event-loop thread.

    A single long-lived loop avoids binding the async DB engine to multiple
    transient loops (which asyncpg / SQLAlchemy do not allow).
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro, timeout: float = 30.0):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)


class BaseValidatorNeuron(BaseNeuron):
    """Maintains per-miner EMA scores and periodically sets weights.

    Subclasses implement `forward()` (build a task, query miners, score them,
    and call `update_scores`).
    """

    def __init__(self, config: bt.Config | None = None) -> None:
        super().__init__(config)

        # EMA of rewards, indexed by miner uid.
        self.scores = np.zeros(self.metagraph.n, dtype=np.float64)

        # Detect commit-reveal once; set_weights routes accordingly.
        self._last_weights_block = 0
        if self.config.mock or self.subtensor is None:
            self.commit_reveal_enabled = False
            self.weights_rate_limit = 0
        else:
            self.commit_reveal_enabled = self.subtensor.commit_reveal_enabled(
                self.config.netuid
            )
            hp = self.subtensor.get_subnet_hyperparameters(self.config.netuid)
            self.weights_rate_limit = int(getattr(hp, "weights_rate_limit", 0) or 0)
            bt.logging.info(
                f"Commit-reveal weights "
                f"{'ENABLED' if self.commit_reveal_enabled else 'disabled'} "
                f"on netuid {self.config.netuid} | "
                f"weights_rate_limit={self.weights_rate_limit} blocks"
            )

        # Rolling per-challenge rank history (in memory; optionally to Postgres).
        self.rank_window = int(getattr(self.config.neuron, "rank_window", 10) or 10)
        self.rank_tracker = RankTracker(window=self.rank_window)
        self.persist_ranks = bool(
            getattr(self.config.neuron, "persist_ranks", False)
        ) and not self.config.mock
        self._async_runner: _AsyncRunner | None = None
        self._challenges_seeded = False

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

    def persist_round_ranks(
        self,
        challenge_id: str,
        round_no: int,
        ranks: dict[int, int],
        scores: dict[int, float] | None = None,
        hotkeys: dict[int, str] | None = None,
    ) -> None:
        """Persist one round's challenge ranks to Postgres (best-effort, opt-in).

        No-op unless ``--neuron.persist_ranks`` is set on a live (non-mock) run.
        Failures are logged, never fatal to the run loop.
        """
        if not self.persist_ranks:
            return
        try:
            from app.core.database import AsyncSessionLocal
            from app.core.rank_history import (
                record_round_ranks,
                seed_challenges,
                update_best_miner,
            )

            seed = not self._challenges_seeded

            async def _do() -> None:
                async with AsyncSessionLocal() as db:
                    if seed:
                        await seed_challenges(db)
                    await record_round_ranks(
                        db, challenge_id, round_no, ranks, scores, hotkeys
                    )
                    await update_best_miner(db, challenge_id, self.rank_window)

            if self._async_runner is None:
                self._async_runner = _AsyncRunner()
            self._async_runner.run(_do())
            self._challenges_seeded = True
        except Exception as exc:  # noqa: BLE001 - persistence must never crash the loop
            bt.logging.warning(f"rank persistence failed: {exc}")

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

        # Respect the chain's weights rate limit (one set per N blocks).
        current_block = self.subtensor.get_current_block()
        elapsed = current_block - self._last_weights_block
        if self._last_weights_block and elapsed < self.weights_rate_limit:
            bt.logging.debug(
                f"Skip set_weights: {elapsed}/{self.weights_rate_limit} blocks since last set"
            )
            return

        mode = "commit-reveal" if self.commit_reveal_enabled else "direct"
        bt.logging.info(f"Submitting weights via {mode} (version_key={__spec_version__})")

        # set_weights auto-routes to the commit-reveal extrinsic when the subnet
        # has it enabled; version_key ties a commit to its later reveal.
        result = self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.config.netuid,
            uids=self.metagraph.uids,
            weights=weights,
            version_key=__spec_version__,
            wait_for_inclusion=True,
        )
        # set_weights may return an ExtrinsicResponse or a (success, msg) tuple.
        if isinstance(result, tuple):
            success, message = result
        else:
            success = getattr(result, "success", bool(result))
            message = getattr(result, "message", "")
        if success:
            self._last_weights_block = current_block
            bt.logging.info(f"Weights submitted on chain ({mode}) at block {current_block}.")
        else:
            bt.logging.warning(f"set_weights failed: {message}")

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
        if self._async_runner is not None:
            self._async_runner.stop()
            self._async_runner = None

    def __enter__(self) -> "BaseValidatorNeuron":
        self.run_in_background()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
