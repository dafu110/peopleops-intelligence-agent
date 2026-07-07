# Five Minute Demo Script

Audience: reviewers, hiring managers, and operators who need to understand the real product loop quickly.

## Before The Demo

Start the local stack:

```powershell
cd C:\Users\lenovo\Desktop\AGENT\peopleops-intelligence-agent
docker compose -f infra/docker-compose.yml up --build
```

Open:

- Web console: `http://127.0.0.1:3000`
- API health: `http://127.0.0.1:8000/health`

If Docker cannot pull `python:3.11-slim`, fix Docker Desktop DNS/proxy first and verify:

```powershell
docker pull python:3.11-slim
```

## Demo Flow

1. **Show readiness**
   - Point to the right-side runtime and launch-check panels.
   - Explain model, database, vector backend, object storage, identity mode, and audit-chain status.

2. **Upload candidate context**
   - Upload `data/测试简历.pdf` or paste extracted resume text.
   - Paste the role description from `data/职位描述.pdf` or the JD textarea.
   - Confirm the left panel shows parsed candidate context.

3. **Ask a policy question**
   - Example: `差旅住宿报销标准是什么？`
   - Show the response and RAG evidence panel.

4. **Run resume/JD matching**
   - Example: `这份简历和 JD 是否匹配？请给出优势和风险。`
   - Show structured fit reasoning in the Agent workspace.

5. **Create a candidate follow-up action**
   - Example: `帮我安排候选人 Alice 明天下午 2 点面试，邮箱 alice@example.com。`
   - Show the action in “动作与审批”.
   - Show generated local artifacts under `var/runtime/email_drafts`, `var/runtime/calendar`, and `var/runtime/ats_exports` when running in local mode.

6. **Review task replay**
   - Open the “任务回放” panel.
   - Select the latest task and walk through `task.created`, `workflow.started`, route/tool/RAG events, and completion events.

7. **Inspect tool governance**
   - Show “工具目录” for registry metadata.
   - Show “最近工具执行” for status, attempts, and idempotency key.
   - Explain that successful mutating tools can be compensated through the API.

8. **Close with audit evidence**
   - Show “审计链”.
   - Open `/audit/integrity` if needed to prove hash-chain validation.

## Expected Talking Points

- The console is not a static dashboard: upload, chat, tool execution, task replay, and audit panels are backed by FastAPI endpoints.
- SQLite, Chroma, and local files are reference backends for local demos.
- PostgreSQL, Qdrant, and MinIO are available in `infra/docker-compose.production.yml` for production dependency validation.
- Enterprise SSO/OIDC and external ATS/calendar integrations still need a real customer environment to validate end to end.
