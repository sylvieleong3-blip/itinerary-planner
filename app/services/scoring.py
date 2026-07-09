from dataclasses import dataclass
from typing import Literal

ActivityStatus = Literal["likely", "maybe", "vetoed", "unlikely", "unrated"]

RATING_LABELS = {
    1: "No way (veto)",
    2: "Probably not",
    3: "Maybe / flexible",
    4: "Probably yes",
    5: "Definitely yes",
}

STATUS_CONFIG = {
    "likely": {"label": "Likely in", "class": "status-likely"},
    "maybe": {"label": "Maybe", "class": "status-maybe"},
    "vetoed": {"label": "Vetoed", "class": "status-vetoed"},
    "unlikely": {"label": "Unlikely", "class": "status-unlikely"},
    "unrated": {"label": "No votes yet", "class": "status-unrated"},
}


@dataclass
class VoteSummary:
    avg_score: float | None
    vote_count: int
    total_members: int
    has_veto: bool
    vetoed_by: str | None
    veto_reason: str | None
    status: ActivityStatus
    distribution: dict[int, int]


def compute_vote_summary(
    ratings: list[tuple[int, str, str | None]],
    total_members: int,
) -> VoteSummary:
    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for rating, _, _ in ratings:
        distribution[rating] = distribution.get(rating, 0) + 1

    vote_count = len(ratings)
    has_veto = any(r == 1 for r, _, _ in ratings)
    veto_vote = next(((n, reason) for r, n, reason in ratings if r == 1), None)

    avg_score = None
    if vote_count > 0:
        avg_score = sum(r for r, _, _ in ratings) / vote_count

    if vote_count == 0:
        status: ActivityStatus = "unrated"
    elif has_veto:
        status = "vetoed"
    elif avg_score is not None and avg_score >= 4.0 and vote_count / total_members >= 0.5:
        status = "likely"
    elif avg_score is not None and avg_score >= 3.0:
        status = "maybe"
    else:
        status = "unlikely"

    return VoteSummary(
        avg_score=avg_score,
        vote_count=vote_count,
        total_members=total_members,
        has_veto=has_veto,
        vetoed_by=veto_vote[0] if veto_vote else None,
        veto_reason=veto_vote[1] if veto_vote else None,
        status=status,
        distribution=distribution,
    )
