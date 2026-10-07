from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ArticleRow(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    source_domain: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    simhash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ingested")
    queue: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceRow(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0)


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    article_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(64), default="other")
    event_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locations: Mapped[dict | list] = mapped_column(JSON, default=list)
    entities: Mapped[dict | list] = mapped_column(JSON, default=list)
    importance: Mapped[int] = mapped_column(Integer, default=1)
    features_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(1024))
    time_start: Mapped[str | None] = mapped_column(String(32), nullable=True)
    time_end: Mapped[str | None] = mapped_column(String(32), nullable=True)
    places: Mapped[dict | list] = mapped_column(JSON, default=list)
    actors: Mapped[dict | list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    city: Mapped[str] = mapped_column(String(64), default="irpin")
    article_ids: Mapped[dict | list] = mapped_column(JSON, default=list)
    claim_ids: Mapped[dict | list] = mapped_column(JSON, default=list)
    queue: Mapped[str | None] = mapped_column(String(32), nullable=True)
    R_article: Mapped[float | None] = mapped_column(Float, nullable=True)
    E_article: Mapped[float | None] = mapped_column(Float, nullable=True)
    M_article: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checkpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ReviewRow(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    article_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    operator_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckpointRow(Base):
    __tablename__ = "solana_checkpoints"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32))
    scope_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    merkle_root: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ipfs_cid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    curator_id: Mapped[str] = mapped_column(String(64))
    curator_pubkey: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tx_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    network: Mapped[str] = mapped_column(String(32), default="devnet")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
