#!/usr/bin/env python3
"""Audit narrative unit dossier quality with lightweight story-structure heuristics.

This script is intentionally advisory. It does not mutate source files; it
produces a ranked JSON report that helps decide which narrative units should be
targeted for prompt tuning or selective reruns.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List


ABSTRACT_TITLE_TOKENS = (
    "破局",
    "入局",
    "终局",
    "立基",
    "暗流",
    "薪火",
    "远行",
    "裂变",
    "定局",
    "转轨",
    "破茧",
    "变局",
    "暗涌",
    "启程",
    "风云",
    "震荡",
    "定势",
)

GENERIC_FUNCTION_MARKERS = (
    "推动剧情发展",
    "承上启下",
    "起到承接作用",
    "推动后续发展",
    "完成叙事推进",
    "为后续铺垫",
)

GENERIC_STRUCTURAL_MARKERS = (
    "作为",
    "完成了",
    "标志着",
    "正式开启",
    "正式踏入",
    "结构性转折",
    "叙事转向",
    "命运轴线",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _contains_any(text: str, tokens: List[str] | tuple[str, ...]) -> bool:
    return any(token and token in text for token in tokens)


def _anchor_tokens(unit: dict) -> List[str]:
    anchors: List[str] = []
    for raw in (unit.get("main_roles") or []) + (unit.get("main_locations") or []):
        name = str(raw or "").strip()
        if len(name) >= 2:
            anchors.append(name)
    return anchors


@dataclass
class AuditFinding:
    unit_id: str
    title: str
    severity: str
    score: int
    reasons: List[str]
    suggestions: List[str]


def audit_units(payload: dict) -> Dict[str, Any]:
    findings: List[AuditFinding] = []
    severity_counts = {"high": 0, "medium": 0, "low": 0}

    for unit in payload.get("units") or []:
        title = str(unit.get("title", "")).strip()
        display_summary = str(unit.get("display_summary", "")).strip()
        long_summary = str(unit.get("long_summary", "")).strip()
        dramatic_function = str(unit.get("dramatic_function", "")).strip()
        what_changes = str(unit.get("what_changes", "")).strip()
        stakes = str(unit.get("stakes", "")).strip()
        anchors = _anchor_tokens(unit)

        reasons: List[str] = []
        suggestions: List[str] = []
        score = 0

        if title and _contains_any(title, ABSTRACT_TITLE_TOKENS) and not _contains_any(title, anchors):
            reasons.append("title_abstract_without_anchor")
            suggestions.append("标题可加入更具体的人物、地点或局势锚点，而不是只用抽象结构词。")
            score += 2

        if display_summary and not _contains_any(display_summary, anchors):
            reasons.append("display_summary_lacks_role_or_location_anchor")
            suggestions.append("display_summary 可更早落到主要人物或场域，减少纯概念化表述。")
            score += 1

        if dramatic_function in GENERIC_FUNCTION_MARKERS:
            reasons.append("dramatic_function_too_generic")
            suggestions.append("dramatic_function 应说明这段戏为何必要，而不是只说承上启下。")
            score += 3

        if dramatic_function and _contains_any(dramatic_function, GENERIC_STRUCTURAL_MARKERS) and not _contains_any(dramatic_function, anchors):
            reasons.append("dramatic_function_high_level_but_low_specificity")
            suggestions.append("dramatic_function 可增加具体角色、关系或局势变化的指向。")
            score += 1

        if what_changes and not _contains_any(what_changes, anchors):
            reasons.append("what_changes_lacks_concrete_anchor")
            suggestions.append("what_changes 应明确是谁、在哪条关系或哪种局势上发生变化。")
            score += 1

        if stakes and len(_normalize_text(stakes)) > 80 and not _contains_any(stakes, anchors):
            reasons.append("stakes_overly_abstract")
            suggestions.append("stakes 可少讲抽象后果，多讲这段戏失败会损失什么具体戏剧价值。")
            score += 1

        if score <= 0:
            continue

        if score >= 4:
            severity = "high"
        elif score >= 2:
            severity = "medium"
        else:
            severity = "low"
        severity_counts[severity] += 1

        findings.append(
            AuditFinding(
                unit_id=str(unit.get("unit_id", "")).strip(),
                title=title,
                severity=severity,
                score=score,
                reasons=reasons,
                suggestions=suggestions,
            )
        )

    findings.sort(key=lambda item: (-item.score, item.unit_id))
    return {
        "generated_at": payload.get("generated_at"),
        "unit_count": len(payload.get("units") or []),
        "flagged_count": len(findings),
        "severity_counts": severity_counts,
        "findings": [asdict(item) for item in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit narrative unit dossier quality.")
    parser.add_argument("--units", default="data/narrative_units.json", help="Narrative units JSON path")
    parser.add_argument(
        "--output",
        default="data/narrative_unit_quality_audit.json",
        help="Where to write the audit report",
    )
    args = parser.parse_args()

    units_path = Path(args.units)
    output_path = Path(args.output)

    payload = _load_json(units_path)
    report = audit_units(payload)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Narrative unit quality audit -> {output_path}")
    print(f"Units: {report['unit_count']}  Flagged: {report['flagged_count']}")
    print(
        "Severity:"
        f" high={report['severity_counts']['high']}"
        f" medium={report['severity_counts']['medium']}"
        f" low={report['severity_counts']['low']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
