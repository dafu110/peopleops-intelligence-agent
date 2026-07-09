# Demo Flow

This walkthrough is for reviewers who want to see the PeopleOps Intelligence Agent work as a real HRBP console rather than a static RAG demo.

## Goal

In about 60 seconds, demonstrate that the app can:

- collect candidate and job context;
- answer HR policy questions with grounded citations;
- compare a resume against a JD;
- create governed candidate follow-up actions;
- expose approval, trace, and audit evidence.

## Prerequisites

Start the backend and frontend from the repository root:

```powershell
Copy-Item .env.example .env
$env:PYTHONPATH="backend"
python -m uvicorn api:app --app-dir backend --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open `http://127.0.0.1:3000`.

## Walkthrough

1. Upload or open `data/测试简历.pdf`, then paste the extracted candidate summary into the left candidate context panel.
2. Open `data/职位描述.pdf`, then paste the JD requirements into the left JD panel.
3. In the center Agent input, ask:

```text
这份简历和 JD 的匹配度如何？
```

Expected result: the Agent returns a fit analysis, highlights strengths and risks, and the right-side trace panel records the task.

4. Ask a policy RAG question:

```text
差旅住宿报销标准是什么？
```

Expected result: the Agent answers with cited handbook evidence, and the evidence/trace panels show the referenced source.

5. Trigger a governed action:

```text
生成候选人面试跟进动作。
```

Expected result: the app creates an action/approval record rather than silently performing an external side effect.

6. Switch the right-side inspector tabs:

- `概览`: readiness score, connector count, tool mode, database, vector store, and launch checks.
- `追溯`: citations and task replay.
- `动作`: approvals, tools, tool executions, and connector status.
- `审计`: audit-chain event history.

## What To Point Out

- The primary workflow is one Agent input, not separate disconnected search boxes.
- RAG answers are grounded in the local Chinese HR handbook fixture.
- Side-effecting actions are governed through approval and audit records.
- The project includes CI gates for backend tests, RAG evals, agent traces, frontend typecheck/build, and public repository hygiene.

## Demo vs Production Notes

- Local mode uses SQLite, Chroma, local artifact folders, and optional access-password mode.
- Production mode should use PostgreSQL, managed vector search, object storage, SSO/OIDC, connector probes, and `TOOL_EXECUTION_MODE=approval` before live execution.
- Do not publish `docker compose config` output if your local `.env` contains real credentials.
