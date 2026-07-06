import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
for path in (BACKEND_DIR, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.workflow import build_execution_plan, keyword_intent
from core.tools import list_registered_tools


DATASET = ROOT / "evals" / "agent_golden_traces.jsonl"
DEFAULT_REPORT_PATH = ROOT / "output" / "agent-golden-trace-report.json"


def load_dataset(path: Path = DATASET) -> list[dict]:
    cases: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        missing = [key for key in ("id", "input", "expected_intent", "expected_plan_steps") if key not in item]
        if missing:
            raise ValueError(f"{path}:{line_number} missing required keys: {', '.join(missing)}")
        cases.append(item)
    if not cases:
        raise ValueError(f"{path} does not contain any eval cases")
    return cases


def score_case(item: dict, registered_tools: set[str]) -> dict:
    state = {"input_text": item["input"], **item.get("context", {})}
    intent = keyword_intent(item["input"])
    plan, stop_condition = build_execution_plan(intent, state)
    plan_steps = [step["step"] for step in plan]
    expected_tools = set(item.get("allowed_tools", []))
    blocked_step = item.get("expected_blocked_step")
    blocked_ok = True
    if blocked_step:
        blocked_ok = any(step["step"] == blocked_step and step["status"] == "blocked" for step in plan)
    tool_registry_ok = expected_tools.issubset(registered_tools)
    return {
        "passed": (
            intent == item["expected_intent"]
            and plan_steps == item["expected_plan_steps"]
            and blocked_ok
            and tool_registry_ok
        ),
        "actual_intent": intent,
        "expected_intent": item["expected_intent"],
        "actual_plan_steps": plan_steps,
        "expected_plan_steps": item["expected_plan_steps"],
        "blocked_ok": blocked_ok,
        "registered_tools_ok": tool_registry_ok,
        "stop_condition": stop_condition,
    }


def evaluate(path: Path = DATASET, report_path: Path | None = None) -> int:
    registered_tools = {tool["name"] for tool in list_registered_tools()}
    results = []
    for item in load_dataset(path):
        metrics = score_case(item, registered_tools)
        print(
            f"[{'PASS' if metrics['passed'] else 'FAIL'}] {item['id']} "
            f"intent={metrics['actual_intent']} steps={len(metrics['actual_plan_steps'])}"
        )
        results.append({"id": item["id"], "risk_tag": item.get("risk_tag", "general"), "metrics": metrics})

    passed = sum(1 for item in results if item["metrics"]["passed"])
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(path),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / max(len(results), 1),
        "registered_tools": sorted(registered_tools),
        "gate_passed": passed == len(results),
        "results": results,
    }
    print(f"Agent golden traces: {summary['passed']}/{summary['total']} passed")
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Agent golden trace report written: {report_path}")
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run deterministic PeopleOps agent golden trace checks.")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--report", type=Path, nargs="?", const=DEFAULT_REPORT_PATH, default=None)
    args = parser.parse_args()
    raise SystemExit(evaluate(path=args.dataset, report_path=args.report))
