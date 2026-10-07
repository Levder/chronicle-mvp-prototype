"""End-to-end: ingest → claims → score → route → optional event. No auto-publish."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    Article,
    ArticleIn,
    Claim,
    Event,
    EventStatus,
    QueueName,
    ReviewDecision,
    ReviewIn,
)
from app.core.scoring import aggregate_article_scores, route, score_claim
from app.db.tables import (
    ArticleRow,
    AuditLogRow,
    CheckpointRow,
    ClaimRow,
    EventRow,
    ReviewRow,
    SourceRow,
)
from app.services.extract import extract_claims
from app.services.ingest import ingest_article


async def _ensure_source(session: AsyncSession, domain: str | None) -> SourceRow | None:
    if not domain:
        return None
    q = await session.execute(select(SourceRow).where(SourceRow.domain == domain))
    row = q.scalar_one_or_none()
    if row:
        return row
    row = SourceRow(id="src_" + uuid.uuid4().hex[:8], domain=domain, accepted_count=0, reviewed_count=0)
    session.add(row)
    await session.flush()
    return row


async def process_article(session: AsyncSession, payload: ArticleIn) -> dict:
    article = ingest_article(payload)

    # Exact dedup
    if article.sha256:
        existing = await session.execute(
            select(ArticleRow).where(ArticleRow.sha256 == article.sha256)
        )
        if existing.scalar_one_or_none():
            return {"status": "duplicate", "sha256": article.sha256, "article_id": None}

    source = await _ensure_source(session, article.source_domain)
    accepted = source.accepted_count if source else 0
    reviewed = source.reviewed_count if source else 0

    session.add(
        ArticleRow(
            id=article.id,
            url=article.url,
            title=article.title,
            raw_text=article.raw_text,
            normalized_text=article.normalized_text,
            source_domain=article.source_domain,
            published_at=article.published_at,
            sha256=article.sha256,
            simhash=article.simhash,
            status=article.status,
        )
    )

    claims = extract_claims(article.id, article.normalized_text)
    scored_claims: list[Claim] = []
    for c in claims:
        if c.features is None:
            continue
        # inject source prior into features
        c.features.source_accepted = accepted
        c.features.source_reviewed = reviewed
        c.score = score_claim(c.features)
        scored_claims.append(c)
        session.add(
            ClaimRow(
                id=c.claim_id,
                article_id=article.id,
                text=c.text,
                type=c.type.value,
                event_date=c.event_date,
                locations=c.locations,
                entities=c.entities,
                importance=c.importance,
                features_json=c.features.model_dump(),
                score_json=c.score.model_dump(),
            )
        )

    if scored_claims:
        e_art, m_art = aggregate_article_scores(
            [c.score for c in scored_claims if c.score],
            [c.importance for c in scored_claims],
        )
        r_art = sum(c.score.R for c in scored_claims if c.score) / len(scored_claims)
        critical_e = min(
            (c.score.E for c in scored_claims if c.score and c.importance >= 3),
            default=None,
        )
        critical_c = max(
            (c.features.contradiction for c in scored_claims if c.features),
            default=0.0,
        )
        route_result = route(
            round(r_art, 1),
            e_art,
            m_art,
            critical_contradiction=critical_c,
            critical_claim_E=critical_e,
        )
    else:
        r_art, e_art, m_art = 0.0, 0.0, 50.0
        route_result = route(0.0, 0.0, 50.0)

    # Create draft event from first locations / title
    places: list[str] = []
    for c in scored_claims:
        places.extend(c.locations)
    places = list(dict.fromkeys(places))
    event_id = "evt_" + uuid.uuid4().hex[:10]
    event = Event(
        id=event_id,
        title=article.title or "Untitled event",
        time_start=next((c.event_date for c in scored_claims if c.event_date), None),
        places=places,
        status=EventStatus.DRAFT,
        city="irpin",
        article_ids=[article.id],
        claim_ids=[c.claim_id for c in scored_claims],
        queue=route_result.queue,
        R_article=round(r_art, 1),
        E_article=e_art,
        M_article=m_art,
    )
    session.add(
        EventRow(
            id=event.id,
            title=event.title,
            time_start=event.time_start,
            places=event.places,
            status=event.status.value,
            version=1,
            city=event.city,
            article_ids=event.article_ids,
            claim_ids=event.claim_ids,
            queue=event.queue.value if event.queue else None,
            R_article=event.R_article,
            E_article=event.E_article,
            M_article=event.M_article,
        )
    )
    for c in scored_claims:
        row = await session.get(ClaimRow, c.claim_id)
        if row:
            row.event_id = event_id

    art_row = await session.get(ArticleRow, article.id)
    if art_row:
        art_row.queue = route_result.queue.value
        art_row.status = "scored"

    session.add(
        AuditLogRow(
            event_type="article_processed",
            object_id=article.id,
            version="mvp3.0",
            payload={
                "event_id": event_id,
                "queue": route_result.queue.value,
                "R": route_result.R,
                "E": route_result.E,
                "M": route_result.M,
                "reasons": route_result.reasons,
            },
        )
    )
    await session.commit()

    return {
        "status": "ok",
        "article_id": article.id,
        "event_id": event_id,
        "queue": route_result.queue.value,
        "R": route_result.R,
        "E": route_result.E,
        "M": route_result.M,
        "reasons": route_result.reasons,
        "claims": [
            {
                "claim_id": c.claim_id,
                "text": c.text,
                "R": c.score.R if c.score else None,
                "E": c.score.E if c.score else None,
                "M": c.score.M if c.score else None,
                "importance": c.importance,
            }
            for c in scored_claims
        ],
    }


async def review_event(session: AsyncSession, event_id: str, review: ReviewIn) -> dict:
    from app.services.checkpoint import enqueue_checkpoint

    ev = await session.get(EventRow, event_id)
    if not ev:
        return {"status": "error", "detail": "event not found"}

    review_id = "rev_" + uuid.uuid4().hex[:10]
    session.add(
        ReviewRow(
            id=review_id,
            event_id=event_id,
            operator_id=review.operator_id,
            decision=review.decision.value,
            reason=review.reason,
        )
    )

    if review.decision == ReviewDecision.APPROVE:
        ev.status = EventStatus.PUBLISHED.value
        ev.version = (ev.version or 1) + (0 if ev.status == EventStatus.DRAFT.value else 1)
        # Update source stats for all article domains
        for aid in ev.article_ids or []:
            art = await session.get(ArticleRow, aid)
            if art and art.source_domain:
                src_q = await session.execute(
                    select(SourceRow).where(SourceRow.domain == art.source_domain)
                )
                src = src_q.scalar_one_or_none()
                if src:
                    src.reviewed_count += 1
                    src.accepted_count += 1
        checkpoint = await enqueue_checkpoint(session, ev, review.operator_id)
        await session.commit()
        return {
            "status": "approved",
            "event_id": event_id,
            "event_status": ev.status,
            "checkpoint": checkpoint,
        }

    if review.decision == ReviewDecision.REJECT:
        ev.status = EventStatus.REJECTED.value
        for aid in ev.article_ids or []:
            art = await session.get(ArticleRow, aid)
            if art and art.source_domain:
                src_q = await session.execute(
                    select(SourceRow).where(SourceRow.domain == art.source_domain)
                )
                src = src_q.scalar_one_or_none()
                if src:
                    src.reviewed_count += 1
        await session.commit()
        return {"status": "rejected", "event_id": event_id}

    if review.decision == ReviewDecision.OVERRIDE_QUEUE and review.override_queue:
        ev.queue = review.override_queue.value
        await session.commit()
        return {"status": "queue_overridden", "queue": ev.queue}

    await session.commit()
    return {"status": "ok", "event_id": event_id}
