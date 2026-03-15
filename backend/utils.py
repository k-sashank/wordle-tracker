from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Dict, List

from pydantic_models import WordleResult, LeaderboardEntry, LeaderboardResponse


NEGATIVE_MISS_SCORE = -3


def compute_score(attempts: int, completed: bool) -> int:
    """
    Score rule:
    - If completed: 7 - attempts (so 6 for 1 attempt, down to 1 for 6 attempts).
    - If not completed: NEGATIVE_MISS_SCORE.
    """
    if not completed:
        return NEGATIVE_MISS_SCORE
    return 7 - attempts


def get_period_bounds(reference: date, period: str) -> (date, date):
    """
    Compute [start, end] inclusive bounds for a given period type.
    period: "day" | "week" | "month" | "year"
    """
    if period == "day":
        return reference, reference

    if period == "week":
        # ISO week: Monday is 0
        start = reference - timedelta(days=reference.weekday())
        end = start + timedelta(days=6)
        return start, end

    if period == "month":
        start = reference.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1, day=1)
        else:
            next_month = start.replace(month=start.month + 1, day=1)
        end = next_month - timedelta(days=1)
        return start, end

    if period == "year":
        start = reference.replace(month=1, day=1)
        end = reference.replace(month=12, day=31)
        return start, end

    raise ValueError(f"Unsupported period: {period}")


def build_leaderboard(
    results: Iterable[WordleResult],
    period: str,
    reference: date | None = None,
) -> LeaderboardResponse:
    if reference is None:
        reference = date.today()

    start, end = get_period_bounds(reference, period)

    # Aggregate scores per user within the period
    scores_by_user: Dict[str, int] = {}
    for r in results:
        if start <= r.date <= end:
            scores_by_user.setdefault(r.username, 0)
            scores_by_user[r.username] += r.score

    entries: List[LeaderboardEntry] = [
        LeaderboardEntry(username=username, total_score=total_score)
        for username, total_score in scores_by_user.items()
    ]
    # Sort descending by score, then by username to keep it stable
    entries.sort(key=lambda e: (-e.total_score, e.username.lower()))

    return LeaderboardResponse(
        period=period,
        period_start=start,
        period_end=end,
        entries=entries,
    )

