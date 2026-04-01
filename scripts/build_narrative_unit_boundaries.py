#!/usr/bin/env python3
"""Build narrative_unit_boundaries.json – deterministic chapter grouping into
narrative units.

Algorithm:
  1. Season boundaries are hard cuts (never merge across seasons).
  2. Each narrative unit spans 1–4 chapters.
  3. Adjacent chapters are merged when they share significant overlap in:
     - characters (Jaccard ≥ 0.3)
     - locations (Jaccard ≥ 0.2)
     - key event continuity (shared event IDs)
     - progress continuity (no gap)
  4. Merge is greedy forward: try to extend the current unit by one chapter;
     stop when overlap drops or unit reaches 4 chapters.

Output schema per unit:
  unit_id, start_unit_index, end_unit_index, source_unit_indexes,
  source_event_ids, boundary_reason, input_hash
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BOUNDARIES_VERSION = "narrative-unit-boundaries-v1"

# Merge thresholds
MAX_UNIT_SPAN = 4
MIN_ROLE_JACCARD = 0.3
MIN_LOCATION_JACCARD = 0.2
MIN_EVENT_OVERLAP = 1


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _should_merge(
    current_chapters: List[dict],
    candidate: dict,
) -> Tuple[bool, str]:
    """Decide whether *candidate* chapter should merge into the current group.

    Returns (should_merge, reason_if_not).
    """
    if len(current_chapters) >= MAX_UNIT_SPAN:
        return False, "max_span_reached"

    # Aggregate current group's roles, locations, events
    group_roles: Set[str] = set()
    group_locations: Set[str] = set()
    group_events: Set[str] = set()
    for ch in current_chapters:
        group_roles.update(ch.get("main_roles") or [])
        group_locations.update(ch.get("main_locations") or [])
        group_events.update(ch.get("top_key_event_ids") or [])

    cand_roles = set(candidate.get("main_roles") or [])
    cand_locations = set(candidate.get("main_locations") or [])
    cand_events = set(candidate.get("top_key_event_ids") or [])

    role_j = _jaccard(group_roles, cand_roles)
    loc_j = _jaccard(group_locations, cand_locations)
    event_overlap = len(group_events & cand_events)

    # Progress continuity: check gap
    last_progress_end = max(
        (ch.get("progress_end") or 0) for ch in current_chapters
    )
    cand_progress_start = candidate.get("progress_start") or 0
    progress_gap = cand_progress_start - last_progress_end if last_progress_end and cand_progress_start else 0

    # Score: count how many signals favour merging
    signals = 0
    if role_j >= MIN_ROLE_JACCARD:
        signals += 1
    if loc_j >= MIN_LOCATION_JACCARD:
        signals += 1
    if event_overlap >= MIN_EVENT_OVERLAP:
        signals += 1
    if progress_gap <= 1:
        signals += 1

    # Need at least 2 of 4 signals to merge
    if signals >= 2:
        return True, ""
    else:
        reasons = []
        if role_j < MIN_ROLE_JACCARD:
            reasons.append(f"role_jaccard={role_j:.2f}<{MIN_ROLE_JACCARD}")
        if loc_j < MIN_LOCATION_JACCARD:
            reasons.append(f"location_jaccard={loc_j:.2f}<{MIN_LOCATION_JACCARD}")
        if event_overlap < MIN_EVENT_OVERLAP:
            reasons.append(f"event_overlap={event_overlap}<{MIN_EVENT_OVERLAP}")
        if progress_gap > 1:
            reasons.append(f"progress_gap={progress_gap}")
        return False, "; ".join(reasons)


def _make_boundary_unit(
    chapters: List[dict],
    *,
    unit_index: int,
    boundary_reason: str,
) -> dict:
    """Build a single narrative unit boundary record from a group of chapter packets."""
    source_unit_indexes = sorted(ch["unit_index"] for ch in chapters)
    all_event_ids: List[str] = []
    seen_events: Set[str] = set()
    for ch in chapters:
        for eid in (ch.get("top_key_event_ids") or []):
            if eid not in seen_events:
                all_event_ids.append(eid)
                seen_events.add(eid)

    season_name = chapters[0].get("season_name", "")

    payload: dict = {
        "unit_id": f"nu_{source_unit_indexes[0]:03d}_{source_unit_indexes[-1]:03d}",
        "unit_index": unit_index,
        "season_name": season_name,
        "start_unit_index": source_unit_indexes[0],
        "end_unit_index": source_unit_indexes[-1],
        "source_unit_indexes": source_unit_indexes,
        "source_event_ids": all_event_ids,
        "chapter_titles": [ch.get("chapter_title", "") for ch in chapters],
        "main_roles": sorted(set(
            r for ch in chapters for r in (ch.get("main_roles") or [])
        )),
        "main_locations": sorted(set(
            loc for ch in chapters for loc in (ch.get("main_locations") or [])
        )),
        "progress_start": chapters[0].get("progress_start"),
        "progress_end": chapters[-1].get("progress_end"),
        "boundary_reason": boundary_reason,
    }
    payload["input_hash"] = _hash_payload(payload)
    return payload


def build_narrative_unit_boundaries(
    *,
    chapter_structure_inputs: dict,
) -> dict:
    """Build narrative unit boundaries from chapter structure inputs.

    Returns the full output payload.
    """
    chapters = chapter_structure_inputs.get("chapters") or []
    if not chapters:
        return {
            "version": BOUNDARIES_VERSION,
            "generated_at": datetime.now().isoformat(),
            "book_id": chapter_structure_inputs.get("book_id", ""),
            "total_units": 0,
            "units": [],
        }

    # Group by season first (hard boundary)
    seasons: Dict[str, List[dict]] = {}
    season_order: List[str] = []
    for ch in chapters:
        sn = ch.get("season_name", "")
        if sn not in seasons:
            seasons[sn] = []
            season_order.append(sn)
        seasons[sn].append(ch)

    all_units: List[dict] = []
    unit_counter = 0

    for season_name in season_order:
        season_chapters = seasons[season_name]
        # Sort by unit_index within season
        season_chapters.sort(key=lambda c: c["unit_index"])

        # Greedy forward merge
        current_group: List[dict] = [season_chapters[0]]
        pending_reason = "season_start"

        for ch in season_chapters[1:]:
            should_merge, reason = _should_merge(current_group, ch)
            if should_merge:
                current_group.append(ch)
            else:
                # Emit current group
                unit_counter += 1
                all_units.append(_make_boundary_unit(
                    current_group,
                    unit_index=unit_counter,
                    boundary_reason=pending_reason,
                ))
                current_group = [ch]
                pending_reason = reason or "low_overlap"

        # Emit trailing group
        if current_group:
            unit_counter += 1
            all_units.append(_make_boundary_unit(
                current_group,
                unit_index=unit_counter,
                boundary_reason=pending_reason,
            ))

    return {
        "version": BOUNDARIES_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": chapter_structure_inputs.get("book_id", ""),
        "total_units": len(all_units),
        "units": all_units,
    }


def validate_boundaries(payload: dict) -> List[str]:
    """Validate narrative unit boundaries for correctness.

    Returns a list of error messages (empty = valid).
    """
    errors: List[str] = []
    units = payload.get("units") or []

    if not units:
        return errors

    all_covered: Set[int] = set()
    prev_end: Optional[int] = None
    prev_season: Optional[str] = None

    for u in units:
        uid = u.get("unit_id", "?")
        source = u.get("source_unit_indexes") or []
        season = u.get("season_name", "")

        # Check span 1-4
        if len(source) < 1 or len(source) > MAX_UNIT_SPAN:
            errors.append(f"{uid}: span {len(source)} outside [1, {MAX_UNIT_SPAN}]")

        # Check no cross-season
        if prev_season is not None and prev_season != season:
            # This is a season boundary — OK
            pass

        # Check no overlap
        for idx in source:
            if idx in all_covered:
                errors.append(f"{uid}: unit_index {idx} already covered (overlap)")
            all_covered.add(idx)

        # Check no gap within same season
        start = u.get("start_unit_index")
        if prev_end is not None and prev_season == season and start is not None:
            if start != prev_end + 1:
                errors.append(f"{uid}: gap between {prev_end} and {start}")

        prev_end = u.get("end_unit_index")
        prev_season = season

    return errors


def build_narrative_unit_boundaries_file(
    *,
    chapter_structure_inputs_path: Path,
    output_path: Path,
) -> dict:
    chapter_structure_inputs = _load_json(chapter_structure_inputs_path)
    payload = build_narrative_unit_boundaries(
        chapter_structure_inputs=chapter_structure_inputs,
    )

    errors = validate_boundaries(payload)
    if errors:
        for e in errors:
            print(f"VALIDATION ERROR: {e}")
        raise ValueError(
            f"Narrative unit boundaries have {len(errors)} validation errors. See above."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build narrative_unit_boundaries.json – deterministic chapter grouping."
    )
    parser.add_argument("--input", default="data/chapter_structure_inputs.json")
    parser.add_argument("--output", default="data/narrative_unit_boundaries.json")
    args = parser.parse_args()

    payload = build_narrative_unit_boundaries_file(
        chapter_structure_inputs_path=Path(args.input),
        output_path=Path(args.output),
    )
    print(
        f"Narrative unit boundaries: {payload['total_units']} units -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
