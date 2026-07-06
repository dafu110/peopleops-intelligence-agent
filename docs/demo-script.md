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
   - Upload `data/娴嬭瘯绠€鍘?pdf` or paste extracted resume text.
   - Paste the role description from `data/鑱屼綅鎻忚堪.pdf` or the JD textarea.
   - Confirm the left panel shows parsed candidate context.

3. **Ask a policy question**
   - Example: `鍑哄樊浣忓鎶ラ攢鏍囧噯鏄粈涔堬紵`
   - Show the response and RAG evidence panel.

4. **Run resume/JD matching**
   - Example: `杩欎唤绠€鍘嗗拰 JD 鏄惁鍖归厤锛熻缁欏嚭浼樺娍鍜岄闄┿€俙
   - Show structured fit reasoning in the Agent workspace.

5. **Create a candidate follow-up action**
   - Example: `甯垜瀹夋帓鍊欓€変汉 Alice 鏄庡ぉ涓嬪崍 2 鐐归潰璇曪紝閭 alice@example.com銆俙
   - Show the action in 鈥滃姩浣滀笌瀹℃壒鈥?
   - Show generated local artifacts under `var/runtime/email_drafts`, `var/runtime/calendar`, and `var/runtime/ats_exports` when running in local mode.

6. **Review task replay**
   - Open the 鈥滀换鍔″洖鏀锯€?panel.
   - Select the latest task and walk through `task.created`, `workflow.started`, route/tool/RAG events, and completion events.

7. **Inspect tool governance**
   - Show 鈥滃伐鍏风洰褰曗€?for registry metadata.
   - Show 鈥滄渶杩戝伐鍏锋墽琛屸€?for status, attempts, and idempotency key.
   - Explain that successful mutating tools can be compensated through the API.

8. **Close with audit evidence**
   - Show 鈥滃璁￠摼鈥?
   - Open `/audit/integrity` if needed to prove hash-chain validation.

## Expected Talking Points

- The console is not a static dashboard: upload, chat, tool execution, task replay, and audit panels are backed by FastAPI endpoints.
- SQLite, Chroma, and local files are reference backends for local demos.
- PostgreSQL, Qdrant, and MinIO are available in `infra/docker-compose.production.yml` for production dependency validation.
- Enterprise SSO/OIDC and external ATS/calendar integrations still need a real customer environment to validate end to end.
