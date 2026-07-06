# PeopleOps Agent Registry

This directory documents the locally implemented PeopleOps Intelligence Agent.

- `peopleops-agent.json` defines the agent objective, state machine, tool boundaries, memory, and eval gates.
- Runtime implementation lives in `backend/core/workflow.py`.
- Governed tools live in `backend/core/tools.py`.
- RAG quality cases live in `evals/rag_eval.jsonl`.
- Agent golden trace cases live in `evals/agent_golden_traces.jsonl`.

Use these checks after agent changes:

```powershell
cd backend
python -m unittest tests.test_core
python scripts/evaluate_rag.py --check-dataset
python scripts/evaluate_rag.py --fixture-eval
python scripts/evaluate_rag.py --generation-fixture
python scripts/evaluate_rag.py --generation-readiness
python scripts/evaluate_rag.py --generation-eval
python scripts/evaluate_agent_traces.py
```

`--generation-readiness` checks live dependencies first, including whether the embedding model is available in the local Hugging Face cache and whether the chat model endpoint is local or explicitly approved. `--generation-eval` uses the live RAG and chat model configuration; use fixture gates for offline CI. Set `ALLOW_RAG_MODEL_DOWNLOAD=true` only after approving external model download/network access, and set `ALLOW_RAG_EXTERNAL_EVAL=true` only after approving policy-context transfer to an external chat model.
