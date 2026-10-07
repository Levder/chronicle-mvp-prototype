"""
Deterministic scoring engine — R / E / M.
LLM never sets final score. Same features always produce same scores.
Formulas from MVP technical model (Bucha/Irpin Verification + Chronicle).
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.models import (
    ClaimFeatures,
    QueueName,
    RouteResult,
    ScoreResult,
)


MODEL_VERSION = "mvp3.0"


def source_prior(accepted: int, reviewed: int) -> float:
    """Beta-smoothed source reliability: S = (A+2)/(N+4). New source → 0.5."""
    return (accepted + 2) / (reviewed + 4)


def independent_evidence_score(root_count: int) -> float:
    """I = min(1, k/4) — count provenance roots, not URLs."""
    return min(1.0, root_count / 4.0)


def score_claim(features: ClaimFeatures) -> ScoreResult:
    """
    R = 100 * (0.45*G + 0.35*T + 0.20*K)
    E = 100 * (0.35*P + 0.30*I + 0.15*G + 0.15*T + 0.05*S)
    M = 100 * (0.35*C + 0.25*A + 0.20*D + 0.10*L + 0.10*U)
    """
    S = source_prior(features.source_accepted, features.source_reviewed)
    I = independent_evidence_score(features.independent_root_count)

    R = 100.0 * (
        0.45 * features.geo_relevance
        + 0.35 * features.time_relevance
        + 0.20 * features.entity_relevance
    )
    E = 100.0 * (
        0.35 * features.primary_evidence
        + 0.30 * I
        + 0.15 * features.geo_consistency
        + 0.15 * features.time_consistency
        + 0.05 * S
    )
    M = 100.0 * (
        0.35 * features.contradiction
        + 0.25 * features.anonymous_dependency
        + 0.20 * features.source_dependency
        + 0.10 * features.loaded_language
        + 0.10 * features.uncertainty
    )

    return ScoreResult(
        R=round(R, 1),
        E=round(E, 1),
        M=round(M, 1),
        S=round(S, 4),
        I=round(I, 4),
        features=features,
        model_version=MODEL_VERSION,
    )


def aggregate_article_scores(
    scores: list[ScoreResult],
    importances: list[int],
) -> tuple[float, float]:
    """
    E_article = Σ(w_i * E_i) / Σw_i
    M_article = max( weighted_avg(M), max(M for critical claims) )
    """
    if not scores:
        return 0.0, 0.0
    weights = [max(1, w) for w in importances]
    total_w = sum(weights)
    e_art = sum(w * s.E for w, s in zip(weights, scores)) / total_w
    m_avg = sum(w * s.M for w, s in zip(weights, scores)) / total_w
    critical_ms = [s.M for s, w in zip(scores, weights) if w >= 3]
    m_art = max(m_avg, max(critical_ms) if critical_ms else m_avg)
    return round(e_art, 1), round(m_art, 1)


def route(
    R: float,
    E: float,
    M: float,
    *,
    critical_contradiction: float = 0.0,
    critical_claim_E: float | None = None,
) -> RouteResult:
    """
    if R < 40 → OUT_OF_SCOPE
    elif critical_C >= 0.8 or critical_claim_E < 35 → DEEP_REVIEW
    elif E >= 75 and M <= 25 → QUICK_REVIEW
    elif E < 45 or M >= 60 → DEEP_REVIEW
    else → FULL_REVIEW
    NEVER auto_publish / auto_delete.
    """
    cfg = get_settings()
    reasons: list[str] = []

    if R < cfg.r_out_of_scope:
        reasons.append(f"R={R} < {cfg.r_out_of_scope} (out of geographic/time scope)")
        return RouteResult(queue=QueueName.OUT_OF_SCOPE, R=R, E=E, M=M, reasons=reasons)

    if critical_contradiction >= cfg.critical_c:
        reasons.append(f"critical contradiction C={critical_contradiction} >= {cfg.critical_c}")
        return RouteResult(queue=QueueName.DEEP_REVIEW, R=R, E=E, M=M, reasons=reasons)

    if critical_claim_E is not None and critical_claim_E < cfg.critical_e:
        reasons.append(f"critical claim E={critical_claim_E} < {cfg.critical_e}")
        return RouteResult(queue=QueueName.DEEP_REVIEW, R=R, E=E, M=M, reasons=reasons)

    if E >= cfg.e_quick and M <= cfg.m_quick:
        reasons.append(f"E={E}>={cfg.e_quick} and M={M}<={cfg.m_quick}")
        return RouteResult(queue=QueueName.QUICK_REVIEW, R=R, E=E, M=M, reasons=reasons)

    if E < cfg.e_deep or M >= cfg.m_deep:
        reasons.append(f"E={E}<{cfg.e_deep} or M={M}>={cfg.m_deep}")
        return RouteResult(queue=QueueName.DEEP_REVIEW, R=R, E=E, M=M, reasons=reasons)

    reasons.append("default full review band")
    return RouteResult(queue=QueueName.FULL_REVIEW, R=R, E=E, M=M, reasons=reasons)
