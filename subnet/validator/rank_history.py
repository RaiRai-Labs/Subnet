"""Rolling per-challenge rank history (Phase 3).

Each round the validator ranks miners *within the challenge it posed*, then folds
that round's ranks into a rolling window of the last ``window`` rounds and
averages them. Averaging over a window means a single lucky (or unlucky) round
cannot spike a miner's standing — weights end up reflecting sustained skill.

Tie-break: when two miners share the same rolling-average rank, the one who
ranked better in the most recent round wins (recency tie-break).

This module is storage-agnostic and dependency-free — `RankTracker` keeps the
window in memory, so it runs in offline ``--mock`` mode with no database. The
matching Postgres persistence lives in ``app.core.rank_history``. Per-round
ranks are produced by ``app.core.scoring.competition_rank`` (with tie handling);
this module only accumulates them over the rolling window.
"""

from collections import defaultdict, deque
from typing import Optional


class RankTracker:
    """In-memory rolling rank history, keyed by challenge then miner uid.

    Liveness (Phase 4): a miner that is queried but does not respond accrues an
    absence strike for that challenge; after ``allowed_absence`` consecutive
    no-shows its rank history is dropped, so stale standings don't linger and a
    returning miner starts fresh. Responding resets the strike count.
    """

    def __init__(self, window: int = 10, allowed_absence: int = 3) -> None:
        self.window = window
        self.allowed_absence = allowed_absence
        # challenge_id -> uid -> deque[(round, rank)] (most recent last)
        self._hist: dict[str, dict[int, deque]] = defaultdict(dict)
        # challenge_id -> uid -> consecutive no-show count
        self._absence: dict[str, dict[int, int]] = defaultdict(dict)

    def record(self, challenge_id: str, round_no: int, ranks: dict[int, int]) -> None:
        """Append this round's per-miner ranks; responding resets absence."""
        per_uid = self._hist[challenge_id]
        for uid, rank in ranks.items():
            if uid not in per_uid:
                per_uid[uid] = deque(maxlen=self.window)
            per_uid[uid].append((round_no, rank))
            self._absence[challenge_id][uid] = 0

    def mark_absent(self, challenge_id: str, uids) -> set[int]:
        """Count no-shows; drop a miner's history after ``allowed_absence`` misses.

        Returns the set of uids whose history was dropped this call.
        """
        strikes = self._absence[challenge_id]
        dropped: set[int] = set()
        for uid in uids:
            strikes[uid] = strikes.get(uid, 0) + 1
            if strikes[uid] >= self.allowed_absence:
                self._hist[challenge_id].pop(uid, None)
                strikes[uid] = 0
                dropped.add(uid)
        return dropped

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
