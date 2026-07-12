from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.candidate_assistance import render_candidate_assistance


DATASET = ROOT / "evals" / "candidate_assistance_safety.jsonl"


def evaluate(path: Path = DATASET) -> int:
    passed = 0
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for case in cases:
        reply = render_candidate_assistance(
            resume_text=case.get("resume_text", ""),
            jd_text=case.get("jd_text", ""),
            analysis=case.get("analysis", {}),
        )
        forbidden_hits = [term for term in case.get("forbidden_terms", []) if term.lower() in reply.lower()]
        missing_required = [term for term in case.get("required_terms", []) if term not in reply]
        ok = not forbidden_hits and not missing_required
        passed += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {case['id']} forbidden={forbidden_hits} missing={missing_required}")
    print(f"Candidate assistance safety eval: {passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(evaluate())
