"""Validator forward pass: pose a task, query miners, score responses."""

import bittensor as bt

from app.core.scoring import competition_rank, dual_metric_error, winner_take_most
from app.miners.mock import MOCK_MINERS
from subnet.validator.anti_gaming import is_valid_prediction
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

    # Shape/sanity penalty (Phase 4): malformed or out-of-range predictions are
    # treated as non-responses. Valid responders go on to collusion screening.
    valid_uids: list[int] = []
    valid_preds: list[float] = []
    absent: list[int] = []
    for uid, prediction in zip(uids, predictions):
        if is_valid_prediction(prediction):
            valid_uids.append(uid)
            valid_preds.append(prediction)
        else:
            absent.append(uid)

    # Collusion penalty (Phase 4): copy-cat prediction streams are excluded from
    # scoring (the newer-registered hotkey of each pair forfeits the round).
    validator.collusion_detector.record(validator.step, dict(zip(valid_uids, valid_preds)))
    colluders = validator.collusion_detector.detect(validator.registration_order())

    active_uids = [u for u in valid_uids if u not in colluders]
    active_preds = [p for u, p in zip(valid_uids, valid_preds) if u not in colluders]
    excluded = [u for u in uids if u not in active_uids]  # absent / invalid / colluding

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

    # Fold competition ranks into the rolling per-challenge window (Phase 3);
    # excluded miners accrue absence strikes so liveness drops stale history.
    cid = challenge.challenge_id
    validator.rank_tracker.record(cid, validator.step, ranks_by_uid)
    validator.rank_tracker.mark_absent(cid, excluded)
    validator.persist_round_ranks(
        cid, validator.step, ranks_by_uid, dict(zip(uids, rewards))
    )

    rolling = validator.rank_tracker.rolling_ranks(cid)
    best = validator.rank_tracker.best_miner(cid)

    flags = ""
    if colluders:
        flags += f" | colluding={sorted(colluders)}"
    if absent:
        flags += f" | absent/invalid={absent}"
    bt.logging.info(
        f"step {validator.step} | challenge {cid} (w={challenge.spec.weight}) "
        f"@ {challenge.synapse.province} | actual={challenge.actual_yield} | "
        + ", ".join(
            f"uid{u}:"
            + ("skip" if u in excluded else f"pred={p}->w={rewards[i]:.3f}->rank{ranks_by_uid.get(u)}")
            for i, (u, p) in enumerate(zip(uids, predictions))
        )
        + f" | best=uid{best} | rolling_ranks="
        + "{" + ", ".join(f"{u}:{avg:.2f}" for u, avg in sorted(rolling.items())) + "}"
        + flags
    )
