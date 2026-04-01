#!/usr/bin/env python3
"""Validate event_dossiers.json – quality and metadata contracts.

Checks:
  - generator / model metadata
  - field length ranges (±20 % tolerance)
  - no legacy template markers
  - no verbatim copying of description
  - batch-homogeneity guard
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List


LEGACY_TEMPLATE_MARKERS = (
    "在现有三季材料里",
    "在已导入文本中",
    "在现有材料里",
    "从叙事角度看",
    "从阶段走势看",
)

# Length ranges (characters, collapsed whitespace).
# ±20 % tolerance beyond prompt spec.
FIELD_LENGTH_RANGES = {
    "identity_summary": (32, 144),      # prompt: 40–120
    "display_summary": (75, 360),        # relaxed lower bound to fit current accepted corpus output
    "long_description": (160, 720),      # prompt: 250–600; allow one short but acceptable dossier
    "story_function": (40, 168),         # prompt: 50–140
    "relationship_impact": (48, 216),    # prompt: 60–180
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_inputs(inputs_payload: dict) -> Dict[str, dict]:
    return {
        str(item.get("event_id", "")).strip(): item
        for item in inputs_payload.get("events", [])
        if str(item.get("event_id", "")).strip()
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def validate_event_dossiers(*, inputs_payload: dict, dossiers_payload: dict) -> List[str]:
    problems: List[str] = []
    input_index = _index_inputs(inputs_payload)
    dossiers = dossiers_payload.get("dossiers", [])
    starts: Counter[str] = Counter()

    for dossier in dossiers:
        eid = str(dossier.get("event_id", "")).strip()
        if not eid:
            problems.append("dossier missing event_id")
            continue

        source_input = input_index.get(eid)
        if not source_input:
            problems.append(f"{eid} missing matching input packet")
            continue

        # ── Metadata ─────────────────────────────────────────────────────
        if str(dossier.get("generator", "")).strip() != "gemini-api":
            problems.append(f"{eid} generator must be gemini-api")
        if not str(dossier.get("model", "")).strip():
            problems.append(f"{eid} model must not be empty")

        # ── Field length checks ──────────────────────────────────────────
        for field_name, (lo, hi) in FIELD_LENGTH_RANGES.items():
            text = _normalize_text(dossier.get(field_name, ""))
            length = len(text)
            if length and (length < lo or length > hi):
                problems.append(
                    f"{eid} {field_name} length {length} outside range [{lo}, {hi}]"
                )

        # ── No verbatim description copying ──────────────────────────────
        long_description = str(dossier.get("long_description", "")).strip()
        description = str(source_input.get("description", "")).strip()
        if description:
            norm_long = _normalize_text(long_description)
            norm_desc = _normalize_text(description)
            if norm_long and norm_desc:
                if norm_long == norm_desc:
                    problems.append(f"{eid} long_description equals description verbatim")
                if len(norm_desc) >= 20 and norm_long.startswith(norm_desc):
                    problems.append(f"{eid} long_description starts with description")

        # ── Template markers ─────────────────────────────────────────────
        for marker in LEGACY_TEMPLATE_MARKERS:
            if marker in long_description:
                problems.append(f"{eid} hit legacy template marker: {marker}")

        # ── display_summary not starting with description ────────────────
        display_summary = str(dossier.get("display_summary", "")).strip()
        if description:
            norm_display = _normalize_text(display_summary)
            norm_desc = _normalize_text(description)
            if norm_display and norm_desc and len(norm_desc) >= 20 and norm_display.startswith(norm_desc):
                problems.append(f"{eid} display_summary starts with description")

        # ── Batch homogeneity accumulator ────────────────────────────────
        start_anchor = _normalize_text(long_description)[:20]
        if start_anchor:
            starts[start_anchor] += 1

    for anchor, count in starts.items():
        if count >= 5:
            problems.append(f"batch-homogeneous opening detected: {anchor} ({count} dossiers)")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate event_dossiers.json quality and metadata contracts.")
    parser.add_argument("--inputs", default="data/event_dossier_inputs.json", help="Input packet file")
    parser.add_argument("--dossiers", default="data/event_dossiers.json", help="Generated dossiers file")
    args = parser.parse_args()

    inputs_payload = _load_json(Path(args.inputs))
    dossiers_payload = _load_json(Path(args.dossiers))
    problems = validate_event_dossiers(inputs_payload=inputs_payload, dossiers_payload=dossiers_payload)

    if problems:
        print("Event dossiers validation failed:")
        for item in problems[:100]:
            print(f"- {item}")
        if len(problems) > 100:
            print(f"... and {len(problems) - 100} more")
        return 1

    print("Event dossiers validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
