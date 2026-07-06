# Deployment

## Local Streamlit

```powershell
cd backend
python -m streamlit run app.py
```

## Local API

```powershell
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Useful endpoints:

- `GET /health`
- `GET /readiness`
- `GET /me`
- `POST /chat`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/events`
- `GET /tools`
- `GET /tool-executions`
- `GET /tool-compensations`
- `POST /tool-executions/{idempotency_key}/compensate`
- `GET /interviews`
- `GET /approvals`
- `GET /connectors`

If `ACCESS_PASSWORD` is configured, pass it as the `X-Access-Password` header.
Pass `X-Tenant-ID`, `X-Org-ID`, and `X-Department-ID` from your API gateway or identity layer so every ATS action, approval, and audit event carries a tenant boundary.
For enterprise identity, either place the API behind a trusted SSO gateway and set `TRUSTED_SSO_ENABLED=true`, or set `OIDC_ENABLED=true` with `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL` for bearer-token validation.

`POST /chat` returns a `task_id`. Use `GET /tasks` for the recent task index, `GET /tasks/{task_id}` for the persisted task snapshot plus ordered events, and `GET /tasks/{task_id}/events` to replay the event timeline.
Use `GET /tools` and `GET /tool-executions` to inspect the registered tool contract, idempotency keys, attempts, and structured tool failure payloads.
Use `POST /tool-executions/{idempotency_key}/compensate` for auditable compensation of a successful mutating tool execution. Compensation preserves generated artifacts for review and writes a `tool_compensations` record.

## Docker

Docker is optional for local development, but useful for repeatable deployment validation. Reference deployment:

```powershell
docker compose -f infra/docker-compose.yml up --build
```

Open the web console at `http://127.0.0.1:3000`.
The FastAPI control plane is exposed at `http://127.0.0.1:8000`.

Runtime state is mounted into:

- `var/runtime/peopleops.sqlite3`
- `var/runtime/audit/events.jsonl`
- `var/runtime/email_drafts/`
- `var/runtime/calendar/`
- `var/runtime/ats_exports/`
- `var/chroma/policy/`

Production dependency stack:

```powershell
$env:POSTGRES_PASSWORD="replace-me"
$env:MINIO_ROOT_USER="peopleops"
$env:MINIO_ROOT_PASSWORD="replace-me"
$env:DEFAULT_TENANT_ID="acme"
docker compose -f infra/docker-compose.production.yml up --build
```

The production compose file starts PostgreSQL, Qdrant, and MinIO alongside the API and web console, and sets:

- `DATABASE_BACKEND=postgresql`
- `DATABASE_URL=postgresql://...`
- `VECTOR_BACKEND=qdrant`
- `VECTOR_STORE_URL=http://qdrant:6333`
- `OBJECT_STORAGE_URI=s3://peopleops-artifacts`
- `TRUSTED_SSO_ENABLED=true`

`GET /readiness` reports whether the production URLs are configured and whether enterprise warnings remain.
The runtime uses `DATABASE_BACKEND` to choose SQLite vs PostgreSQL persistence, and `VECTOR_BACKEND` to choose Chroma vs Qdrant retrieval. `GET /readiness` reports whether the required production URLs are configured.

The Streamlit workbench remains available as a local debug surface:

```powershell
cd backend
python -m streamlit run app.py
```

## Production Checklist

- Review the production readiness checklist in `docs/production-readiness.md`.
- Configure `ACCESS_PASSWORD` for demos, or use trusted SSO headers behind an enterprise identity gateway.
- Prefer `pbkdf2_sha256$...` access passwords for shared demos; plain text remains supported for local convenience and is reported as a readiness warning.
- Keep `.env` outside source control.
- Set `DATABASE_BACKEND=postgresql` and `DATABASE_URL` for production database deployments.
- Set `VECTOR_BACKEND=qdrant` and configure `VECTOR_STORE_URL` for production retrieval deployments.
- Replay task/tool/audit flows against PostgreSQL and rerun `python backend/scripts/evaluate_rag.py` against Qdrant before promotion.
- Move resumes, JD files, generated artifacts, and audit exports to S3, MinIO, OSS, or managed object storage via `OBJECT_STORAGE_URI`.
- Set real `DEFAULT_TENANT_ID`, `DEFAULT_ORG_ID`, and `DEFAULT_DEPARTMENT_ID`; do not use `default` in enterprise mode.
- Keep `TOOL_EXECUTION_MODE=approval` for candidate follow-up messages, rejection drafts, offer drafts, calendar invites, and ATS stage changes until an HR reviewer approves `/approvals` entries.
- Configure `TOOL_DEFAULT_TIMEOUT_SECONDS` and `TOOL_DEFAULT_RETRIES`; mutating tools do not auto-retry after timeout and rely on idempotency keys plus manual replay to avoid duplicate side effects.
- Keep both RAG gates enabled: the main CI job runs the lightweight fixture gate, and the `rag-real-eval` CI job installs full backend dependencies and runs `python backend/scripts/evaluate_rag.py` against the real retriever. Tune `RAG_MIN_PASS_RATE`, `RAG_MIN_KEYWORD_COVERAGE`, and `RAG_MIN_CITATION_CORRECTNESS` before promotion.
- Generate a release eval artifact with `python backend/scripts/evaluate_rag.py --fixture-eval --report`; attach `output/rag-eval-report.json` to release evidence.
- Use `/connectors` to track Workday, BambooHR, Greenhouse, Lever, Feishu, DingTalk, Enterprise WeChat, Outlook, and Google Calendar readiness.
- Persist `var/runtime` and `var/chroma` only for local reference deployments.
- Rotate audit logs.
- Use `TOOL_EXECUTION_MODE=live` with SMTP settings only in controlled environments.
- Replace local calendar artifacts and the file-based ATS adapter with enterprise calendar and ATS APIs when credentials are available.
- After installing Docker Desktop on Windows, reboot once before first validation if WSL or Virtual Machine Platform was newly enabled. Then run `docker info` and `docker compose version`.
