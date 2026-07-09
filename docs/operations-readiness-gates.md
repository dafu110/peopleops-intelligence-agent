# Operations Readiness Gates

Use this checklist when moving PeopleOps Intelligence Agent from a local demo to
a production-like environment. Each gate should have evidence attached to the
release notes before live tool execution is enabled.

## Gate 1: External Systems

Required evidence:

- `GET /production/checks?live=true` output for PostgreSQL, Qdrant, OIDC, and SMTP.
- Screenshot or log excerpt showing at least one configured ATS/calendar connector.
- Sandbox ATS stage change with matching `/tool-executions` and `/audit/events` records.
- Calendar invite sandbox execution with idempotency replay proof.
- Failed external action followed by compensation proof in `/tool-compensations`.

## Gate 2: Object Storage

Required evidence:

- `OBJECT_STORAGE_URI` points to S3, MinIO, OSS, or managed object storage.
- Upload, download, and delete a non-sensitive fixture file.
- Confirm tenant-prefixed object paths.
- Confirm lifecycle or retention policy.
- Confirm audit event includes only redacted metadata, not document content.

## Gate 3: Database Migrations

The current repository still uses application-managed schema initialization for
the reference SQLite/PostgreSQL adapters. Before production, add a formal
migration tool such as Alembic and require these checks:

- Migration scripts are ordered, reviewable, and reversible where practical.
- CI runs migrations against an empty PostgreSQL database.
- CI runs migrations against a previous release snapshot.
- Release notes include the current schema version.
- Rollback notes explain whether database rollback is automatic, manual, or
  forward-only.

## Gate 4: Monitoring And Alerts

Required metrics:

- Task success rate.
- Tool failure rate.
- Approval backlog size.
- RAG eval pass rate.
- Citation correctness.
- PII leakage count.
- Readiness warning count.
- API 4xx/5xx rate and latency.

Required alerts:

- Task success rate drops below release threshold.
- Tool failures exceed release threshold.
- Audit integrity check fails.
- RAG eval gate fails.
- Approval backlog exceeds operating threshold.
- External connector live probe fails.

## Gate 5: Release Drill

Run this before switching `TOOL_EXECUTION_MODE=live`:

```powershell
$env:PYTHONPATH = "$PWD\backend"
python -m unittest discover -s backend\tests
python backend/scripts/evaluate_rag.py --check-dataset
python backend/scripts/evaluate_rag.py --fixture-eval --report
cd frontend
pnpm typecheck
pnpm test:ui
pnpm build
```

Manual proof:

- Upload or paste candidate material.
- Paste a JD.
- Ask for resume/JD fit.
- Ask for a candidate follow-up action.
- Approve or reject the action.
- Confirm task replay, tool execution, compensation readiness, and audit-chain
  integrity.
