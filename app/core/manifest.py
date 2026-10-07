"""Canonical manifest + SHA-256 for Solana checkpoint (tamper-evident, not oracle of truth)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.core.models import ChronicleManifest, Event, ManifestEvent


def _canonical_dumps(obj: Any) -> bytes:
    """Stable JSON: sorted keys, no extra whitespace, UTF-8."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_event_manifest(event: Event, curator_id: str = "op_demo") -> ChronicleManifest:
    me = ManifestEvent(
        event_id=event.id,
        version=event.version,
        title=event.title,
        time_window=[t for t in [event.time_start, event.time_end] if t],
        places=list(event.places),
        claim_ids=list(event.claim_ids),
        status=event.status.value if hasattr(event.status, "value") else str(event.status),
    )
    return ChronicleManifest(
        schema="chronicle.manifest.v1",
        scope="event",
        day=event.time_start,
        city=event.city,
        events=[me],
        curator_id=curator_id,
        approved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def manifest_to_dict(manifest: ChronicleManifest) -> dict:
    return {
        "schema": manifest.schema_name,
        "scope": manifest.scope,
        "day": manifest.day,
        "city": manifest.city,
        "events": [
            {
                "event_id": e.event_id,
                "version": e.version,
                "title": e.title,
                "time_window": e.time_window,
                "places": e.places,
                "claim_ids": e.claim_ids,
                "status": e.status,
            }
            for e in manifest.events
        ],
        "curator_id": manifest.curator_id,
        "approved_at": manifest.approved_at,
    }


def hash_manifest(manifest: ChronicleManifest) -> str:
    """SHA-256 hex of canonical JSON. Same input always → same hash."""
    payload = manifest_to_dict(manifest)
    return hashlib.sha256(_canonical_dumps(payload)).hexdigest()


def memo_payload(city: str, scope_id: str, version: int, manifest_hash: str, curator_short: str) -> str:
    """Compact memo string for Solana Memo Program (max practical ~500 bytes)."""
    return f"CHRONICLE|{city}|{scope_id}|v{version}|{manifest_hash[:32]}|{curator_short[:12]}"
