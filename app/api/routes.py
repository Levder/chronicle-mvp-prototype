from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ArticleIn, ReviewIn
from app.db.database import get_session
from app.db.tables import ArticleRow, CheckpointRow, ClaimRow, EventRow
from app.services.extract import ClaimExtractionError
from app.services.pipeline import process_article, review_event

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}


@router.post("/ingest")
async def ingest(payload: ArticleIn, session: AsyncSession = Depends(get_session)):
    if not payload.url and not payload.raw_text:
        raise HTTPException(400, "Provide url or raw_text")
    try:
        result = await process_article(session, payload)
    except ClaimExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return result


@router.get("/articles/{article_id}")
async def get_article(article_id: str, session: AsyncSession = Depends(get_session)):
    row = await session.get(ArticleRow, article_id)
    if not row:
        raise HTTPException(404, "article not found")
    claims = (
        await session.execute(select(ClaimRow).where(ClaimRow.article_id == article_id))
    ).scalars().all()
    return {
        "id": row.id,
        "title": row.title,
        "url": row.url,
        "queue": row.queue,
        "status": row.status,
        "sha256": row.sha256,
        "source_domain": row.source_domain,
        "claims": [
            {
                "id": c.id,
                "text": c.text,
                "score": c.score_json,
                "importance": c.importance,
                "locations": c.locations,
            }
            for c in claims
        ],
    }


@router.get("/events")
async def list_events(
    status: str | None = None,
    queue: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    q = select(EventRow)
    if status:
        q = q.where(EventRow.status == status)
    if queue:
        q = q.where(EventRow.queue == queue)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "status": r.status,
            "queue": r.queue,
            "places": r.places,
            "R": r.R_article,
            "E": r.E_article,
            "M": r.M_article,
            "version": r.version,
            "manifest_hash": r.published_manifest_hash,
            "checkpoint_id": r.last_checkpoint_id,
        }
        for r in rows
    ]


@router.get("/events/{event_id}")
async def get_event(event_id: str, session: AsyncSession = Depends(get_session)):
    r = await session.get(EventRow, event_id)
    if not r:
        raise HTTPException(404, "event not found")
    claims = (
        await session.execute(select(ClaimRow).where(ClaimRow.event_id == event_id))
    ).scalars().all()
    cp = None
    if r.last_checkpoint_id:
        cp_row = await session.get(CheckpointRow, r.last_checkpoint_id)
        if cp_row:
            explorer = None
            if cp_row.tx_signature:
                q = f"?cluster={cp_row.network}" if cp_row.network != "mainnet-beta" else ""
                explorer = f"https://solscan.io/tx/{cp_row.tx_signature}{q}"
            cp = {
                "id": cp_row.id,
                "status": cp_row.status,
                "manifest_hash": cp_row.manifest_hash,
                "tx_signature": cp_row.tx_signature,
                "network": cp_row.network,
                "explorer_url": explorer,
                "error": cp_row.error,
            }
    return {
        "id": r.id,
        "title": r.title,
        "status": r.status,
        "queue": r.queue,
        "places": r.places,
        "R": r.R_article,
        "E": r.E_article,
        "M": r.M_article,
        "version": r.version,
        "claims": [
            {"id": c.id, "text": c.text, "score": c.score_json, "importance": c.importance}
            for c in claims
        ],
        "checkpoint": cp,
    }


@router.get("/queue/{name}")
async def queue_events(name: str, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(EventRow).where(
                EventRow.queue == name.upper(),
                EventRow.status == "draft",
            )
        )
    ).scalars().all()
    return [{"id": r.id, "title": r.title, "R": r.R_article, "E": r.E_article, "M": r.M_article} for r in rows]


@router.post("/events/{event_id}/review")
async def review(event_id: str, body: ReviewIn, session: AsyncSession = Depends(get_session)):
    result = await review_event(session, event_id, body)
    if result.get("status") == "error":
        raise HTTPException(404, result.get("detail"))
    return result


@router.get("/timeline")
async def public_timeline(session: AsyncSession = Depends(get_session)):
    """Published events only — public chronicle."""
    rows = (
        await session.execute(select(EventRow).where(EventRow.status == "published"))
    ).scalars().all()
    out = []
    for r in rows:
        explorer = None
        if r.last_checkpoint_id:
            cp = await session.get(CheckpointRow, r.last_checkpoint_id)
            if cp and cp.tx_signature:
                q = f"?cluster={cp.network}" if cp.network != "mainnet-beta" else ""
                explorer = f"https://solscan.io/tx/{cp.tx_signature}{q}"
        out.append(
            {
                "id": r.id,
                "title": r.title,
                "places": r.places,
                "time_start": r.time_start,
                "version": r.version,
                "manifest_hash": r.published_manifest_hash,
                "solana_explorer": explorer,
            }
        )
    return out
