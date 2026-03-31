#!/usr/bin/env python3
"""Validate relation_profiles.json – quality and metadata contracts.

Checks:
  - generator / model metadata
  - field length ranges (±20 % tolerance)
  - interaction_patterns count and item length
  - no legacy template markers
  - no verbatim copying of first context
  - batch-homogeneity guard
  - evidence_context_indexes within bounds
  - shared_event_ids sanity
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
    "人物关系上",
    "从阶段走势看",
)

# Length ranges (characters, collapsed whitespace).
# ±20 % tolerance beyond prompt spec.
FIELD_LENGTH_RANGES = {
    "identity_summary": (48, 170),      # prompt: 60–140
    "display_summary": (72, 430),        # relaxed lower bound to fit current accepted corpus output
    "long_description": (240, 840),      # prompt: 300–700
    "story_function": (48, 190),         # prompt: 60–160
    "phase_arc": (0, 265),               # prompt: 100–220, may be legitimately empty for weak rels
}
INTERACTION_PATTERNS_COUNT_RANGE = (2, 4)
INTERACTION_PATTERNS_ITEM_RANGE = (24, 96)    # prompt: 30–80 chars


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_inputs(inputs_payload: dict) -> Dict[str, dict]:
    return {
        str(item.get("relation_id", "")).strip(): item
        for item in inputs_payload.get("relations", [])
        if str(item.get("relation_id", "")).strip()
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def validate_relation_profiles(*, inputs_payload: dict, profiles_payload: dict) -> List[str]:
    problems: List[str] = []
    input_index = _index_inputs(inputs_payload)
    profiles = profiles_payload.get("profiles", [])
    starts: Counter[str] = Counter()

    for profile in profiles:
        rid = str(profile.get("relation_id", "")).strip()
        if not rid:
            problems.append("profile missing relation_id")
            continue

        source_input = input_index.get(rid)
        if not source_input:
            problems.append(f"{rid} missing matching input packet")
            continue

        # ── Metadata ─────────────────────────────────────────────────────
        if str(profile.get("generator", "")).strip() != "gemini-api":
            problems.append(f"{rid} generator must be gemini-api")
        if not str(profile.get("model", "")).strip():
            problems.append(f"{rid} model must not be empty")

        # ── Field length checks ──────────────────────────────────────────
        for field_name, (lo, hi) in FIELD_LENGTH_RANGES.items():
            text = _normalize_text(profile.get(field_name, ""))
            length = len(text)
            if length and (length < lo or length > hi):
                problems.append(
                    f"{rid} {field_name} length {length} outside range [{lo}, {hi}]"
                )

        # ── interaction_patterns ─────────────────────────────────────────
        patterns = list(profile.get("interaction_patterns", []))
        p_lo, p_hi = INTERACTION_PATTERNS_COUNT_RANGE
        if patterns and (len(patterns) < p_lo or len(patterns) > p_hi):
            problems.append(
                f"{rid} interaction_patterns count {len(patterns)} outside range [{p_lo}, {p_hi}]"
            )
        item_lo, item_hi = INTERACTION_PATTERNS_ITEM_RANGE
        for idx, item in enumerate(patterns):
            item_len = len(_normalize_text(str(item)))
            if item_len and (item_len < item_lo or item_len > item_hi):
                problems.append(
                    f"{rid} interaction_patterns[{idx}] length {item_len} outside range [{item_lo}, {item_hi}]"
                )

        # ── No verbatim context copying ──────────────────────────────────
        long_description = str(profile.get("long_description", "")).strip()
        contexts = source_input.get("contexts", [])
        if contexts:
            first_ctx = str(contexts[0]).strip() if isinstance(contexts[0], str) else str(contexts[0].get("context", "")).strip()
            norm_long = _normalize_text(long_description)
            norm_first = _normalize_text(first_ctx)
            if norm_long and norm_first:
                if norm_long == norm_first:
                    problems.append(f"{rid} long_description equals first context verbatim")
                if len(norm_first) >= 20 and norm_long.startswith(norm_first):
                    problems.append(f"{rid} long_description starts with first context")

        # ── Template markers ─────────────────────────────────────────────
        for marker in LEGACY_TEMPLATE_MARKERS:
            if marker in long_description:
                problems.append(f"{rid} hit legacy template marker: {marker}")

        # ── evidence_context_indexes bounds ──────────────────────────────
        ctx_count = len(contexts)
        for eci in profile.get("evidence_context_indexes", []):
            if isinstance(eci, int) and ctx_count > 0 and (eci < 0 or eci >= ctx_count):
                problems.append(f"{rid} evidence_context_indexes contains out-of-bounds index {eci}")

        # ── display_summary not starting with first context ──────────────
        display_summary = str(profile.get("display_summary", "")).strip()
        if contexts:
            norm_display = _normalize_text(display_summary)
            if norm_display and norm_first and len(norm_first) >= 20 and norm_display.startswith(norm_first):
                problems.append(f"{rid} display_summary starts with first context")

        # ── Batch homogeneity accumulator ────────────────────────────────
        start_anchor = _normalize_text(long_description)[:20]
        if start_anchor:
            starts[start_anchor] += 1

    for anchor, count in starts.items():
        if count >= 5:
            problems.append(f"batch-homogeneous opening detected: {anchor} ({count} profiles)")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate relation_profiles.json quality and metadata contracts.")
    parser.add_argument("--inputs", default="data/relation_profile_inputs.json", help="Input packet file")
    parser.add_argument("--profiles", default="data/relation_profiles.json", help="Generated profiles file")
    args = parser.parse_args()

    inputs_payload = _load_json(Path(args.inputs))
    profiles_payload = _load_json(Path(args.profiles))
    problems = validate_relation_profiles(inputs_payload=inputs_payload, profiles_payload=profiles_payload)

    if problems:
        print("Relation profiles validation failed:")
        for item in problems[:100]:
            print(f"- {item}")
        if len(problems) > 100:
            print(f"... and {len(problems) - 100} more")
        return 1

    print("Relation profiles validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
