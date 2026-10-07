"""Unit tests: scoring must be deterministic; routing rules from MVP model."""
from app.core.models import ClaimFeatures
from app.core.scoring import route, score_claim, source_prior, independent_evidence_score
from app.core.models import QueueName
from app.core.manifest import ChronicleManifest, ManifestEvent, hash_manifest


def test_source_prior_new():
    assert source_prior(0, 0) == 0.5


def test_source_prior_positive():
    assert abs(source_prior(10, 10) - 12 / 14) < 1e-9


def test_independent_caps_at_1():
    assert independent_evidence_score(0) == 0.0
    assert independent_evidence_score(2) == 0.5
    assert independent_evidence_score(4) == 1.0
    assert independent_evidence_score(10) == 1.0


def test_score_deterministic():
    f = ClaimFeatures(
        geo_relevance=1.0,
        time_relevance=1.0,
        entity_relevance=1.0,
        primary_evidence=1.0,
        independent_root_count=4,
        geo_consistency=1.0,
        time_consistency=1.0,
        source_accepted=10,
        source_reviewed=10,
        contradiction=0.0,
        anonymous_dependency=0.0,
        source_dependency=0.0,
        loaded_language=0.0,
        uncertainty=0.0,
    )
    a = score_claim(f)
    b = score_claim(f)
    assert a.R == b.R == 100.0
    assert a.E == b.E
    assert a.M == b.M == 0.0
    assert a.E > 90  # strong evidence


def test_route_out_of_scope():
    r = route(30, 80, 10)
    assert r.queue == QueueName.OUT_OF_SCOPE


def test_route_quick():
    r = route(80, 80, 10)
    assert r.queue == QueueName.QUICK_REVIEW


def test_route_deep_low_e():
    r = route(80, 40, 30)
    assert r.queue == QueueName.DEEP_REVIEW


def test_route_deep_critical_c():
    r = route(90, 90, 10, critical_contradiction=0.9)
    assert r.queue == QueueName.DEEP_REVIEW


def test_route_full():
    r = route(60, 60, 40)
    assert r.queue == QueueName.FULL_REVIEW


def test_manifest_hash_stable():
    m = ChronicleManifest(
        schema="chronicle.manifest.v1",
        scope="event",
        day="2022-03-05",
        city="irpin",
        events=[
            ManifestEvent(
                event_id="evt_1",
                version=1,
                title="Test",
                time_window=["2022-03-05"],
                places=["Ірпінь"],
                claim_ids=["clm_1"],
                status="published",
            )
        ],
        curator_id="op_demo",
        approved_at="2026-01-01T00:00:00Z",
    )
    h1 = hash_manifest(m)
    h2 = hash_manifest(m)
    assert h1 == h2
    assert len(h1) == 64
