"""Postgres persistence for the rolling rank history (Phase 3).

The neuron computes per-challenge ranks in memory each round
(`subnet.validator.rank_history.RankTracker`); this module persists the same
data so standings survive restarts and can be averaged over a rolling window:

- ``seed_challenges``       — upsert the taxonomy into ``challenges``.
- ``record_round_ranks``    — store one round's per-miner ranks for a challenge.
- ``rolling_ranks``         — average rank per miner over the last N rounds.
- ``update_best_miner``     — recompute + upsert the best miner for a challenge.

All functions operate on a caller-supplied ``AsyncSession`` (mirroring the
existing app/api pattern) and commit their own writes.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.challenge import BestMiner, Challenge, ChallengeRankHistory
from subnet.validator.challenge_spec import CHALLENGES


async def seed_challenges(db: AsyncSession) -> int:
    """Insert any taxonomy cells missing from the ``challenges`` table."""
    existing = set(
        (await db.scalars(select(Challenge.challenge_id))).all()
    )
    added = 0
    for spec in CHALLENGES:
        if spec.challenge_id in existing:
            continue
        db.add(
            Challenge(
                challenge_id=spec.challenge_id,
                crop=spec.crop,
                horizon_days=spec.horizon_days,
                weight=spec.weight,
            )
        )
        added += 1
    if added:
        await db.commit()
    return added


async def record_round_ranks(
    db: AsyncSession,
    challenge_id: str,
    round_no: int,
    ranks: dict[int, int],
    scores: Optional[dict[int, float]] = None,
    hotkeys: Optional[dict[int, str]] = None,
) -> None:
    """Persist one round's ranks for a challenge (idempotent per round)."""
    scores = scores or {}
    hotkeys = hotkeys or {}
    for uid, rank in ranks.items():
        db.add(
            ChallengeRankHistory(
                challenge_id=challenge_id,
                round=round_no,
                miner_uid=uid,
                miner_hotkey=hotkeys.get(uid),
                rank=rank,
                score=scores.get(uid),
            )
        )
    await db.commit()


async def rolling_ranks(
    db: AsyncSession, challenge_id: str, window: int = 10
) -> dict[int, float]:
    """Average rank per miner over the last ``window`` rounds of a challenge."""
    recent_rounds = (
        select(ChallengeRankHistory.round)
        .where(ChallengeRankHistory.challenge_id == challenge_id)
        .distinct()
        .order_by(ChallengeRankHistory.round.desc())
        .limit(window)
        .subquery()
    )
    rows = await db.execute(
        select(
            ChallengeRankHistory.miner_uid,
            func.avg(ChallengeRankHistory.rank),
        )
        .where(
            ChallengeRankHistory.challenge_id == challenge_id,
            ChallengeRankHistory.round.in_(select(recent_rounds.c.round)),
        )
        .group_by(ChallengeRankHistory.miner_uid)
    )
    return {uid: float(avg) for uid, avg in rows.all()}


async def update_best_miner(
    db: AsyncSession, challenge_id: str, window: int = 10
) -> Optional[int]:
    """Recompute the best miner for a challenge and upsert ``best_miners``.

    Best = lowest rolling-average rank. Ties are broken by the most recent
    round's rank (recency tie-break), matching the in-memory tracker.
    """
    rolling = await rolling_ranks(db, challenge_id, window)
    if not rolling:
        return None

    # Most recent (round, rank) per miner, for the recency tie-break.
    last_rows = await db.execute(
        select(
            ChallengeRankHistory.miner_uid,
            func.max(ChallengeRankHistory.round),
        )
        .where(ChallengeRankHistory.challenge_id == challenge_id)
        .group_by(ChallengeRankHistory.miner_uid)
    )
    last_round = {uid: rnd for uid, rnd in last_rows.all()}

    def sort_key(uid: int) -> tuple:
        return (rolling[uid], last_round.get(uid, 0) * -1)

    best_uid = min(rolling, key=sort_key)
    best_hotkey = await db.scalar(
        select(ChallengeRankHistory.miner_hotkey)
        .where(
            ChallengeRankHistory.challenge_id == challenge_id,
            ChallengeRankHistory.miner_uid == best_uid,
        )
        .order_by(ChallengeRankHistory.round.desc())
        .limit(1)
    )

    row = await db.scalar(
        select(BestMiner).where(BestMiner.challenge_id == challenge_id)
    )
    if row is None:
        row = BestMiner(challenge_id=challenge_id)
        db.add(row)
    row.miner_uid = best_uid
    row.miner_hotkey = best_hotkey
    row.avg_rank = rolling[best_uid]
    row.window = window

    await db.commit()
    return best_uid
