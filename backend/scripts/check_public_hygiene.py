from __future__ import annotations

import json
import re
import subprocess
from urllib.parse import unquote, urlparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

BLOCKED_TRACKED_PREFIXES = (
    ".env",
    ".playwright-cli/",
    ".pnpm-store/",
    "frontend/.next/",
    "frontend/node_modules/",
    "node_modules/",
    "output/",
    "var/chroma/",
    "var/runtime/",
)

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{24,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
)

MOJIBAKE_PATTERNS = (
    "\ufffd",
    "\u93c6",
    "\u934a",
    "\u7ec9\u71b8",
    "\u7481\u5757",
    "\u6d63\u72b2\u30bd",
    "\u9286",
    "\u951b",
    "\u9422",
    "\u5bf0\u546d",
)

TEXT_SUFFIXES = {
    ".css",
    ".env",
    ".example",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".tsx",
    ".ts",
    ".txt",
    ".yml",
    ".yaml",
}

README_SCREENSHOT = "docs/screenshots/peopleops-intelligence-console.png"
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
LOCAL_MARKDOWN_TARGET_SUFFIXES = {".md", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.name in {".env.example", ".gitignore", "AGENTS.md", "README.md"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check_blocked_paths(files: list[str], failures: list[str]) -> None:
    for item in files:
        normalized = item.rstrip("/")
        if normalized == ".env" or any(normalized.startswith(prefix) for prefix in BLOCKED_TRACKED_PREFIXES if prefix != ".env"):
            failures.append(f"Tracked generated/local file should not be public: {item}")


def check_text_quality(files: list[str], failures: list[str]) -> None:
    for item in files:
        path = ROOT / item
        if not path.exists() or not is_text_file(path):
            continue
        text = read_text(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"Possible secret literal in tracked file: {item}")
                break
        for marker in MOJIBAKE_PATTERNS:
            if marker in text:
                failures.append(f"Possible mojibake marker {marker!r} in tracked file: {item}")
                break


def check_jsonl(files: list[str], failures: list[str]) -> None:
    for item in files:
        if not item.endswith(".jsonl"):
            continue
        path = ROOT / item
        for line_number, line in enumerate(read_text(path).splitlines(), start=1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                failures.append(f"Invalid JSONL in {item}:{line_number}: {exc}")


def check_readme_screenshot(files: list[str], failures: list[str]) -> None:
    readme = read_text(ROOT / "README.md")
    if README_SCREENSHOT not in readme:
        failures.append(f"README does not reference {README_SCREENSHOT}")
    if README_SCREENSHOT not in files:
        failures.append(f"README screenshot is not tracked: {README_SCREENSHOT}")
    if not (ROOT / README_SCREENSHOT).exists():
        failures.append(f"README screenshot is missing on disk: {README_SCREENSHOT}")
    old_screenshots = [
        "docs/screenshots/peopleops-enterprise-console-overview.png",
        "docs/screenshots/peopleops-enterprise-console-governance.png",
    ]
    for screenshot in old_screenshots:
        if screenshot in files:
            failures.append(f"Old README screenshot should stay deleted: {screenshot}")


def is_local_link(target: str) -> bool:
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    if target.startswith("#"):
        return False
    return True


def check_markdown_links(files: list[str], failures: list[str]) -> None:
    markdown_files = [item for item in files if item.endswith(".md")]
    for item in markdown_files:
        source = ROOT / item
        if not source.exists():
            continue
        text = read_text(source)
        for match in MARKDOWN_LINK_PATTERN.finditer(text):
            target = match.group(1).strip()
            if not target or not is_local_link(target):
                continue
            clean_target = target.split("#", 1)[0].strip()
            if not clean_target:
                continue
            if clean_target.startswith("<") and clean_target.endswith(">"):
                clean_target = clean_target[1:-1]
            clean_target = unquote(clean_target)
            target_path = (source.parent / clean_target).resolve()
            try:
                target_path.relative_to(ROOT)
            except ValueError:
                failures.append(f"Markdown link escapes repository root: {item} -> {target}")
                continue
            if Path(clean_target).suffix.lower() not in LOCAL_MARKDOWN_TARGET_SUFFIXES and "." not in Path(clean_target).name:
                continue
            if not target_path.exists():
                failures.append(f"Broken local Markdown link: {item} -> {target}")


def main() -> int:
    failures: list[str] = []
    files = git_ls_files()
    check_blocked_paths(files, failures)
    check_text_quality(files, failures)
    check_jsonl(files, failures)
    check_readme_screenshot(files, failures)
    check_markdown_links(files, failures)

    if failures:
        print("Public repository hygiene check failed:")
        for failure in failures:
            safe_failure = failure.encode("ascii", errors="backslashreplace").decode("ascii")
            print(f"- {safe_failure}")
        return 1

    print("Public repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
