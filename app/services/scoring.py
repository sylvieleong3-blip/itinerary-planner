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
    "likely": {
        "label": "Likely in",
        "class": "bg-emerald-50 text-emerald-700 border-emerald-200",
    },
    "maybe": {
        "label": "Maybe",
        "class": "bg-amber-50 text-amber-700 border-amber-200",
    },
    "vetoed": {
        "label": "Vetoed",
        "class": "bg-red-50 text-red-700 border-red-200",
    },
    "unlikely": {
        "label": "Unlikely",
        "class": "bg-gray-50 text-gray-600 border-gray-200",
    },
    "unrated": {
        "label": "No votes yet",
        "class": "bg-white text-gray-500 border-gray-200",
    },
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
