# Production Readiness

This checklist turns PeopleOps Intelligence Agent from a local demo into a
production SaaS deployment candidate.

For release evidence requirements, also use
[`operations-readiness-gates.md`](operations-readiness-gates.md). It defines the
external connector, object storage, migration, monitoring, and release-drill
proof expected before live tool execution.

## 1. Production Dependencies

Production must run on managed services instead of local reference stores.

Required configuration:

```text
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql://...
VECTOR_BACKEND=qdrant
VECTOR_STORE_URL=http://qdrant:6333
OBJECT_STORAGE_URI=s3://peopleops-artifacts
SMTP_HOST=...
CONFIGURED_CONNECTOR_ENV=ATS,CALENDAR,EMAIL
```

Validation:

```powershell
python -m uvicorn api:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/readiness
```

Run the production integration gate in configuration mode:

```powershell
curl -H "X-Access-Password: <password>" http://127.0.0.1:8000/production/checks
```

Run read-only live probes where supported:

```powershell
curl -H "X-Access-Password: <password>" "http://127.0.0.1:8000/production/checks?live=true"
```

Statuses mean:

- `not_configured`: required production endpoint or identity mode is missing.
- `configured`: configuration exists, but no real live proof has been collected.
- `verified`: a safe live probe passed, such as PostgreSQL `SELECT 1`.
- `failed`: a live probe or required configuration check failed.

Current live probes are intentionally read-only:

- PostgreSQL: `SELECT 1`.
- Qdrant: `GET /collections`.
- OIDC: JWKS endpoint fetch when `OIDC_JWKS_URL` is configured.
- SMTP: host/port socket reachability.

Object storage, ATS, calendar, and mail-send validation still require deployment
environment credentials and sandbox-side-effect tests. Do not mark them verified
until put/get/delete, sandbox ATS stage change, calendar invite, mail send,
retry, idempotency, and compensation flows have actual evidence.

## 2. Enterprise Authentication

Use one production identity mode:

- Trusted SSO headers behind an enterprise gateway.
- OIDC bearer tokens with issuer, audience, and JWKS validation.

Required tenant headers:

```text
X-Tenant-ID
X-Org-ID
X-Department-ID
```

Roles are mapped to `admin`, `hrbp`, and `viewer`. Every task, approval, tool
execution, and audit event should carry the tenant scope.

## 3. Observability

The API already emits request IDs and persisted task events. Production review
should include:

- `GET /tasks` and `GET /tasks/{task_id}` for task replay.
- `GET /tool-executions` for tool status, retries, idempotency keys, and errors.
- `GET /operations/summary` for task success rate and recent failures.
- `GET /audit/events` and `GET /audit/integrity` for audit-chain review.

Release metrics:

- Task success rate.
- Tool failure rate.
- Approval backlog.
- RAG eval pass rate.
- Citation correctness.
- PII leakage cases.
- Readiness warning count.

## 4. End-To-End Demo Gate

A release candidate should complete this flow in one session:

1. Start backend and frontend.
2. Upload a resume or paste candidate material.
3. Paste JD context.
4. Ask for resume/JD fit.
5. Ask for a candidate follow-up action.
6. Approve or reject the generated action.
7. Confirm task replay, tool execution, and audit event visibility.

Frontend:

```powershell
cd frontend
pnpm install
pnpm dev
```

Backend:

```powershell
cd backend
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

## 5. Quality Gates

Before release:

```powershell
cd frontend
pnpm build
```

```powershell
$env:PYTHONPATH = "$PWD\backend"
python -m unittest discover -s backend/tests
python backend/scripts/evaluate_rag.py --check-dataset
python backend/scripts/evaluate_rag.py --fixture-eval --report
```

Manual visual QA should cover at least:

- Desktop: 1440px wide.
- Tablet: 1024px wide.
- Mobile: 390px wide.

Check for overlapping text, horizontal overflow, broken empty states, disabled
buttons, and inaccessible focus states.

## 6. RAG And Agent Eval Report

The eval report is written to:

```text
output/rag-eval-report.json
```

It contains:

- Pass rate and required pass rate.
- Average keyword coverage.
- Average citation correctness.
- PII leakage cases.
- Forbidden-term hits.
- Per-case retrieval sources and metrics.
- Final gate result.

Use this report as a release artifact and attach it to PR or deployment notes.

## 7. Deployment And Rollback Materials

Keep these artifacts ready for each release:

- `.env.production` template without secrets.
- Database migration notes.
- Object storage bucket and retention policy.
- Backup and restore procedure for PostgreSQL and object storage.
- RAG index rebuild procedure.
- Docker image tags for backend and frontend.
- Previous known-good prompt/model configuration.
- Rollback command or deployment platform rollback steps.

Rollback rule:

If task failure rate, tool failure rate, or RAG eval gate regresses after release,
disable live tool execution first, then roll back model/prompt/config, then roll
back the application image if needed.
