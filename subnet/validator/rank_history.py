"""Rolling per-challenge rank history (Phase 3).

Each round the validator ranks miners *within the challenge it posed*, then folds
that round's ranks into a rolling window of the last ``window`` rounds and
averages them. Averaging over a window means a single lucky (or unlucky) round
cannot spike a miner's standing — weights end up reflecting sustained skill.

Tie-break: when two miners share the same rolling-average rank, the one who
ranked better in the most recent round wins (recency tie-break).

This module is storage-agnostic and dependency-free — `RankTracker` keeps the
window in memory, so it runs in offline ``--mock`` mode with no database. The
matching Postgres persistence lives in ``app.core.rank_history``.
"""

from collections import defaultdict, deque
from typing import Optional


def competition_rank(scores: dict[int, float]) -> dict[int, int]:
    """Rank miner uids by score, highest score first → rank 1, 2, 3, ...

    This is a minimal *ordinal* ranking. Proper shared-rank tie handling (e.g.
    two miners tied for 1st both getting rank 1) is the separate "competition
    ranking with tie handling" upgrade; here ties fall back to uid order purely
    for determinism.
    """
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return {uid: position for position, (uid, _score) in enumerate(ordered, start=1)}


class RankTracker:
    """In-memory rolling rank history, keyed by challenge then miner uid."""

    def __init__(self, window: int = 10) -> None:
        self.window = window
        # challenge_id -> uid -> deque[(round, rank)] (most recent last)
        self._hist: dict[str, dict[int, deque]] = defaultdict(dict)

    def record(self, challenge_id: str, round_no: int, ranks: dict[int, int]) -> None:
        """Append this round's per-miner ranks for a challenge."""
        per_uid = self._hist[challenge_id]
        for uid, rank in ranks.items():
            if uid not in per_uid:
                per_uid[uid] = deque(maxlen=self.window)
            per_uid[uid].append((round_no, rank))

    def rolling_ranks(self, challenge_id: str) -> dict[int, float]:
        """Average rank per miner over the retained window for a challenge."""
        return {
            uid: sum(rank for _round, rank in dq) / len(dq)
            for uid, dq in self._hist[challenge_id].items()
            if dq
        }

    def best_miner(self, challenge_id: str) -> Optional[int]:
        """Uid with the lowest rolling-average rank (recency tie-break)."""
        rolling = self.rolling_ranks(challenge_id)
        if not rolling:
            return None

        def sort_key(uid: int) -> tuple:
            last_round, last_rank = self._hist[challenge_id][uid][-1]
            # lowest avg first; then best recent rank; then most recent round.
            return (rolling[uid], last_rank, -last_round)

        return min(rolling, key=sort_key)
