#!/usr/bin/env python3
"""Validate narrative_units.json quality and metadata contracts."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List


FIELD_LENGTH_RANGES = {
    "title": (2, 16),
    "display_summary": (80, 320),
    "long_summary": (220, 1200),
    "dramatic_function": (30, 220),
    "what_changes": (40, 280),
    "stakes": (16, 160),
}

LEGACY_TEMPLATE_MARKERS = (
    "这一剧情单元讲述了",
    "在这几章中",
    "从叙事角度看",
    "这段剧情主要讲述",
    "该单元主要围绕",
)

GENERIC_FUNCTION_MARKERS = (
    "推动剧情发展",
    "承上启下",
    "起到承接作用",
    "推动后续发展",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _index_inputs(inputs_payload: dict) -> Dict[str, dict]:
    return {
        str(item.get("unit_id", "")).strip(): item
        for item in inputs_payload.get("units", [])
        if str(item.get("unit_id", "")).strip()
    }


def _looks_like_event_list(summary: str, source_input: dict) -> bool:
    normalized = _normalize_text(summary)
    if not normalized:
        return False
    key_events = source_input.get("key_events") or []
    hit_count = 0
    for item in key_events:
        event_name = _normalize_text(item.get("event_name", ""))
        if event_name and event_name in normalized:
            hit_count += 1
    if hit_count >= 3:
        return True
    separators = summary.count("；") + summary.count(";") + summary.count("、")
    return separators >= 6


def _too_similar(display_summary: str, long_summary: str) -> bool:
    display_norm = _normalize_text(display_summary)
    long_norm = _normalize_text(long_summary)
    if not display_norm or not long_norm:
        return False
    if display_norm == long_norm:
        return True
    shorter, longer = sorted((display_norm, long_norm), key=len)
    if len(shorter) >= 60 and longer.startswith(shorter):
        return True
    ratio = SequenceMatcher(a=display_norm, b=long_norm).ratio()
    return ratio >= 0.92


def validate_narrative_units(*, inputs_payload: dict, units_payload: dict) -> List[str]:
    problems: List[str] = []
    input_index = _index_inputs(inputs_payload)
    starts: Counter[str] = Counter()

    for unit in units_payload.get("units", []):
        unit_id = str(unit.get("unit_id", "")).strip()
        if not unit_id:
            problems.append("unit missing unit_id")
            continue

        source_input = input_index.get(unit_id)
        if not source_input:
            problems.append(f"{unit_id} missing matching input packet")
            continue

        if str(unit.get("generator", "")).strip() != "gemini-api":
            problems.append(f"{unit_id} generator must be gemini-api")
        if not str(unit.get("model", "")).strip():
            problems.append(f"{unit_id} model must not be empty")

        expected_hash = str(source_input.get("input_hash", "")).strip()
        actual_hash = str(unit.get("generated_from_input_hash", "")).strip()
        if expected_hash and actual_hash != expected_hash:
            problems.append(f"{unit_id} generated_from_input_hash mismatch")

        for field_name, (lo, hi) in FIELD_LENGTH_RANGES.items():
            text = _normalize_text(unit.get(field_name, ""))
            length = len(text)
            if not length:
                problems.append(f"{unit_id} {field_name} must not be empty")
                continue
            if length < lo or length > hi:
                problems.append(
                    f"{unit_id} {field_name} length {length} outside range [{lo}, {hi}]"
                )

        title = str(unit.get("title", "")).strip()
        chapter_titles = [
            str(item).strip()
            for item in (source_input.get("chapter_titles") or [])
            if str(item).strip()
        ]
        if any(_normalize_text(title) == _normalize_text(ch_title) for ch_title in chapter_titles):
            problems.append(f"{unit_id} title reuses a chapter title verbatim")

        display_summary = str(unit.get("display_summary", "")).strip()
        long_summary = str(unit.get("long_summary", "")).strip()
        dramatic_function = str(unit.get("dramatic_function", "")).strip()
        what_changes = str(unit.get("what_changes", "")).strip()
        stakes = str(unit.get("stakes", "")).strip()

        for marker in LEGACY_TEMPLATE_MARKERS:
            if marker in display_summary or marker in long_summary:
                problems.append(f"{unit_id} hit legacy/template marker: {marker}")

        if _looks_like_event_list(display_summary, source_input):
            problems.append(f"{unit_id} display_summary looks like an event list")

        if _too_similar(display_summary, long_summary):
            problems.append(f"{unit_id} display_summary and long_summary are too similar")

        for marker in GENERIC_FUNCTION_MARKERS:
            if dramatic_function == marker:
                problems.append(f"{unit_id} dramatic_function too generic: {marker}")

        for field_name, text in (
            ("dramatic_function", dramatic_function),
            ("what_changes", what_changes),
            ("stakes", stakes),
        ):
            if "待补" in text or "暂无" in text:
                problems.append(f"{unit_id} {field_name} contains placeholder wording")

        anchor = _normalize_text(long_summary)[:24]
        if anchor:
            starts[anchor] += 1

    for anchor, count in starts.items():
        if count >= 5:
            problems.append(f"batch-homogeneous opening detected: {anchor} ({count} units)")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate narrative_units.json quality and metadata contracts.")
    parser.add_argument("--inputs", default="data/narrative_unit_dossier_inputs.json", help="Input packet file")
    parser.add_argument("--units", default="data/narrative_units.json", help="Generated narrative units file")
    args = parser.parse_args()

    inputs_payload = _load_json(Path(args.inputs))
    units_payload = _load_json(Path(args.units))
    problems = validate_narrative_units(inputs_payload=inputs_payload, units_payload=units_payload)

    if problems:
        print("Narrative units validation failed:")
        for item in problems[:100]:
            print(f"- {item}")
        if len(problems) > 100:
            print(f"... and {len(problems) - 100} more")
        return 1

    print("Narrative units validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
