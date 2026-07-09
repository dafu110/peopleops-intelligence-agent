# ADR 0001: Governed PeopleOps Tool Execution

## Status

Accepted.

## Context

PeopleOps Intelligence Agent can create candidate follow-up actions, email drafts, calendar artifacts, ATS-style records, approval requests, and candidate stage changes. These actions involve private candidate data and can become externally visible in live deployments.

## Decision

Tool execution is governed through explicit execution modes:

- `dry_run`: no side-effecting artifacts beyond the response.
- `approval`: create auditable pending actions for human review.
- `local`: persist local artifacts for demo and development.
- `live`: allow external side effects only after release gates are satisfied.

Tools must write audit events, use tenant scope, generate idempotency keys, and support compensation where practical.

## Consequences

- Production-like demos should prefer `TOOL_EXECUTION_MODE=approval`.
- `live` mode requires external connector proof and rollback/compensation evidence.
- Tool responses should expose action IDs, approval IDs, idempotency keys, and tenant scope.
- Sensitive candidate data should be redacted from logs and audit payloads.

## Verification

```powershell
cd backend
python -m unittest discover -s tests
cd ..
python backend\scripts\evaluate_agent_traces.py
python backend\scripts\evaluate_rag.py --fixture-eval --report
```
