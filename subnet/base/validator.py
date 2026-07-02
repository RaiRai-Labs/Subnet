"""Base validator neuron: scoring state, run loop, and weight setting."""

import asyncio
import threading
import time

import bittensor as bt
import numpy as np

from app.core.scoring import normalize_weights
from subnet import __spec_version__
from subnet.base.neuron import BaseNeuron
from subnet.validator.anti_gaming import CollusionDetector
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
        allowed_absence = int(getattr(self.config.neuron, "allowed_absence", 3) or 3)
        self.rank_tracker = RankTracker(
            window=self.rank_window, allowed_absence=allowed_absence
        )
        # Anti-gaming: flag miners with copy-cat prediction streams.
        self.collusion_detector = CollusionDetector(
            threshold=float(getattr(self.config.neuron, "collusion_threshold", 0.02))
        )
        # In live mode persistence is required for deferred scoring to work —
        # default True. Only False in mock (offline dev) mode, or if explicitly
        # disabled via --neuron.persist_ranks false.
        self.persist_ranks = bool(
            getattr(self.config.neuron, "persist_ranks", not self.config.mock)
        ) and not self.config.mock
        self._async_runner: _AsyncRunner | None = None
        self._challenges_seeded = False

        self.step = 0
        self.should_exit = False
        self._thread: threading.Thread | None = None

    # --- to be implemented by subclasses ---
    def forward(self) -> None:
        raise NotImplementedError

    def registration_order(self) -> dict[int, int]:
        """uid → registration ordinal (higher == newer), for collusion penalties.

        Uses on-chain ``block_at_registration`` when available; offline (mock)
        falls back to uid, which increases with registration order.
        """
        blocks = getattr(self.metagraph, "block_at_registration", None)
        if blocks is not None:
            return {int(u): int(blocks[u]) for u in self.metagraph.uids}
        return {int(u): int(u) for u in self.metagraph.uids}

    # --- scoring ---
    def update_scores(self, rewards: list[float], uids: list[int]) -> None:
        alpha = self.config.neuron.moving_average_alpha
        for uid, reward in zip(uids, rewards):
            self.scores[uid] = alpha * reward + (1 - alpha) * self.scores[uid]

    def drop_scores(self, uids: set[int]) -> None:
        """Zero EMA scores for miners dropped by liveness handling."""
        for uid in uids:
            self.scores[uid] = 0.0

    def persist_task(self, challenge) -> int | None:
        """Save a live challenge as a PredictionTask in Postgres so the backend
        can look it up by farm_id when the farmer submits their harvest.

        Returns the PredictionTask PK (used to link MinerResponse rows), or None
        if persistence is disabled / the challenge has no farm_id.

        No-op unless ``--neuron.persist_ranks`` is set (reuses the same gate).
        Failures are logged and never fatal.
        """
        if not self.persist_ranks or challenge.farm_id is None:
            return None
        try:
            import uuid
            from app.core.database import AsyncSessionLocal
            from app.models.task import PredictionTask

            task_id = f"task_{uuid.uuid4().hex[:12]}"
            syn = challenge.synapse

            async def _do() -> int:
                async with AsyncSessionLocal() as db:
                    from sqlalchemy import select as _select
                    from app.models.task import TaskStatus

                    # One task per (farm, crop, horizon) per season — no duplicates.
                    existing = await db.scalar(
                        _select(PredictionTask).where(
                            PredictionTask.farm_id == challenge.farm_id,
                            PredictionTask.crop == syn.crop,
                            PredictionTask.horizon_days == getattr(syn, "horizon_days", None),
                            PredictionTask.status.in_([TaskStatus.open, TaskStatus.completed]),
                        )
                    )
                    if existing:
                        bt.logging.debug(
                            f"[task] skip duplicate — {existing.task_id} already open for "
                            f"farm_id={challenge.farm_id} crop={syn.crop} "
                            f"horizon={syn.horizon_days}d"
                        )
                        return existing.id

                    task = PredictionTask(
                        task_id=task_id,
                        farm_id=challenge.farm_id,
                        crop=syn.crop,
                        province=getattr(syn, "province", None),
                        field_size=getattr(syn, "field_size", None),
                        planting_date=getattr(syn, "planting_date", None),
                        horizon_days=getattr(syn, "horizon_days", None),
                        ndvi=syn.ndvi,
                        evi=getattr(syn, "evi", None),
                        ndwi=getattr(syn, "ndwi", None),
                        weather=syn.weather,
                    )
                    db.add(task)
                    await db.commit()
                    await db.refresh(task)
                    return task.id

            if self._async_runner is None:
                self._async_runner = _AsyncRunner()
            task_db_id: int = self._async_runner.run(_do())
            bt.logging.debug(f"[task] persisted task_id={task_id} farm_id={challenge.farm_id}")
            return task_db_id
        except Exception as exc:
            bt.logging.warning(f"task persistence failed: {exc}")
            return None

    def persist_miner_responses(
        self,
        task_db_id: int,
        valid_preds: dict[int, float],
        confidences: dict[int, float] | None = None,
    ) -> None:
        """Save each miner's prediction as a MinerResponse row linked to task_db_id.

        Called in live mode right after query_miners(). Only valid predictions are
        stored (absent / invalid miners are excluded upstream). Rows are marked
        revealed=True / hash_valid=True because the subnet dendrite path has no
        commit-reveal phase — the prediction arrives directly.

        These rows are what _run_scoring() (responses.py) reads when the farmer
        later submits their actual harvest yield.
        """
        if not self.persist_ranks or not valid_preds:
            return
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.response import MinerResponse

            hotkeys: dict[int, str] = {
                int(u): self.metagraph.hotkeys[u] for u in self.metagraph.uids
            }

            async def _do() -> None:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                async with AsyncSessionLocal() as db:
                    for uid, prediction in valid_preds.items():
                        hotkey = hotkeys.get(uid, "")
                        stmt = (
                            pg_insert(MinerResponse)
                            .values(
                                task_id=task_db_id,
                                miner_uid=uid,
                                miner_hotkey=hotkey,
                                expected_yield=prediction,
                                confidence=confidences.get(uid) if confidences else None,
                                revealed=True,
                                hash_valid=True,
                            )
                            .on_conflict_do_update(
                                constraint="uq_task_miner",
                                set_={
                                    "expected_yield": prediction,
                                    "confidence": confidences.get(uid) if confidences else None,
                                },
                            )
                        )
                        await db.execute(stmt)
                    await db.commit()

            if self._async_runner is None:
                self._async_runner = _AsyncRunner()
            self._async_runner.run(_do())
            bt.logging.debug(
                f"[task] saved {len(valid_preds)} miner response(s) for task_db_id={task_db_id}"
            )
        except Exception as exc:
            bt.logging.warning(f"miner response persistence failed: {exc}")

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
