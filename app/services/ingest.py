"""Ingest URL or raw text → normalized article + hashes. Exact dedup via SHA-256."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

from app.core.models import Article, ArticleIn

# Optional heavy deps — degrade gracefully
try:
    import trafilatura
except ImportError:
    trafilatura = None  # type: ignore


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _simple_simhash(text: str) -> str:
    """Lightweight fingerprint (not cryptographic). Good enough for MVP demo."""
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return "0" * 16
    h = 0
    for t in tokens[:500]:
        h ^= int(hashlib.md5(t.encode()).hexdigest()[:8], 16)
    return f"{h:016x}"


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return None


def fetch_url_text(url: str) -> tuple[str, str | None]:
    """Returns (text, title). Falls back to empty if trafilatura missing / fail."""
    if trafilatura is None:
        return "", None
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "", None
    text = trafilatura.extract(downloaded, include_comments=False) or ""
    meta = trafilatura.extract_metadata(downloaded)
    title = meta.title if meta else None
    return text, title


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ingest_article(payload: ArticleIn) -> Article:
    raw = payload.raw_text or ""
    title = payload.title
    url = payload.url

    if url and not raw:
        fetched, fetched_title = fetch_url_text(url)
        raw = fetched
        title = title or fetched_title

    normalized = normalize_text(raw)
    article_id = "art_" + uuid.uuid4().hex[:10]

    return Article(
        id=article_id,
        url=url,
        title=title or (normalized[:80] + "…" if len(normalized) > 80 else normalized) or "Untitled",
        raw_text=raw,
        normalized_text=normalized,
        source_domain=payload.source_domain or _domain(url),
        published_at=payload.published_at,
        sha256=_sha256(normalized) if normalized else None,
        simhash=_simple_simhash(normalized) if normalized else None,
        status="ingested",
        created_at=datetime.utcnow(),
    )
