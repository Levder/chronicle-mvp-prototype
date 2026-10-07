import asyncio
import json as jsonlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.api import routes
from app.core.models import ArticleIn, ClaimType
from app.services import extract


API_KEY = "local-test-key-never-return"


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("API error", request=request, response=response)

    def json(self):
        return self.body


def configure_openai(monkeypatch, post, api_mode="chat_completions"):
    monkeypatch.setattr(
        extract,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=API_KEY,
            openai_model="test-model",
            openai_api_mode=api_mode,
            openai_agent_session_id="agent_session_test",
        ),
    )
    monkeypatch.setattr(extract.httpx, "post", post)


def test_extract_claims_uses_bearer_key_and_parses_structured_response(monkeypatch):
    response_claim = {
        "text": "Russian forces entered Irpin on 2022-03-05.",
        "type": "event_time_location",
        "event_date": "2022-03-05",
        "locations": ["Irpin"],
        "entities": ["Russian forces"],
        "importance": 3,
    }
    request_details = {}

    def fake_post(url, *, headers, json, timeout):
        request_details.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            200,
            {
                "choices": [
                    {"message": {"content": jsonlib.dumps({"claims": [response_claim]})}}
                ]
            },
        )

    configure_openai(monkeypatch, fake_post)
    claims = extract.extract_claims("art_1", "Article text")

    assert request_details["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert request_details["json"]["response_format"] == {"type": "json_object"}
    assert len(claims) == 1
    assert claims[0].article_id == "art_1"
    assert claims[0].type == ClaimType.EVENT_TIME_LOCATION
    assert claims[0].event_date == "2022-03-05"
    assert claims[0].importance == 3


def test_agents_mode_sends_message_to_session_and_parses_completed_turn(monkeypatch):
    response_claim = {
        "text": "Russian forces entered Irpin on 2022-03-05.",
        "type": "event_time_location",
        "event_date": "2022-03-05",
        "locations": ["Irpin"],
        "entities": ["Russian forces"],
        "importance": 3,
    }
    events = [
        {
            "type": "agent.session.turn.output_text.done",
            "text": jsonlib.dumps({"claims": [response_claim]}),
        },
        {
            "type": "agent.session.turn.completed",
            "turn": {"subagent_id": None},
        },
    ]

    class FakeStream(FakeResponse):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_lines(self):
            return [f"data: {jsonlib.dumps(event)}" for event in events]

    calls = {}

    class FakeClient:
        def __init__(self, *, timeout):
            calls["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, *, params, headers):
            calls["stream"] = (method, url, params, headers)
            return FakeStream(200, {})

        def post(self, url, *, headers, json):
            calls["post"] = (url, headers, json)
            return FakeResponse(200, {})

    configure_openai(monkeypatch, lambda *args, **kwargs: None, api_mode="agents")
    monkeypatch.setattr(extract.httpx, "Client", FakeClient)

    claims = extract.extract_claims("art_1", "Article text")

    assert calls["stream"][0] == "GET"
    assert calls["stream"][1].endswith("/agent_session_test/events")
    assert calls["stream"][2] == {"stream": "true"}
    assert calls["stream"][3]["Authorization"] == f"Bearer {API_KEY}"
    assert calls["post"][0] == calls["stream"][1]
    assert calls["post"][1]["Authorization"] == f"Bearer {API_KEY}"
    assert calls["post"][1]["Idempotency-Key"]
    assert calls["post"][2]["events"][0]["type"] == "agent.session.input.message"
    assert len(claims) == 1
    assert claims[0].type == ClaimType.EVENT_TIME_LOCATION
    assert claims[0].importance == 3


@pytest.mark.parametrize(
    ("status_code", "expected_message"),
    [
        (401, "OpenAI authorization failed. Check OPENAI_API_KEY."),
        (500, "OpenAI API request failed (HTTP 500)."),
    ],
)
def test_openai_errors_are_clear_and_do_not_expose_key_or_fallback(
    monkeypatch, status_code, expected_message
):
    configure_openai(monkeypatch, lambda *args, **kwargs: FakeResponse(status_code, {}))
    monkeypatch.setattr(
        extract,
        "_heuristic_claims",
        lambda *args: pytest.fail("heuristic fallback must not run"),
    )

    with pytest.raises(extract.ClaimExtractionError) as error:
        extract.extract_claims("art_1", "Article text")

    assert str(error.value) == expected_message
    assert API_KEY not in str(error.value)


def test_invalid_structured_claims_raise_clear_error_without_fallback(monkeypatch):
    body = {"claims": [{"text": "A claim", "importance": 9}]}
    configure_openai(
        monkeypatch,
        lambda *args, **kwargs: FakeResponse(
            200, {"choices": [{"message": {"content": jsonlib.dumps(body)}}]}
        ),
    )
    monkeypatch.setattr(
        extract,
        "_heuristic_claims",
        lambda *args: pytest.fail("heuristic fallback must not run"),
    )

    with pytest.raises(
        extract.ClaimExtractionError, match="OpenAI returned an invalid claims response."
    ):
        extract.extract_claims("art_1", "Article text")


def test_missing_key_keeps_heuristic_fallback(monkeypatch):
    monkeypatch.setattr(
        extract,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="", openai_model="test-model"),
    )

    claims = extract.extract_claims(
        "art_1",
        "Russian forces entered Irpin after clashes in the city during the morning.",
    )

    assert claims
    assert claims[0].article_id == "art_1"


def test_ingest_returns_safe_gateway_error_for_extraction_failure(monkeypatch):
    async def fail_extraction(*args, **kwargs):
        raise extract.ClaimExtractionError(
            "OpenAI authorization failed. Check OPENAI_API_KEY."
        )

    monkeypatch.setattr(routes, "process_article", fail_extraction)

    with pytest.raises(HTTPException) as error:
        asyncio.run(routes.ingest(ArticleIn(raw_text="Article text"), session=None))

    assert error.value.status_code == 502
    assert API_KEY not in error.value.detail
