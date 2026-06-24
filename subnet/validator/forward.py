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

    # Step 1: separate responding miners from silent ones.
    # Silent miners are skipped entirely — no penalty, no rank, no reward.
    active_uids  = [u for u, p in zip(uids, predictions) if p is not None]
    active_preds = [p for p in predictions if p is not None]

    rewards = [0.0] * len(uids)

    if active_uids:
        # Step 2: compute dual-metric error only for miners who responded.
        errors = [dual_metric_error(p, challenge.actual_yield) for p in active_preds]

        # Step 3: rank responding miners competitively (ties averaged).
        ranks = competition_rank(errors)

        # Step 4: winner-take-most weights across responding miners only.
        active_rewards = winner_take_most(ranks)

        # Map active rewards back to full uid list (silent miners stay 0.0).
        uid_to_reward = dict(zip(active_uids, active_rewards))
        rewards = [uid_to_reward.get(u, 0.0) for u in uids]

    validator.update_scores(rewards, uids)

    bt.logging.info(
        f"step {validator.step} | {challenge.synapse.crop} "
        f"@ {challenge.synapse.province} | actual={challenge.actual_yield} | "
        + ", ".join(
            f"uid{u}:{'skip' if p is None else f'pred={p}->w={rewards[i]:.3f}'}"
            for i, (u, p) in enumerate(zip(uids, predictions))
        )
    )
