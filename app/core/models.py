"""Pydantic domain models — Claim is the unit of evidence; Event is the unit of chronicle."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class QueueName(str, Enum):
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    QUICK_REVIEW = "QUICK_REVIEW"
    FULL_REVIEW = "FULL_REVIEW"
    DEEP_REVIEW = "DEEP_REVIEW"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE_QUEUE = "override_queue"


class EventStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UPDATED = "updated"
    REJECTED = "rejected"


class CheckpointStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ClaimType(str, Enum):
    EVENT_TIME_LOCATION = "event_time_location"
    ACTOR_ACTION = "actor_action"
    CASUALTY = "casualty"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"


# --- Feature vectors for scoring (all 0..1) ---

class ClaimFeatures(BaseModel):
    geo_relevance: float = Field(ge=0, le=1, default=0.0)
    time_relevance: float = Field(ge=0, le=1, default=0.0)
    entity_relevance: float = Field(ge=0, le=1, default=0.0)
    primary_evidence: float = Field(ge=0, le=1, default=0.0)
    independent_root_count: int = Field(ge=0, default=0)
    geo_consistency: float = Field(ge=0, le=1, default=0.5)
    time_consistency: float = Field(ge=0, le=1, default=0.5)
    source_accepted: int = Field(ge=0, default=0)
    source_reviewed: int = Field(ge=0, default=0)
    contradiction: float = Field(ge=0, le=1, default=0.0)
    anonymous_dependency: float = Field(ge=0, le=1, default=0.0)
    source_dependency: float = Field(ge=0, le=1, default=0.0)
    loaded_language: float = Field(ge=0, le=1, default=0.0)
    uncertainty: float = Field(ge=0, le=1, default=0.0)
    importance: int = Field(ge=1, le=3, default=1)


class ScoreResult(BaseModel):
    R: float
    E: float
    M: float
    S: float
    I: float
    features: ClaimFeatures
    model_version: str = "mvp3.0"


class Claim(BaseModel):
    claim_id: str
    article_id: str
    event_id: Optional[str] = None
    text: str
    type: ClaimType = ClaimType.OTHER
    event_date: Optional[str] = None
    locations: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    importance: int = Field(ge=1, le=3, default=1)
    explicit_or_inferred: str = "explicit"
    features: Optional[ClaimFeatures] = None
    score: Optional[ScoreResult] = None


class Evidence(BaseModel):
    evidence_id: str
    claim_id: str
    url: Optional[str] = None
    evidence_type: str = "link"  # link | photo | video | document | primary
    root_group: Optional[str] = None
    geo_match: float = 0.5
    time_match: float = 0.5
    is_primary: bool = False


class ArticleIn(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    raw_text: Optional[str] = None
    source_domain: Optional[str] = None
    published_at: Optional[datetime] = None


class Article(BaseModel):
    id: str
    url: Optional[str] = None
    title: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    source_id: Optional[str] = None
    source_domain: Optional[str] = None
    published_at: Optional[datetime] = None
    sha256: Optional[str] = None
    simhash: Optional[str] = None
    status: str = "ingested"
    queue: Optional[QueueName] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Event(BaseModel):
    id: str
    title: str
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    places: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    status: EventStatus = EventStatus.DRAFT
    version: int = 1
    city: str = "irpin"
    article_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    last_checkpoint_id: Optional[str] = None
    published_manifest_hash: Optional[str] = None
    R_article: Optional[float] = None
    E_article: Optional[float] = None
    M_article: Optional[float] = None
    queue: Optional[QueueName] = None


class ReviewIn(BaseModel):
    decision: ReviewDecision
    reason: str = Field(min_length=3)
    operator_id: str = "op_demo"
    override_queue: Optional[QueueName] = None


class Review(BaseModel):
    id: str
    article_id: Optional[str] = None
    event_id: Optional[str] = None
    operator_id: str
    decision: ReviewDecision
    reason: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SolanaCheckpoint(BaseModel):
    id: str
    scope: str  # event | daily
    scope_id: str
    version: int = 1
    manifest_hash: str
    merkle_root: Optional[str] = None
    ipfs_cid: Optional[str] = None
    curator_id: str
    curator_pubkey: Optional[str] = None
    tx_signature: Optional[str] = None
    slot: Optional[int] = None
    status: CheckpointStatus = CheckpointStatus.PENDING
    network: str = "devnet"
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None


class ManifestEvent(BaseModel):
    event_id: str
    version: int
    title: str
    time_window: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    status: str = "published"


class ChronicleManifest(BaseModel):
    schema_name: str = Field(default="chronicle.manifest.v1", alias="schema")
    scope: str = "event"
    day: Optional[str] = None
    city: str = "irpin"
    events: list[ManifestEvent] = Field(default_factory=list)
    curator_id: str = "op_demo"
    approved_at: str = ""

    model_config = {"populate_by_name": True}


class RouteResult(BaseModel):
    queue: QueueName
    R: float
    E: float
    M: float
    reasons: list[str] = Field(default_factory=list)
