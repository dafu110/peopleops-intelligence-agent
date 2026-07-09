# Agent Operating Guide

This repository follows a lightweight agent-skills workflow: define the change, plan the narrowest path, build in small patches, verify with executable gates, review public-facing artifacts, then ship.

## Project Boundaries

- Backend entry points: `backend/api.py` for FastAPI and `backend/app.py` for the optional Streamlit workbench.
- Frontend entry point: `frontend/app/page.tsx`, with reusable UI helpers in `frontend/lib/` and components in `frontend/components/`.
- Agent logic and governance live under `backend/core/`.
- Public launch assets live in `README.md`, `docs/`, `docs/screenshots/`, `.github/workflows/ci.yml`, and `infra/`.

## Required Checks

Run the smallest relevant checks first, then expand before shipping:

```powershell
python -m compileall -q backend
$env:PYTHONPATH='backend'; python -m unittest discover -s backend/tests
$env:PYTHONPATH='backend'; python backend/scripts/evaluate_agent_traces.py
$env:PYTHONPATH='backend'; python backend/scripts/evaluate_rag.py --fixture-eval
python backend/scripts/check_public_hygiene.py
```

Frontend changes require:

```powershell
cd frontend
pnpm typecheck
pnpm test:ui
pnpm build
```

## Public Repo Rules

- Keep exactly one README hero screenshot at `docs/screenshots/peopleops-intelligence-console.png`.
- Do not commit local runtime state, generated indexes, `.env`, `.next`, `node_modules`, `output`, or `var/runtime`.
- Never paste `docker compose config` output publicly when local `.env` contains real credentials.
- Treat mojibake or broken Chinese UI text as a release blocker.
- Keep demo-mode wording distinct from production claims unless production connectors have evidence.

## Review Lens

Prioritize findings in this order:

1. Security, tenant isolation, PII handling, approval gates, and secret leakage.
2. Agent correctness, RAG grounding, citations, tool idempotency, and audit integrity.
3. CI reliability, deterministic tests, and release reproducibility.
4. Frontend clarity, accessibility, responsive layout, and screenshot freshness.
5. README polish and portfolio first impression.
