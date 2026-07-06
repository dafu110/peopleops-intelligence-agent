# Task Plan: Professional Project Structure

## Goal
Make the PeopleOps Intelligence Agent folder visually and technically clear by separating backend, frontend, infrastructure, data, docs, and runtime state.

## Current Phase
Phase 1

## Phases

### Phase 1: Discovery
- [x] Confirm current messy root layout
- [x] Identify frontend/backend ambiguity
- **Status:** complete

### Phase 2: Restructure
- [x] Create backend, infra, and var folders
- [x] Move backend code, tests, scripts, and runtime state into clear locations
- [x] Keep frontend as its own application folder
- **Status:** complete

### Phase 3: Path Updates
- [x] Update imports/commands/docs/CI/Docker for the new layout
- [x] Update environment defaults for var/runtime and var/chroma
- **Status:** pending

### Phase 4: Verification
- [x] Compile backend Python files
- [x] Run backend tests
- [x] Check frontend package/build readiness
- **Status:** pending

### Phase 5: Delivery
- [x] Review final folder tree
- [x] Report changed structure and verification results
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use backend/ for Python API, Streamlit legacy app, core package, tests, scripts, and requirements | Makes Python application boundary obvious. |
| Keep frontend/ as the Next.js UI app | Separates professional UI implementation from backend services. |
| Use infra/ for Docker and compose | Keeps deployment files out of application roots. |
| Use var/ for local runtime/chroma state | Avoids hidden runtime directories cluttering the root. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| None yet | 1 | N/A |
