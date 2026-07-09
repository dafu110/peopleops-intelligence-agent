# Launch Hardening Checklist

This checklist follows the agent-skills loop: define the release surface, plan the narrowest change, build with small patches, verify with executable gates, review public artifacts, then ship.

## Blocking Gates

- Do not publish local virtual environments, generated Chroma indexes, runtime databases, email drafts, calendar artifacts, or ATS exports.
- Set `REQUIRE_ACCESS_PASSWORD=true` or use trusted SSO/OIDC before exposing the API.
- Use `TOOL_EXECUTION_MODE=approval` until live connector probes and compensation proof are complete.
- Confirm tenant headers are propagated for tasks, approvals, tool executions, and audit events.
- Verify audit-chain integrity before exporting evidence.
- Treat mojibake, stale README screenshots, tracked `.env`, or generated runtime state as release blockers.

## Recommended Pre-Launch Commands

```powershell
cd backend
python -m unittest discover -s tests
cd ..
python backend\scripts\evaluate_agent_traces.py
python backend\scripts\evaluate_rag.py --check-dataset
python backend\scripts\evaluate_rag.py --fixture-eval --report
python backend\scripts\check_public_hygiene.py
```

Frontend checks:

```powershell
cd frontend
pnpm typecheck
pnpm test:ui
pnpm build
```

## Portfolio Polish

- Keep `docs/screenshots/peopleops-intelligence-console.png` current.
- Make the README explicit about demo mode versus production mode.
- Attach evidence for PostgreSQL, Qdrant, OIDC, SMTP, object storage, and connector probes before making production claims.

## Review Checklist

- Security: no tracked secrets, local `.env`, or public compose output containing credentials.
- Agent correctness: golden traces pass for RAG, resume screening, missing context, and governed tool actions.
- RAG grounding: fixture and real retrieval gates meet the configured pass-rate and citation thresholds.
- Frontend clarity: the default console view has one obvious primary workflow and no broken Chinese text.
- GitHub presentation: README screenshot, badges, run instructions, ADRs, and launch limitations are current.
