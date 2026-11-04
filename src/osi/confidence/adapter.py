"""Map OSI graph edges onto the Estorides confidence model.

The vendored ``reliability_scoring`` module (see ``vendor/NOTICE``) is the
source of truth for how a single observation scores. This adapter does three
things on top of it:

1. Translate an OSI edge relation (``owns``, ``co_owner``, ``same_mail``, ...)
   into the Estorides enums ``(SourceReliability, Credibility, SourceType)``.
2. Count how many independent sources corroborate the edge, since that term
   dominates the score.
3. Apply negative evidence (``namesake``) as a multiplicative penalty, because
   ``merge_confidence``'s ``max()`` semantics cannot express a contradiction.
"""
from __future__ import annotations

from .vendor.reliability_scoring import (
    ConfidenceInput,
    Credibility,
    SourceReliability,
    SourceType,
    compute_confidence,
    merge_confidence,
)

CONTRADICTION_PENALTY = 0.3

OSI_EDGE_TAXONOMY: dict[str, tuple[SourceReliability, Credibility, SourceType]] = {
    "owns":                   (SourceReliability.A, Credibility.CONFIRMED,     SourceType.PRIMARY),
    "sold_to":                (SourceReliability.A, Credibility.CONFIRMED,     SourceType.PRIMARY),
    "statutory_agent_of":     (SourceReliability.A, Credibility.CONFIRMED,     SourceType.PRIMARY),
    "officer_of":             (SourceReliability.A, Credibility.CONFIRMED,     SourceType.PRIMARY),
    "registered_as":          (SourceReliability.A, Credibility.PROBABLY_TRUE, SourceType.PRIMARY),
    "signed_for":             (SourceReliability.A, Credibility.CONFIRMED,     SourceType.PRIMARY),
    "co_owner":               (SourceReliability.B, Credibility.PROBABLY_TRUE, SourceType.SECONDARY),
    "same_mail":              (SourceReliability.C, Credibility.POSSIBLY_TRUE, SourceType.SECONDARY),
    "wikipedia_corroborated": (SourceReliability.B, Credibility.CONFIRMED,     SourceType.PRIMARY),
    "has_alias":              (SourceReliability.E, Credibility.DOUBTFUL,      SourceType.TERTIARY),
    "probable_identity":      (SourceReliability.E, Credibility.DOUBTFUL,      SourceType.TERTIARY),
    "namesake":               (SourceReliability.F, Credibility.IMPROBABLE,    SourceType.TERTIARY),
}

CONTRADICTION_RELATIONS = {"namesake"}


def _default_tier() -> tuple[SourceReliability, Credibility, SourceType]:
    return (SourceReliability.C, Credibility.CANNOT_BE_JUDGED, SourceType.TERTIARY)


def edge_confidence(
    relation: str,
    *,
    corroboration_count: int = 1,
    observation_age_seconds: float = 0.0,
    base_confidence: float = 1.0,
) -> float:
    """Score one edge observation. Returns a float in [0, 1]."""
    rel, cred, st = OSI_EDGE_TAXONOMY.get(relation, _default_tier())
    result = compute_confidence(
        ConfidenceInput(
            source_reliability=rel,
            credibility=cred,
            source_type=st,
            corroboration_count=max(0, corroboration_count),
            observation_age_seconds=max(0.0, observation_age_seconds),
            base_confidence=max(0.0, min(1.0, base_confidence)),
        )
    )
    return result.score


def merge_positive(observations: list[dict]) -> float:
    """Combine several positive observations of the same underlying claim.

    Each observation is a dict with at least ``relation``. Optional keys:
    ``corroboration_count``, ``observation_age_seconds``, ``base_confidence``.

    Returns the merged confidence in [0, 1]. Empty list returns 0.0.
    """
    if not observations:
        return 0.0
    score = 0.0
    for obs in observations:
        rel, cred, st = OSI_EDGE_TAXONOMY.get(obs.get("relation"), _default_tier())
        merged = merge_confidence(
            existing=score,
            new_observation=max(0.0, min(1.0, obs.get("base_confidence", 1.0))),
            new_reliability=rel,
            new_credibility=cred,
            new_source_type=st,
            corroboration_count=max(1, obs.get("corroboration_count", 1)),
            observation_age_seconds=max(0.0, obs.get("observation_age_seconds", 0.0)),
        )
        score = merged.score
    return score


def resolve_with_contradictions(
    positive_edges: list[dict],
    contradicting_edges: list[dict],
    *,
    penalty: float = CONTRADICTION_PENALTY,
) -> dict:
    """Merged confidence for a claim, reduced by each explicit contradiction.

    ``positive_edges`` and ``contradicting_edges`` are lists of edge dicts with
    a ``relation`` key. Contradictions multiply the merged positive score by
    ``penalty`` once per contradiction, clamped to [0, 1].
    """
    base = merge_positive(positive_edges)
    n_contradictions = sum(
        1 for e in contradicting_edges if e.get("relation") in CONTRADICTION_RELATIONS
    )
    final = base * (penalty ** n_contradictions)
    return {
        "score": max(0.0, min(1.0, final)),
        "base_score": base,
        "contradictions": n_contradictions,
        "penalty": penalty,
    }


if __name__ == "__main__":
    print("=== single-source scores by relation ===")
    for rel in sorted(OSI_EDGE_TAXONOMY):
        score = edge_confidence(rel, corroboration_count=1)
        print(f"  {rel:24s} {score:.4f}")

    print()
    print("=== corroboration sweep on 'owns' ===")
    for n in (1, 2, 3, 5, 9, 20):
        print(f"  n={n:2d}  {edge_confidence('owns', corroboration_count=n):.4f}")

    print()
    print("=== contradiction penalty on a merged claim ===")
    positive = [{"relation": "co_owner", "corroboration_count": 1}]
    for k in (0, 1, 2):
        contra = [{"relation": "namesake"}] * k
        r = resolve_with_contradictions(positive, contra)
        print(f"  {k} contradiction(s): score={r['score']:.4f}  base={r['base_score']:.4f}")
