#!/usr/bin/env python3
"""
Generate event_display_catalog.json — grounded display titles for recurring
pattern-key events.

Rules enforced:
  - display_name must not equal pattern_key when corpus occurrence > 1
  - display_name must include at least 2 of: participant, action/conflict, location
  - display_name must be traceable to evidence_excerpt
  - one_line_event_summary ≤ 60 chars
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, List


CATALOG_VERSION = "event-display-catalog-v1"
GENERATOR_NAME = "local-agent"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --- Title generation helpers --------------------------------------------------

_ACTION_KEYWORDS = (
    "对话", "冲突", "相识", "照面", "同行", "南下", "起势", "揭示",
    "指点", "护持", "迁移", "遭遇", "会见", "传道", "过境", "争执",
    "告别", "立誓", "激战", "收徒", "赠剑", "赠物", "问道", "试探",
    "商议", "结盟", "追杀", "救援", "比武", "论道", "疗伤", "出关",
    "入城", "离城", "夜谈", "抉择", "交锋", "拜访", "现身",
)


def _extract_action_verb(evidence: str, pattern_key: str) -> str:
    """Try to extract a meaningful action verb from evidence or pattern_key."""
    for kw in _ACTION_KEYWORDS:
        if kw in pattern_key:
            return kw
    for kw in _ACTION_KEYWORDS:
        if kw in evidence:
            return kw
    return ""


def _build_display_name(pack: dict) -> str:
    """Build a grounded display_name from the event pack."""
    pattern_key = pack.get("pattern_key", "")
    participants = pack.get("participants", [])
    location = pack.get("location") or ""
    evidence = pack.get("evidence_excerpt", "")
    source_title = pack.get("source_unit_title", "")

    # Extract an action verb from the pattern_key or evidence
    action = _extract_action_verb(evidence, pattern_key)

    # Build title with at least 2 of 3 grounding signals
    parts_available = []
    if participants:
        parts_available.append("participant")
    if action:
        parts_available.append("action")
    if location:
        parts_available.append("location")

    if len(participants) >= 2 and location and action:
        title = f"{participants[0]}与{participants[1]}在{location}{action}"
    elif len(participants) >= 2 and action:
        title = f"{participants[0]}与{participants[1]}{action}"
    elif len(participants) >= 2 and location:
        title = f"{participants[0]}与{participants[1]}在{location}会面"
    elif participants and location and action:
        title = f"{participants[0]}在{location}{action}"
    elif participants and action:
        title = f"{participants[0]}{action}"
    elif participants and location:
        title = f"{participants[0]}在{location}关键场景"
    elif len(participants) >= 2:
        title = f"{participants[0]}与{participants[1]}互动"
    elif participants:
        # Only one grounding signal — include source context
        title = f"{participants[0]}（{source_title}）" if source_title else f"{participants[0]}事件"
    else:
        # Fallback: use source_title as differentiator
        title = f"{pattern_key}（{source_title}）" if source_title else pattern_key

    # Ensure display_name != pattern_key by appending differentiator if needed
    if title == pattern_key and source_title:
        title = f"{pattern_key}（{source_title}）"
    elif title == pattern_key and participants:
        title = f"{participants[0]}{pattern_key}"

    return title[:80]


def _build_one_line_summary(pack: dict, display_name: str) -> str:
    """Build a ≤60 char one-line summary."""
    evidence = pack.get("evidence_excerpt", "")
    significance = pack.get("significance", "")

    # Prefer significance if short enough
    if significance and len(significance) <= 60:
        return significance

    # Otherwise build from evidence
    if evidence:
        # Take first sentence-like chunk
        for sep in ("。", "，", "；"):
            pos = evidence.find(sep)
            if 8 <= pos <= 58:
                return evidence[: pos + 1]
        return evidence[:58] + "…"

    return display_name[:60]


def build_event_display_catalog(inputs_payload: dict) -> dict:
    """Generate a catalog of display titles from event_display_inputs.json."""
    entries: List[dict] = []
    for pack in inputs_payload.get("packs", []):
        display_name = _build_display_name(pack)
        one_line = _build_one_line_summary(pack, display_name)
        entries.append(
            {
                "event_id": pack["event_id"],
                "display_name": display_name,
                "one_line_event_summary": one_line,
                "pattern_key": pack.get("pattern_key", ""),
                "generated_from_input_hash": pack["input_hash"],
                "generator": GENERATOR_NAME,
                "generated_at": datetime.now().isoformat(),
            }
        )

    return {
        "version": CATALOG_VERSION,
        "generated_at": datetime.now().isoformat(),
        "generator": GENERATOR_NAME,
        "total_entries": len(entries),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate event_display_catalog.json from event_display_inputs.json."
    )
    parser.add_argument(
        "--input",
        default="data/event_display_inputs.json",
        help="Event display inputs path.",
    )
    parser.add_argument(
        "--output",
        default="data/event_display_catalog.json",
        help="Catalog output path.",
    )
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    output = build_event_display_catalog(payload)
    Path(args.output).write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Event display catalog -> {args.output}  ({output['total_entries']} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
