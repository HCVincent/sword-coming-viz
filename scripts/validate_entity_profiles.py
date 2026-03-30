#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


LEGACY_TEMPLATE_MARKERS = (
    "在现有三季材料里",
    "人物关系上",
    "从阶段走势看",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_inputs(inputs_payload: dict) -> Dict[Tuple[str, str], dict]:
    index: Dict[Tuple[str, str], dict] = {}
    for plural in ("roles", "locations"):
        singular = plural[:-1]
        for item in inputs_payload.get(plural, []):
            entity_id = str(item.get("entity_id", "")).strip()
            if entity_id:
                index[(singular, entity_id)] = item
    return index


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _titles_majority_ratio(text: str, titles: Iterable[str]) -> float:
    normalized = _normalize_text(text)
    if not normalized:
        return 0.0
    total = len(normalized)
    matched = 0
    for title in titles:
        t = _normalize_text(title)
        if not t:
            continue
        occurrences = normalized.count(t)
        matched += occurrences * len(t)
    return matched / total if total else 0.0


def validate_entity_profiles(*, inputs_payload: dict, profiles_payload: dict) -> List[str]:
    problems: List[str] = []
    input_index = _index_inputs(inputs_payload)
    profiles = profiles_payload.get("profiles", [])
    starts = Counter()

    for profile in profiles:
        entity_type = str(profile.get("entity_type", "")).strip()
        entity_id = str(profile.get("entity_id", "")).strip()
        key = (entity_type, entity_id)
        if not entity_type or not entity_id:
            problems.append("profile missing entity_type/entity_id")
            continue

        source_input = input_index.get(key)
        if not source_input:
            problems.append(f"{entity_type}:{entity_id} missing matching input packet")
            continue

        model_name = str(profile.get("model", "")).strip()
        if str(profile.get("generator", "")).strip() != "gemini-api":
            problems.append(f"{entity_type}:{entity_id} generator must be gemini-api")
        if not model_name:
            problems.append(f"{entity_type}:{entity_id} model must not be empty")

        long_description = str(profile.get("long_description", "")).strip()
        original_descriptions = source_input.get("original_descriptions", [])
        first_original = str(original_descriptions[0]).strip() if original_descriptions else ""
        if first_original:
            norm_long = _normalize_text(long_description)
            norm_first = _normalize_text(first_original)
            if norm_long and norm_long == norm_first:
                problems.append(f"{entity_type}:{entity_id} long_description equals original_descriptions[0]")
            if norm_long and norm_first and norm_long.startswith(norm_first):
                problems.append(f"{entity_type}:{entity_id} long_description starts with original_descriptions[0]")

        for marker in LEGACY_TEMPLATE_MARKERS:
            if marker in long_description:
                problems.append(f"{entity_type}:{entity_id} hit legacy template marker: {marker}")

        turning_titles = [
            str(item.get("display_name") or item.get("name") or "").strip()
            for item in source_input.get("turning_point_candidates", [])
            if str(item.get("display_name") or item.get("name") or "").strip()
        ]
        if turning_titles:
            counts = Counter(turning_titles)
            duplicates = [title for title, count in counts.items() if count > 1]
            if duplicates:
                problems.append(f"{entity_type}:{entity_id} duplicate turning point titles in input: {duplicates[:3]}")

            ratio = _titles_majority_ratio(long_description, turning_titles)
            if ratio >= 0.5:
                problems.append(f"{entity_type}:{entity_id} long_description is dominated by turning point titles")

        display_summary = str(profile.get("display_summary", "")).strip()
        if first_original:
            norm_display = _normalize_text(display_summary)
            norm_first = _normalize_text(first_original)
            if norm_display and norm_first and norm_display.startswith(norm_first):
                problems.append(f"{entity_type}:{entity_id} display_summary starts with original_descriptions[0]")

        start_anchor = _normalize_text(long_description)[:20]
        if start_anchor:
            starts[start_anchor] += 1

    for anchor, count in starts.items():
        if count >= 5:
            problems.append(f"batch-homogeneous opening detected: {anchor} ({count} profiles)")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate entity_profiles.json quality and metadata contracts.")
    parser.add_argument("--inputs", default="data/entity_profile_inputs.json", help="Input packet file")
    parser.add_argument("--profiles", default="data/entity_profiles.json", help="Generated profiles file")
    args = parser.parse_args()

    inputs_payload = _load_json(Path(args.inputs))
    profiles_payload = _load_json(Path(args.profiles))
    problems = validate_entity_profiles(inputs_payload=inputs_payload, profiles_payload=profiles_payload)

    if problems:
        print("Entity profiles validation failed:")
        for item in problems[:100]:
            print(f"- {item}")
        if len(problems) > 100:
            print(f"... and {len(problems) - 100} more")
        return 1

    print("Entity profiles validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
