"""Validator forward pass: pose a task, query miners, score responses."""

import os

import bittensor as bt

from app.core.scoring import (
    aggregate_challenge_weights,
    competition_rank,
    dual_metric_error,
    winner_take_most,
)
from app.miners.mock import MOCK_MINERS
from subnet.validator.anti_gaming import is_valid_prediction
from subnet.validator.challenge import Challenge, generate_challenge, generate_challenge_live
from subnet.validator.challenge_spec import CHALLENGES

_BACKEND_URL = os.getenv("BACKEND_URL", "")


def _apply_deferred_scores(validator, uids: list[int]) -> None:
    """Pull weights from newly-scored tasks and fold them into the validator EMA.

    Runs once per forward pass in live mode. Tracks which task_ids have already
    been applied so the same task never updates the EMA twice.
    """
    if not hasattr(validator, "_applied_task_ids"):
        validator._applied_task_ids: set[str] = set()
    applied: set[str] = validator._applied_task_ids

    async def _fetch() -> list[dict]:
        from app.core.database import AsyncSessionLocal
        from app.models.response import MinerResponse
        from app.models.task import PredictionTask, TaskStatus
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            tasks = list(
                await db.scalars(
                    select(PredictionTask).where(PredictionTask.status == TaskStatus.scored)
                )
            )
            new_tasks = [t for t in tasks if t.task_id not in applied]
            if not new_tasks:
                return []

            rows: list[dict] = []
            for task in new_tasks:
                responses = list(
                    await db.scalars(
                        select(MinerResponse).where(
                            MinerResponse.task_id == task.id,
                            MinerResponse.miner_uid.isnot(None),
                            MinerResponse.weight.isnot(None),
                        )
                    )
                )
                for r in responses:
                    rows.append(
                        {"task_id": task.task_id, "miner_uid": r.miner_uid, "weight": r.weight}
                    )
            return rows

    try:
        if validator._async_runner is None:
            from subnet.base.validator import _AsyncRunner
            validator._async_runner = _AsyncRunner()
        scored = validator._async_runner.run(_fetch())
    except Exception as exc:
        bt.logging.warning(f"[deferred scoring] DB fetch failed: {exc}")
        return

    if not scored:
        return

    # One uid may appear in several tasks — take the best weight across them.
    uid_to_weight: dict[int, float] = {}
    new_task_ids: set[str] = set()
    for row in scored:
        uid = row["miner_uid"]
        uid_to_weight[uid] = max(uid_to_weight.get(uid, 0.0), row["weight"])
        new_task_ids.add(row["task_id"])

    # Only update miners present in this scored batch — injecting 0.0 for
    # unrelated miners would decay their EMA without cause.
    deferred_uids = [u for u in uids if u in uid_to_weight]
    deferred_rewards = [uid_to_weight[u] for u in deferred_uids]
    validator.update_scores(deferred_rewards, deferred_uids)
    validator._applied_task_ids.update(new_task_ids)
    bt.logging.info(
        f"[deferred scoring] applied {len(new_task_ids)} task(s) → "
        + ", ".join(f"uid{u}:{uid_to_weight[u]:.3f}" for u in uids if u in uid_to_weight)
    )


def get_query_uids(validator) -> list[int]:
    """Miner uids to query: all in mock mode; serving non-self uids on chain."""
    if validator.config.mock:
        return list(validator.metagraph.uids)
    return [
        int(uid)
        for uid in validator.metagraph.uids
        if int(uid) != validator.uid and validator.metagraph.axons[uid].is_serving
    ]


def query_miners(validator, challenge: Challenge, uids: list[int]) -> list[float | None]:
    """Return each miner's predicted yield (None if it did not respond)."""
    if validator.config.mock:
        return [miner.predict(challenge.synapse) for miner in MOCK_MINERS]

    axons = [validator.metagraph.axons[uid] for uid in uids]
    responses = validator.dendrite.query(
        axons=axons, synapse=challenge.synapse, deserialize=True
    )
    return list(responses)


def forward(validator) -> None:
    # Log the data-source mode once on the first forward pass so operators can
    # immediately see whether the validator is using real farm data or synthetic
    # fallback data. BACKEND_URL missing means the scoring pipeline is broken.
    if validator.step == 0:
        live_mode_check = not validator.config.mock
        if not live_mode_check:
            bt.logging.info("[challenge] MOCK mode — synthetic challenges, no chain")
        elif _BACKEND_URL:
            bt.logging.info(
                f"[challenge] LIVE mode — fetching real farm data from {_BACKEND_URL}"
            )
        else:
            bt.logging.warning(
                "[challenge] LIVE mode but BACKEND_URL is not set — "
                "falling back to SYNTHETIC challenges. "
                "No real farm data will be used and the scoring pipeline is broken. "
                "Set BACKEND_URL in your .env to fix this."
            )

    uids = get_query_uids(validator)

    if not uids:
        bt.logging.info(f"step {validator.step} | no miners to query yet")
        return

    per_challenge_rewards: list[list[float]] = []
    challenge_weights: list[float] = []
    reg_order = validator.registration_order()
    all_excluded: set[int] = set()  # absent + invalid + colluding across all challenges

    live_mode = not validator.config.mock

    # Detect colluders from PREVIOUS rounds' history before recording anything
    # new this round. This keeps colluder status fixed across all challenges in
    # the same forward pass — otherwise status can flip mid-round as record()
    # adds data and detect() sees a moving window.
    prior_colluders = validator.collusion_detector.detect(reg_order)

    for spec in CHALLENGES:
        # Live mode: real farm data from backend + deferred scoring.
        # Mock mode: synthetic data + immediate scoring against known yield.
        if live_mode:
            challenge = generate_challenge_live(spec=spec, backend_url=_BACKEND_URL)
            task_db_id = validator.persist_task(challenge)
        else:
            challenge = generate_challenge(spec=spec)
            task_db_id = None

        predictions = query_miners(validator, challenge, uids)

        # Miners that did not respond at all.
        absent: set[int] = {u for u, p in zip(uids, predictions) if p is None}

        # Shape/sanity filter — malformed/out-of-range treated as non-response.
        valid_preds: dict[int, float] = {
            u: p
            for u, p in zip(uids, predictions)
            if p is not None and is_valid_prediction(p)
        }
        # Responded but failed sanity check — treated same as absent for liveness.
        invalid: set[int] = {
            u for u, p in zip(uids, predictions)
            if p is not None and not is_valid_prediction(p)
        }

        # Live mode: persist each miner's prediction so _run_scoring() can score
        # them months later when the farmer submits their actual harvest yield.
        if live_mode and task_db_id is not None:
            validator.persist_miner_responses(task_db_id, valid_preds)

        # Record this challenge's predictions for future collusion detection.
        # Use prior_colluders (detected before this round) so colluder status
        # stays fixed across all 6 challenges in this forward pass.
        validator.collusion_detector.record(validator.step, valid_preds)

        # Active = valid responses with known colluders removed.
        active_uids = [u for u in valid_preds if u not in prior_colluders]
        active_preds = [valid_preds[u] for u in active_uids]

        # Everyone who isn't actively scoring accrues an absence strike:
        # absent (no response) + invalid (bad response) + colluding.
        excluded: set[int] = absent | invalid | (set(valid_preds) & prior_colluders)
        all_excluded |= excluded

        ch_rewards = [0.0] * len(uids)
        ranks_for_history: dict[int, float] = {}

        if active_uids:
            if not live_mode:
                # Mock: score immediately; record error-based ranks for history.
                errors = [dual_metric_error(p, challenge.actual_yield) for p in active_preds]
                ranks = competition_rank(errors)
                active_rewards = winner_take_most(ranks)
                uid_to_reward = dict(zip(active_uids, active_rewards))
                ch_rewards = [uid_to_reward.get(u, 0.0) for u in uids]
                ranks_for_history = dict(zip(active_uids, ranks))
                validator.rank_tracker.record(spec.challenge_id, validator.step, ranks_for_history)
                validator.persist_round_ranks(
                    spec.challenge_id, validator.step, ranks_for_history,
                    dict(zip(uids, ch_rewards)),
                )
                bt.logging.info(
                    f"[{spec.challenge_id}] actual={challenge.actual_yield} | "
                    + " | ".join(
                        f"uid{u}: err={e:.4f} rank={r} w={w:.4f}"
                        for u, e, r, w in zip(active_uids, errors, ranks, active_rewards)
                    )
                )
            else:
                # Live: ground truth unknown — skip rank history entirely.
                # Recording prediction-based ranks would let miners game the
                # history by always predicting extreme values. Rank history in
                # live mode is only updated via mark_absent (absence strikes).
                bt.logging.info(
                    f"[{spec.challenge_id}] live challenge sent to {len(active_uids)} miner(s)"
                    + (f" | farm_id={challenge.farm_id}" if challenge.farm_id else "")
                )

        # Liveness: absent + invalid + colluding all accrue absence strikes.
        # Miners that exceed the allowed absence threshold are dropped.
        dropped = validator.rank_tracker.mark_absent(spec.challenge_id, excluded)
        if dropped:
            validator.drop_scores(dropped)
            bt.logging.info(
                f"[liveness] uid(s) {sorted(dropped)} dropped after "
                f"{validator.rank_tracker.allowed_absence} consecutive no-shows "
                f"on '{spec.challenge_id}' — scores reset to 0"
            )

        per_challenge_rewards.append(ch_rewards)
        challenge_weights.append(spec.weight)

    # Re-detect colluders with the full round's data and zero their aggregate rewards.
    colluders = validator.collusion_detector.detect(reg_order)
    rewards = aggregate_challenge_weights(per_challenge_rewards, challenge_weights)

    if colluders:
        for i, u in enumerate(uids):
            if u in colluders:
                rewards[i] = 0.0
        bt.logging.info(f"[anti-gaming] zeroed colluding uid(s): {sorted(colluders)}")

    # In mock mode score immediately; in live mode weights come exclusively from
    # deferred scoring (harvest submissions) — calling update_scores with the
    # all-zero live rewards would silently decay EMA scores toward zero every round.
    if not live_mode:
        validator.update_scores(rewards, uids)
    else:
        _apply_deferred_scores(validator, uids)

    flags = ""
    if colluders:
        flags += f" | colluding={sorted(colluders)}"
    if all_excluded:
        flags += f" | excluded={sorted(all_excluded)}"
    bt.logging.info(
        f"step {validator.step} | final aggregated weights | "
        + ", ".join(f"uid{u}:w={rewards[i]:.3f}" for i, u in enumerate(uids))
        + flags
    )
