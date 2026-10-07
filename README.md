# Verified Local Chronicle MVP

A human-reviewed prototype for turning articles or raw text about the Bucha–Irpin region into structured claims, deterministic evidence scores, review queues, and a draft local chronicle.

> **Important:** This is a research/demo prototype, not an automated fact-checker. Scores are triage signals, not proof of truth. A person must review and approve every event before it is published.

## What it does

1. Accepts a URL or pasted article text.
2. Removes exact duplicate submissions using SHA-256.
3. Extracts up to eight claims using local heuristics or an optional OpenAI integration.
4. Computes deterministic relevance (`R`), evidence (`E`), and risk (`M`) scores in Python, then routes the article to a review queue.
5. Lets a curator inspect the material and approve or reject it.
6. Shows published events in a public timeline. Optionally, after approval, it stores a manifest hash on Solana as a tamper-evident checkpoint.

The LLM only structures claims; it does not assign final scores. Solana stores a hash, not the underlying evidence or a claim that an event is true. Nothing is auto-published or auto-deleted.

## Quick start on Windows

Requirements: Python 3.12 or newer, PowerShell, and an internet connection for installing packages. Open two PowerShell windows from the project folder.

### 1. Create the environment and install dependencies

In the first window:

```powershell
Set-Location "$HOME\Downloads\chronicle_mvp_prototype"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks virtual-environment activation, allow it for this window only and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Configure the app

Open `.env`:

```powershell
notepad .env
```

For the simplest setup, run without an LLM:

```dotenv
OPENAI_API_KEY=
OPENAI_API_MODE=chat_completions
OPENAI_AGENT_SESSION_ID=
```

With an empty key, claim extraction uses built-in heuristics. This keeps the app usable without OpenAI credentials, but the extracted claims are less capable than LLM-generated claims.

To use Chat Completions instead, put a valid OpenAI API key in `OPENAI_API_KEY` and keep `OPENAI_API_MODE=chat_completions`. If a configured API request fails or returns invalid structured data, ingestion reports an error; it does not silently switch to heuristics.

Keep `.env` on the machine running the API. Do not commit it, paste secrets into the UI, or put them in URLs or ngrok settings. If a key has been exposed, revoke it and create a new one.

### 3. Start the API

In the first PowerShell window, from the project folder with `.venv` activated:

```powershell
uvicorn app.main:app --reload --port 8000
```

Leave this window running. Check that the API is up:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

The response should include `"status": "ok"`.

### 4. Start the curator UI

In the second PowerShell window:

```powershell
Set-Location "$HOME\Downloads\chronicle_mvp_prototype"
.\.venv\Scripts\Activate.ps1
streamlit run .\ui\curator.py
```

Open:

- Curator UI: http://127.0.0.1:8501
- Interactive API docs: http://127.0.0.1:8000/docs

When both are running on the same PC, the Streamlit server calls the API at `http://127.0.0.1:8000/api`.

## Try the demo

Use the **Ingest** tab to submit a URL or paste text, then select **Process**. The response includes the event ID, queue, scores, and extracted claims. Open **Review queues**, refresh a queue, inspect an event, and choose **Approve** or **Reject** with a reason of at least three characters. Approved events appear in **Public timeline**.

To load the three built-in demo scenarios (verified-style report, copied rumor, and date conflict), stop the API first or use another database, then run this in an activated project environment:

```powershell
python .\scripts\seed_demo.py
```

The demo data is illustrative test material, not a real verification result.

## Optional OpenAI Agents API mode

`OPENAI_API_MODE=agents` uses an **already-created Agents API session**. The app does not create the session or start the executor. Before enabling this mode, you need:

- `OPENAI_API_KEY`: the application API key with the Agents session and Responses permissions required by the OpenAI API.
- `OPENAI_AGENT_SESSION_ID`: the session ID (not the session's remote URL or environment ID).
- A connected self-hosted executor for that session, running with its separate restricted environment key as `CODEX_API_KEY`.

Set the mode and session in `.env`:

```dotenv
OPENAI_API_MODE=agents
OPENAI_AGENT_SESSION_ID=<session-id>
```

Provision and run the session/executor separately according to the [OpenAI self-hosted environments guide](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted). Keep the executor key separate from `OPENAI_API_KEY` and out of the app's `.env`. Use a dedicated, isolated environment: an Agents executor can run commands and access files in its environment, and submitted article text is untrusted input. The local API waits for the Agents turn to finish, so allow longer request timeouts than in the no-LLM mode.

## Optional ngrok access

ngrok is not needed for local use or for OpenAI API calls. The local API connects to OpenAI directly.

To let someone access the UI remotely, run `ngrok http 8501` and share the UI tunnel URL. Streamlit makes its API requests from the Streamlit server process, so when the UI and API are on the same PC it should continue to use `http://127.0.0.1:8000/api`; do not change `CHRONICLE_API` to the API tunnel URL for this setup. An API tunnel on port `8000` is only needed for a separate external client that calls the API directly.

**Security warning:** this prototype has no user authentication or authorization. Do not expose it to the public internet or share an ngrok URL with untrusted users. A tunnel does not add application-level access control. Never expose `.env`.

## Optional Solana checkpoint

Solana is disabled by default. To enable the devnet integration, configure `SOLANA_PRIVATE_KEY`, set `SOLANA_ENABLED=true`, and keep `SOLANA_NETWORK=devnet` in `.env`. On human approval, the app builds a canonical event manifest, hashes it, and sends a memo transaction. The UI can show a Solscan link when the checkpoint is confirmed.

The event remains published if the checkpoint is skipped or fails; the checkpoint status is recorded as `skipped` or `failed`. Solana is an optional integrity checkpoint, not a verification oracle.

## API overview

All routes are under `/api`.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/ingest` | Submit a URL and/or raw text |
| `GET` | `/articles/{article_id}` | Get an article and its claims |
| `GET` | `/events?status=draft&queue=DEEP_REVIEW` | List events, optionally filtered |
| `GET` | `/events/{event_id}` | Get an event, claims, and checkpoint |
| `GET` | `/queue/{name}` | List draft events in a review queue |
| `POST` | `/events/{event_id}/review` | Approve, reject, or override a queue |
| `GET` | `/timeline` | List published events only |

Example ingestion body:

```json
{
  "raw_text": "Paste article text here"
}
```

Or submit a URL:

```json
{
  "url": "https://example.com/article"
}
```

The API accepts either field; at least one must be provided. Review decisions use `approve` or `reject` and require a reason.

## Scoring and review queues

Scores are calculated by the Python scoring module, not by the LLM:

- `R` — relevance to the geographic and temporal scope.
- `E` — evidence strength, including primary evidence, independent roots, consistency, and the source prior.
- `M` — risk signals such as contradiction, dependencies, loaded language, and uncertainty.

The routing thresholds are initial prototype settings in `app/core/config.py`; they have not been calibrated as production thresholds. The queues are `OUT_OF_SCOPE`, `QUICK_REVIEW`, `FULL_REVIEW`, and `DEEP_REVIEW`. A queue is a prioritization aid, not an approval decision.

## Run tests

With the project virtual environment activated:

```powershell
python -m pytest tests\ -q
```

## Docker

With Docker Desktop installed and running, create `.env` as described above. From the project folder:

```powershell
docker compose up --build
```

The API is exposed on port `8000`, and the UI on port `8501`. The Compose configuration connects the UI container to the API container using Docker's internal service name.

## Project layout

```text
app/
  api/       FastAPI routes
  core/      settings, domain models, scoring, manifests
  db/        SQLAlchemy tables and database setup
  services/  ingestion, claim extraction, pipeline, checkpoints
  solana/    optional Solana memo client
ui/
  curator.py Streamlit curator interface
tests/       extraction and scoring tests
scripts/
  seed_demo.py
docs/        Ukrainian technical reference document
```

## Current limitations

- This is an MVP for a Bucha–Irpin verification archive and local chronicle, not a general-purpose fact-checking service.
- Heuristic extraction is intentionally basic. LLM output is also not evidence of truth.
- Provenance-root counting and several feature values are prototype-level; validate and calibrate them before relying on scores.
- The app has no authentication, multi-user permissions, or production deployment hardening.
- Solana records a manifest hash only; it does not store the article or establish the truth of an event.

## Principles

1. The LLM structures information; deterministic application code calculates scores.
2. Count independent provenance roots, not raw URL totals.
3. Only a human curator publishes an event.
4. Solana is an optional tamper-evident checkpoint, not an oracle.
5. The system does not automatically delete material.
