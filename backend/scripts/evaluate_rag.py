import json
import argparse
import importlib.util
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
for path in (BACKEND_DIR, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.database import create_rag_evaluation
from core.security import EMAIL_RE, ID_CARD_RE, PHONE_RE
from core.config import get_settings


DATASET = ROOT / "evals" / "rag_eval.jsonl"
DEFAULT_REPORT_PATH = ROOT / "output" / "rag-eval-report.json"


def score_case(
    context: str,
    sources: list[str],
    expected_keywords: list[str],
    expected_sources: list[str] | None = None,
    forbidden_terms: list[str] | None = None,
) -> dict:
    settings = get_settings()
    expected_sources = expected_sources or []
    forbidden_terms = forbidden_terms or []
    matched_keywords = [keyword for keyword in expected_keywords if keyword in context]
    keyword_coverage = len(matched_keywords) / max(len(expected_keywords), 1)
    citation_count = len(sources)
    matched_sources = [source for source in expected_sources if any(source in actual for actual in sources)]
    citation_correctness = len(matched_sources) / max(len(expected_sources), 1) if expected_sources else 1.0
    pii_leakage = bool(PHONE_RE.search(context) or EMAIL_RE.search(context) or ID_CARD_RE.search(context))
    forbidden_hits = [term for term in forbidden_terms if term in context]
    passed = (
        bool(context)
        and keyword_coverage >= settings.rag_min_keyword_coverage
        and citation_count > 0
        and citation_correctness >= settings.rag_min_citation_correctness
        and not pii_leakage
        and not forbidden_hits
    )
    return {
        "passed": passed,
        "matched_keywords": matched_keywords,
        "keyword_coverage": keyword_coverage,
        "citation_count": citation_count,
        "citation_correctness": citation_correctness,
        "matched_sources": matched_sources,
        "pii_leakage": pii_leakage,
        "forbidden_hits": forbidden_hits,
        "context_chars": len(context),
    }


def load_dataset(path: Path = DATASET) -> list[dict]:
    cases: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        missing = [key for key in ("question", "expected_keywords") if key not in item]
        if missing:
            raise ValueError(f"{path}:{line_number} missing required keys: {', '.join(missing)}")
        if not isinstance(item["expected_keywords"], list):
            raise ValueError(f"{path}:{line_number} expected_keywords must be a list")
        cases.append(item)
    if not cases:
        raise ValueError(f"{path} does not contain any eval cases")
    return cases


def check_dataset(path: Path = DATASET) -> int:
    cases = load_dataset(path)
    print(f"RAG eval dataset OK: {len(cases)} cases at {path}")
    return 0


def summarize_results(results: list[dict], mode: str) -> dict:
    settings = get_settings()
    total = len(results)
    passed = sum(1 for item in results if item["metrics"]["passed"])
    pass_rate = passed / max(total, 1)
    avg_keyword_coverage = sum(item["metrics"]["keyword_coverage"] for item in results) / max(total, 1)
    avg_citation_correctness = sum(item["metrics"]["citation_correctness"] for item in results) / max(total, 1)
    pii_leakage_cases = [item["id"] for item in results if item["metrics"]["pii_leakage"]]
    forbidden_hit_cases = [item["id"] for item in results if item["metrics"]["forbidden_hits"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "dataset": str(DATASET),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "required_pass_rate": settings.rag_min_pass_rate,
        "avg_keyword_coverage": avg_keyword_coverage,
        "required_keyword_coverage": settings.rag_min_keyword_coverage,
        "avg_citation_correctness": avg_citation_correctness,
        "required_citation_correctness": settings.rag_min_citation_correctness,
        "pii_leakage_cases": pii_leakage_cases,
        "forbidden_hit_cases": forbidden_hit_cases,
        "gate_passed": pass_rate >= settings.rag_min_pass_rate and not pii_leakage_cases and not forbidden_hit_cases,
        "results": results,
    }


def write_report(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RAG eval report written: {path}")


def generation_readiness() -> dict:
    settings = get_settings()
    checks = []
    api_host = urlparse(settings.api_base or "").hostname or ""
    chat_api_is_local = api_host in {"localhost", "127.0.0.1", "::1"}
    external_eval_allowed = os.getenv("ALLOW_RAG_EXTERNAL_EVAL", "").strip().lower() in {"1", "true", "yes", "on"}

    checks.append({
        "id": "chat_model_config",
        "ready": settings.has_llm_config,
        "detail": "OPENAI_API_KEY and OPENAI_API_BASE are configured." if settings.has_llm_config else "OPENAI_API_KEY or OPENAI_API_BASE is missing.",
    })
    checks.append({
        "id": "chat_model_data_boundary",
        "ready": bool(settings.has_llm_config and (chat_api_is_local or external_eval_allowed)),
        "detail": (
            "Chat model API base is local."
            if chat_api_is_local
            else "External chat model eval explicitly allowed by ALLOW_RAG_EXTERNAL_EVAL."
            if external_eval_allowed
            else "Live generation eval may send policy context to an external chat model. Set ALLOW_RAG_EXTERNAL_EVAL=true only after approving that data transfer."
        ),
    })
    checks.append({
        "id": "policy_pdf",
        "ready": settings.policy_pdf_path.exists(),
        "detail": str(settings.policy_pdf_path),
    })
    if settings.vector_backend == "qdrant":
        checks.append({
            "id": "qdrant_url",
            "ready": bool(settings.vector_store_url),
            "detail": "VECTOR_STORE_URL configured." if settings.vector_store_url else "VECTOR_STORE_URL is required for qdrant.",
        })

    optional_imports = [
        ("langchain_openai", "Chat model client"),
        ("langchain_huggingface", "Embedding client"),
        ("langchain_community", "PDF loader/vector store integrations"),
        ("langchain_text_splitters", "Document chunking"),
    ]
    for module_name, label in optional_imports:
        if importlib.util.find_spec(module_name) is not None:
            ready = True
            detail = f"{label} import OK."
        else:
            ready = False
            detail = f"{label} missing: {module_name}."
        checks.append({"id": module_name, "ready": ready, "detail": detail})

    allow_model_download = os.getenv("ALLOW_RAG_MODEL_DOWNLOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    embedding_cache_ready = False
    embedding_cache_detail = "Embedding model cache was not checked."
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(settings.embedding_model, local_files_only=True)
        embedding_cache_ready = True
        embedding_cache_detail = f"Embedding model is available in local Hugging Face cache: {settings.embedding_model}."
    except ModuleNotFoundError:
        embedding_cache_detail = "huggingface_hub is not installed, so offline embedding cache cannot be checked."
    except Exception as exc:
        embedding_cache_detail = (
            f"Embedding model is not available offline: {settings.embedding_model}. "
            "Set ALLOW_RAG_MODEL_DOWNLOAD=true only after approving external model download/network access. "
            f"Original error: {exc}"
        )
    checks.append({
        "id": "embedding_model_offline_cache",
        "ready": embedding_cache_ready or allow_model_download,
        "detail": embedding_cache_detail if not allow_model_download else "External embedding model download is explicitly allowed by ALLOW_RAG_MODEL_DOWNLOAD.",
    })

    return {
        "ready": all(item["ready"] for item in checks),
        "mode": "generation",
        "checks": checks,
    }


def check_generation_readiness() -> int:
    payload = generation_readiness()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


def evaluate(report_path: Path | None = None) -> int:
    from core.rag_engine import retrieve_policy_context

    results: list[dict] = []

    for index, item in enumerate(load_dataset(DATASET), start=1):
        context, sources = retrieve_policy_context(item["question"])
        expected_keywords = item.get("expected_keywords", [])
        metrics = score_case(
            context,
            sources,
            expected_keywords,
            expected_sources=item.get("expected_sources", []),
            forbidden_terms=item.get("forbidden_terms", []),
        )
        ok = metrics["passed"]
        create_rag_evaluation(
            question=item["question"],
            expected_keywords=",".join(expected_keywords),
            retrieved_sources=",".join(sources),
            passed=ok,
            metrics=metrics,
        )
        print(
            f"[{'PASS' if ok else 'FAIL'}] {item['question']} "
            f"coverage={metrics['keyword_coverage']:.0%} "
            f"citations={metrics['citation_count']} "
            f"citation_correctness={metrics['citation_correctness']:.0%} "
            f"pii_leakage={metrics['pii_leakage']} "
            f"forbidden_hits={len(metrics['forbidden_hits'])} "
                f"chars={metrics['context_chars']} -> {sources}"
        )
        results.append(
            {
                "id": item.get("id", f"case-{index}"),
                "question": item["question"],
                "expected_keywords": expected_keywords,
                "expected_sources": item.get("expected_sources", []),
                "retrieved_sources": sources,
                "metrics": metrics,
            }
        )

    summary = summarize_results(results, mode="retriever")
    print(f"RAG eval: {summary['passed']}/{summary['total']} passed")
    print(f"RAG eval pass_rate={summary['pass_rate']:.0%} required={summary['required_pass_rate']:.0%}")
    if report_path:
        write_report(summary, report_path)
    return 0 if summary["gate_passed"] else 1


def evaluate_generation(report_path: Path | None = None) -> int:
    readiness = generation_readiness()
    if not readiness["ready"]:
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
        print("RAG generation eval skipped: live generation dependencies are not ready.")
        return 2

    from core.rag_engine import ask_rag_with_evidence

    results: list[dict] = []
    for index, item in enumerate(load_dataset(DATASET), start=1):
        answer = ask_rag_with_evidence(item["question"])
        reply = str(answer.get("reply", ""))
        evidence = list(answer.get("evidence", []))
        sources = list(answer.get("sources") or [entry.get("source", "") for entry in evidence if entry.get("source")])
        expected_keywords = item.get("expected_keywords", [])
        metrics = score_case(
            reply,
            sources,
            expected_keywords,
            expected_sources=item.get("expected_sources", []),
            forbidden_terms=item.get("forbidden_terms", []),
        )
        metrics["reply_chars"] = len(reply)
        metrics["evidence_count"] = len(evidence)
        ok = metrics["passed"]
        create_rag_evaluation(
            question=item["question"],
            expected_keywords=",".join(expected_keywords),
            retrieved_sources=",".join(sources),
            passed=ok,
            metrics=metrics,
        )
        print(
            f"[{'PASS' if ok else 'FAIL'}] {item['question']} "
            f"answer_coverage={metrics['keyword_coverage']:.0%} "
            f"citations={metrics['citation_count']} "
            f"evidence={metrics['evidence_count']} "
            f"pii_leakage={metrics['pii_leakage']}"
        )
        results.append(
            {
                "id": item.get("id", f"case-{index}"),
                "question": item["question"],
                "expected_keywords": expected_keywords,
                "expected_sources": item.get("expected_sources", []),
                "retrieved_sources": sources,
                "metrics": metrics,
            }
        )

    summary = summarize_results(results, mode="generation")
    print(f"RAG generation eval: {summary['passed']}/{summary['total']} passed")
    print(f"RAG generation pass_rate={summary['pass_rate']:.0%} required={summary['required_pass_rate']:.0%}")
    if report_path:
        write_report(summary, report_path)
    return 0 if summary["gate_passed"] else 1


def evaluate_fixture(path: Path = DATASET, report_path: Path | None = None) -> int:
    results: list[dict] = []
    for index, item in enumerate(load_dataset(path), start=1):
        context = item.get("retrieved_context") or " ".join(item.get("expected_keywords", []))
        sources = item.get("retrieved_sources") or item.get("expected_sources") or ["fixture-source"]
        metrics = score_case(
            context,
            sources,
            item.get("expected_keywords", []),
            expected_sources=item.get("expected_sources", []),
            forbidden_terms=item.get("forbidden_terms", []),
        )
        print(
            f"[{'PASS' if metrics['passed'] else 'FAIL'}] {item['question']} "
            f"coverage={metrics['keyword_coverage']:.0%} "
            f"citation_correctness={metrics['citation_correctness']:.0%} "
            f"chars={metrics['context_chars']}"
        )
        results.append(
            {
                "id": item.get("id", f"case-{index}"),
                "question": item["question"],
                "expected_keywords": item.get("expected_keywords", []),
                "expected_sources": item.get("expected_sources", []),
                "retrieved_sources": sources,
                "metrics": metrics,
            }
        )
    summary = summarize_results(results, mode="fixture")
    print(
        f"RAG fixture eval: {summary['passed']}/{summary['total']} passed "
        f"pass_rate={summary['pass_rate']:.0%} required={summary['required_pass_rate']:.0%}"
    )
    if report_path:
        write_report(summary, report_path)
    return 0 if summary["gate_passed"] else 1


def evaluate_generation_fixture(path: Path = DATASET, report_path: Path | None = None) -> int:
    results: list[dict] = []
    for index, item in enumerate(load_dataset(path), start=1):
        answer = item.get("generated_answer") or item.get("retrieved_context") or " ".join(item.get("expected_keywords", []))
        sources = item.get("retrieved_sources") or item.get("expected_sources") or ["fixture-source"]
        metrics = score_case(
            answer,
            sources,
            item.get("expected_keywords", []),
            expected_sources=item.get("expected_sources", []),
            forbidden_terms=item.get("forbidden_terms", []),
        )
        metrics["answer_chars"] = len(answer)
        metrics["answer_has_source_label"] = bool(sources)
        metrics["faithfulness_mode"] = "fixture_answer_keywords_and_safety"
        print(
            f"[{'PASS' if metrics['passed'] else 'FAIL'}] {item['question']} "
            f"answer_coverage={metrics['keyword_coverage']:.0%} "
            f"citation_correctness={metrics['citation_correctness']:.0%} "
            f"pii_leakage={metrics['pii_leakage']}"
        )
        results.append(
            {
                "id": item.get("id", f"case-{index}"),
                "question": item["question"],
                "expected_keywords": item.get("expected_keywords", []),
                "expected_sources": item.get("expected_sources", []),
                "retrieved_sources": sources,
                "metrics": metrics,
            }
        )
    summary = summarize_results(results, mode="generation_fixture")
    print(
        f"RAG generation fixture eval: {summary['passed']}/{summary['total']} passed "
        f"pass_rate={summary['pass_rate']:.0%} required={summary['required_pass_rate']:.0%}"
    )
    if report_path:
        write_report(summary, report_path)
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run or validate PeopleOps RAG evaluations.")
    parser.add_argument(
        "--check-dataset",
        action="store_true",
        help="Validate eval dataset shape without loading embeddings or model dependencies.",
    )
    parser.add_argument(
        "--fixture-eval",
        action="store_true",
        help="Run the retrieval scoring gate against fixture contexts without loading embeddings.",
    )
    parser.add_argument(
        "--generation-fixture",
        action="store_true",
        help="Run answer-level fixture checks for keyword faithfulness, citations, and PII safety.",
    )
    parser.add_argument(
        "--generation-eval",
        action="store_true",
        help="Run live retrieval plus generated-answer scoring. Requires full RAG and model configuration.",
    )
    parser.add_argument(
        "--generation-readiness",
        action="store_true",
        help="Check whether live RAG generation evaluation can run in this environment.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        nargs="?",
        const=DEFAULT_REPORT_PATH,
        default=None,
        help="Write a JSON eval report. Defaults to output/rag-eval-report.json when no path is provided.",
    )
    args = parser.parse_args()
    if args.check_dataset:
        raise SystemExit(check_dataset())
    if args.generation_readiness:
        raise SystemExit(check_generation_readiness())
    if args.generation_eval:
        raise SystemExit(evaluate_generation(report_path=args.report))
    if args.generation_fixture:
        raise SystemExit(evaluate_generation_fixture(report_path=args.report))
    raise SystemExit(evaluate_fixture(report_path=args.report) if args.fixture_eval else evaluate(report_path=args.report))
