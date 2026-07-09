# ADR 0002: Public Repository Quality Gates

## Status

Accepted.

## Context

The project is used as a public PeopleOps agent reference implementation. Its GitHub surface needs to demonstrate a working AI product while avoiding common launch risks: stale screenshots, accidental local artifacts, leaked secrets, broken Chinese UI text, and unsupported production claims.

## Decision

Public-facing changes must pass automated hygiene checks in addition to backend, RAG, agent-trace, frontend typecheck, UI-flow, and build gates.

The hygiene gate checks:

- tracked local/generated paths such as `.env`, `.next`, runtime state, and output artifacts;
- common secret token patterns and private key headers;
- mojibake markers in tracked text files;
- JSONL parseability for eval fixtures;
- README screenshot presence and deletion of old screenshots.

## Consequences

- README, docs, screenshots, and release-hardening changes are treated as shippable product surfaces, not secondary assets.
- UI text encoding problems fail before GitHub publication.
- Secret hygiene has a repository-local backstop even when a developer has real credentials in `.env`.
- Future production-readiness claims must be supported by explicit evidence and linked checks.

## Verification

```powershell
python backend/scripts/check_public_hygiene.py
```
