"""Validator forward pass: pose a task, query miners, score responses."""

import bittensor as bt

from app.core.scoring import competition_rank, dual_metric_error, winner_take_most
from app.miners.mock import MOCK_MINERS
from subnet.validator.challenge import Challenge, generate_challenge


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
        # Offline: query the in-process mock miners directly.
        return [miner.predict(challenge.synapse) for miner in MOCK_MINERS]

    axons = [validator.metagraph.axons[uid] for uid in uids]
    responses = validator.dendrite.query(
        axons=axons, synapse=challenge.synapse, deserialize=True
    )
    return list(responses)


def forward(validator) -> None:
    challenge = generate_challenge()
    uids = get_query_uids(validator)

    if not uids:
        bt.logging.info(f"step {validator.step} | no miners to query yet")
        return

    predictions = query_miners(validator, challenge, uids)

    # Responding miners only; silent miners earn no reward/rank this round.
    active_uids = [u for u, p in zip(uids, predictions) if p is not None]
    active_preds = [p for p in predictions if p is not None]

    rewards = [0.0] * len(uids)
    ranks_by_uid: dict[int, float] = {}
    if active_uids:
        # Dual-metric error -> competition rank (ties averaged) -> winner-take-most.
        errors = [dual_metric_error(p, challenge.actual_yield) for p in active_preds]
        ranks = competition_rank(errors)  # rank 1 = lowest error = best
        active_rewards = winner_take_most(ranks)
        uid_to_reward = dict(zip(active_uids, active_rewards))
        rewards = [uid_to_reward.get(u, 0.0) for u in uids]
        ranks_by_uid = dict(zip(active_uids, ranks))

    validator.update_scores(rewards, uids)

    # Fold this round's competition ranks into the rolling per-challenge window,
    # so standings reflect sustained per-challenge skill (Phase 3).
    cid = challenge.challenge_id
    validator.rank_tracker.record(cid, validator.step, ranks_by_uid)
    validator.persist_round_ranks(
        cid, validator.step, ranks_by_uid, dict(zip(uids, rewards))
    )

    rolling = validator.rank_tracker.rolling_ranks(cid)
    best = validator.rank_tracker.best_miner(cid)

    bt.logging.info(
        f"step {validator.step} | challenge {cid} (w={challenge.spec.weight}) "
        f"@ {challenge.synapse.province} | actual={challenge.actual_yield} | "
        + ", ".join(
            f"uid{u}:"
            + ("skip" if p is None else f"pred={p}->w={rewards[i]:.3f}->rank{ranks_by_uid.get(u)}")
            for i, (u, p) in enumerate(zip(uids, predictions))
        )
        + f" | best=uid{best} | rolling_ranks="
        + "{" + ", ".join(f"{u}:{avg:.2f}" for u, avg in sorted(rolling.items())) + "}"
    )
