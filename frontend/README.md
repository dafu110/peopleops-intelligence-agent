# PeopleOps Intelligence Agent Frontend

This directory contains the professional web console for PeopleOps Intelligence Agent.

## Purpose

The frontend is the primary product UI:

- Left panel: candidate context, resume notes, and JD input.
- Center panel: single Agent conversation entry point.
- Right panel: readiness, evidence, approvals, actions, and audit trail.

The Streamlit app in `backend/` remains available as a local demo/debug surface.

## Local Development

Start the backend from the backend folder:

```powershell
cd backend
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open `http://127.0.0.1:3000`.

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` if the API does not run on `http://127.0.0.1:8000`.

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
pnpm dev
```

## Verification

```powershell
pnpm build
```

For production-readiness QA, also review:

```text
../docs/production-readiness.md
```

The Settings view in the console mirrors the same readiness matrix for database,
object storage, vector store, identity, observability, demo flow, eval gates, and
deployment materials.

## Repository Structure Note

The current project layout keeps the production console in `frontend/`, the API in
`backend/`, and deployment assets in `infra/`. If `git status` shows deleted
root-level backend files together with untracked `backend/`, `frontend/`, or
`infra/` folders, treat that as a pending repository migration review rather
than a frontend-only change.

Before publishing, review the migration intentionally:

```powershell
git status --short
git diff --stat
```

Stage the moved application structure only after confirming the deleted
root-level files are represented under the new folders.
