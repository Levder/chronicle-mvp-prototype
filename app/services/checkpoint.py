"""
Solana checkpoint layer.
After human Approve → build manifest → hash → enqueue.
Worker sends memo tx (or skips if SOLANA_ENABLED=false).
NEVER un-publishes on Solana failure.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.manifest import build_event_manifest, hash_manifest, memo_payload
from app.core.models import CheckpointStatus, Event, EventStatus
from app.db.tables import AuditLogRow, CheckpointRow, EventRow

logger = logging.getLogger(__name__)


def _event_from_row(row: EventRow) -> Event:
    return Event(
        id=row.id,
        title=row.title,
        time_start=row.time_start,
        time_end=row.time_end,
        places=list(row.places or []),
        actors=list(row.actors or []),
        status=EventStatus(row.status) if row.status in EventStatus._value2member_map_ else EventStatus.DRAFT,
        version=row.version or 1,
        city=row.city or "irpin",
        article_ids=list(row.article_ids or []),
        claim_ids=list(row.claim_ids or []),
        last_checkpoint_id=row.last_checkpoint_id,
        published_manifest_hash=row.published_manifest_hash,
    )


async def enqueue_checkpoint(session: AsyncSession, ev_row: EventRow, curator_id: str) -> dict:
    settings = get_settings()
    event = _event_from_row(ev_row)
    manifest = build_event_manifest(event, curator_id=curator_id)
    mhash = hash_manifest(manifest)
    cp_id = "cp_" + uuid.uuid4().hex[:10]

    status = CheckpointStatus.PENDING
    tx_signature = None
    slot = None
    error = None
    network = settings.solana_network

    if not settings.solana_enabled:
        status = CheckpointStatus.SKIPPED
        error = "SOLANA_ENABLED=false — checkpoint recorded off-chain only"
    else:
        try:
            from app.solana.client import send_checkpoint_memo

            memo = memo_payload(
                event.city,
                event.id,
                event.version,
                mhash,
                curator_id,
            )
            result = send_checkpoint_memo(memo)
            tx_signature = result.get("signature")
            slot = result.get("slot")
            status = CheckpointStatus.CONFIRMED if tx_signature else CheckpointStatus.FAILED
            if not tx_signature:
                error = result.get("error", "unknown send error")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Solana checkpoint failed")
            status = CheckpointStatus.FAILED
            error = str(exc)

    cp = CheckpointRow(
        id=cp_id,
        scope="event",
        scope_id=event.id,
        version=event.version,
        manifest_hash=mhash,
        curator_id=curator_id,
        tx_signature=tx_signature,
        slot=slot,
        status=status.value,
        network=network,
        error=error,
        confirmed_at=datetime.utcnow() if status == CheckpointStatus.CONFIRMED else None,
    )
    session.add(cp)
    ev_row.last_checkpoint_id = cp_id
    ev_row.published_manifest_hash = mhash

    session.add(
        AuditLogRow(
            event_type="solana_checkpoint",
            object_id=event.id,
            version=str(event.version),
            payload={
                "checkpoint_id": cp_id,
                "manifest_hash": mhash,
                "status": status.value,
                "tx_signature": tx_signature,
                "network": network,
                "error": error,
            },
        )
    )

    explorer = None
    if tx_signature:
        cluster_q = f"?cluster={network}" if network != "mainnet-beta" else ""
        explorer = f"https://solscan.io/tx/{tx_signature}{cluster_q}"

    return {
        "checkpoint_id": cp_id,
        "manifest_hash": mhash,
        "status": status.value,
        "tx_signature": tx_signature,
        "slot": slot,
        "network": network,
        "explorer_url": explorer,
        "error": error,
    }
