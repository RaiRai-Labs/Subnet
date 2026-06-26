"""
Quick smoke-test: runs one validator forward pass in-process.

Shows dual-metric error → competition rank → winner-take-most weights
for the three mock miners. No bittensor / chain required.

Usage:
    python scripts/demo_scoring.py
"""

import random
from app.core.scoring import (
    aggregate_challenge_weights,
    competition_rank,
    dual_metric_error,
    winner_take_most,
)

# ── Mock miners (same fixed yields as app/miners/mock.py) ─────────────────────
MOCK_MINERS = [
    {"uid": 0, "hotkey": "miner_a", "fixed_yield": 4.1},
    {"uid": 1, "hotkey": "miner_b", "fixed_yield": 4.3},
    {"uid": 2, "hotkey": "miner_c", "fixed_yield": 4.2},
]

# ── Simulate two challenge types ───────────────────────────────────────────────
CHALLENGES = [
    {"name": "rice / 30-day",    "weight": 0.6},
    {"name": "cassava / 60-day", "weight": 0.4},
]


def run_challenge(name: str) -> list[float]:
    actual_yield = round(random.uniform(3.5, 4.8), 2)
    print(f"\n{'-'*50}")
    print(f"Challenge : {name}")
    print(f"Actual yield : {actual_yield} t/ha")
    print()

    predictions = [m["fixed_yield"] for m in MOCK_MINERS]
    errors = [dual_metric_error(p, actual_yield) for p in predictions]
    ranks  = competition_rank(errors)
    weights = winner_take_most(ranks)

    for m, pred, err, rank, w in zip(MOCK_MINERS, predictions, errors, ranks, weights):
        print(
            f"  {m['hotkey']}  pred={pred}  "
            f"dual_err={err:.4f}  rank={rank}  weight={w:.4f}"
        )

    return weights


def main():
    print("=" * 50)
    print("RaiRai Validator - scoring demo (mock mode)")
    print("=" * 50)

    per_challenge_rewards = []
    challenge_weights = []

    for c in CHALLENGES:
        rewards = run_challenge(c["name"])
        per_challenge_rewards.append(rewards)
        challenge_weights.append(c["weight"])

    # Combine across challenges
    final = aggregate_challenge_weights(per_challenge_rewards, challenge_weights)

    print(f"\n{'-'*50}")
    print("Final aggregated weights (sent to Yuma Consensus):")
    for m, w in zip(MOCK_MINERS, final):
        print(f"  {m['hotkey']}  {w:.4f}")
    print(f"  total = {sum(final):.4f}")


if __name__ == "__main__":
    main()
