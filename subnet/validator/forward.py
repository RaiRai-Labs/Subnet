"""Validator forward pass: pose a task, query miners, score responses."""

import bittensor as bt

from app.core.scoring import mean_absolute_error, rank_score
from app.miners.mock import MOCK_MINERS
from subnet.validator.challenge import Challenge, generate_challenge


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
    uids = list(validator.metagraph.uids)

    predictions = query_miners(validator, challenge, uids)

    rewards: list[float] = []
    for prediction in predictions:
        if prediction is None:
            rewards.append(0.0)
            continue
        mae = mean_absolute_error(prediction, challenge.actual_yield)
        rewards.append(rank_score(mae))

    validator.update_scores(rewards, uids)

    bt.logging.info(
        f"step {validator.step} | {challenge.synapse.crop} "
        f"@ {challenge.synapse.province} | actual={challenge.actual_yield} | "
        + ", ".join(
            f"uid{u}:pred={p}->r={r:.3f}"
            for u, p, r in zip(uids, predictions, rewards)
        )
    )
