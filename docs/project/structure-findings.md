# Findings & Decisions

## Requirements
- Root folder should look professional and not mix frontend and backend files.
- Frontend and backend boundaries should be clear in Windows Explorer.
- Existing functionality should keep working after the move.

## Research Findings
- Current root mixes Python entrypoints (`api.py`, `app.py`), `core/`, tests, scripts, Docker files, frontend, docs, data, and runtime folders.
- A clearer layout is a monorepo shape: `backend/`, `frontend/`, `infra/`, `data/`, `docs/`, `evals/`, `var/`.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Move `api.py`, `app.py`, `requirements.txt`, `core/`, `scripts/`, and `tests/` into `backend/` | These are Python/backend concerns. |
| Move `.runtime/` to `var/runtime/` and `.chroma/` to `var/chroma/` | Runtime state is not source code and should be grouped under a conventional state folder. |
| Move Docker files into `infra/` | Deployment/infrastructure files should not compete with app source files at root. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Project directory is outside the original writable root | Use elevated filesystem commands scoped to the new project directory. |

## Resources
- Project root: C:\Users\47912\Desktop\AGENT\peopleops-intelligence-agent

## Visual/Browser Findings
- User screenshot/feedback indicates the folder still feels visually mixed and unprofessional because backend files sit at root next to frontend and infra.
