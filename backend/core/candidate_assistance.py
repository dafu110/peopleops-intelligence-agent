from __future__ import annotations

from typing import Any, Iterable

from .security import redact_pii


DECISION_TERMS = (
    "录用",
    "淘汰",
    "拒绝",
    "通过",
    "不通过",
    "聘用",
    "推荐",
    "适合",
    "不适合",
    "匹配度",
    "hire",
    "reject",
)

PROTECTED_TRAIT_TERMS = (
    "性别",
    "年龄",
    "婚育",
    "婚姻",
    "已婚",
    "未婚",
    "怀孕",
    "民族",
    "籍贯",
    "残疾",
)


def _safe_items(items: Iterable[Any]) -> list[str]:
    safe: list[str] = []
    for item in items:
        text = redact_pii(str(item or "").strip())
        if not text:
            continue
        if any(term.lower() in text.lower() for term in PROTECTED_TRAIT_TERMS):
            safe.append("该项包含不应作为岗位判断依据的受保护特征，已移除；请仅围绕岗位相关证据复核。")
        elif any(term.lower() in text.lower() for term in DECISION_TERMS):
            safe.append("该项包含决策性措辞，已移除；请由 HRBP 基于原始材料独立复核。")
        else:
            safe.append(text)
    return safe


def render_candidate_assistance(*, resume_text: str, jd_text: str, analysis: dict[str, Any]) -> str:
    """Render candidate material as evidence-only decision support for HRBP review."""

    missing: list[str] = []
    if not resume_text.strip():
        missing.append("候选人简历")
    if not jd_text.strip():
        missing.append("职位说明（JD）")
    if missing:
        return (
            "### 候选人辅助（仅供 HRBP 复核）\n\n"
            f"缺少{'、'.join(missing)}，不形成匹配结论。请补充材料后，由 HRBP 结合岗位背景和组织要求复核。"
        )

    evidence = _safe_items(analysis.get("pros", []))
    pending = _safe_items(analysis.get("cons", []))
    evidence_text = "\n".join(f"- {item}" for item in evidence) or "- 未提取到可核验的匹配证据。"
    pending_text = "\n".join(f"- {item}" for item in pending) or "- 未发现额外待确认项；仍需 HRBP 复核原始材料。"
    return (
        "### 候选人辅助（仅供 HRBP 复核）\n\n"
        "#### 可核验证据\n"
        f"{evidence_text}\n\n"
        "#### 待确认项与复核理由\n"
        f"{pending_text}\n\n"
        "#### 证据来源\n"
        "- 候选人简历材料（已脱敏）\n"
        "- 职位说明（JD）（已脱敏）\n\n"
        "系统不提供任何雇佣处置结论；最终判断、追问和后续动作由 HRBP 负责。"
    )
