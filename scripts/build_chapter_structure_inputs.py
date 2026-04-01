#!/usr/bin/env python3
"""Build chapter_structure_inputs.json – per-chapter metadata packets for
narrative unit boundary computation.

Each chapter packet includes:
  unit_index, season_name, chapter_title, chapter_synopsis,
  main_roles, main_locations, top_key_event_ids, progress_range

This is a pure aggregation step (no LLM) that combines:
  - chapter_synopses.json
  - unit_progress_index.json
  - key_events_index.json
  - writer_insights.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INPUTS_VERSION = "chapter-structure-inputs-v1"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _collect_writer_event_ids_by_unit(writer_insights: dict) -> Dict[int, Set[str]]:
    """Map unit_index -> set of event_ids referenced by writer_insights."""
    unit_events: Dict[int, Set[str]] = {}

    def _add(eid: str, units: list[int]) -> None:
        for u in units:
            unit_events.setdefault(u, set()).add(eid)

    for overview in writer_insights.get("season_overviews") or []:
        if not isinstance(overview, dict):
            continue
        for beat in overview.get("story_beats") or []:
            if not isinstance(beat, dict):
                continue
            event = beat.get("event") or {}
            eid = event.get("event_id", "")
            if eid:
                units = event.get("source_units") or []
                _add(eid, units)
        for event in overview.get("anchor_events") or []:
            if not isinstance(event, dict):
                continue
            eid = event.get("event_id", "")
            if eid:
                _add(eid, event.get("source_units") or [])

    for arc in writer_insights.get("character_arcs") or []:
        if not isinstance(arc, dict):
            continue
        for event in arc.get("key_events") or []:
            if not isinstance(event, dict):
                continue
            eid = event.get("event_id", "")
            if eid:
                _add(eid, event.get("source_units") or [])

    return unit_events


def _collect_key_event_ids_by_unit(key_events_index: dict) -> Dict[int, List[str]]:
    """Map unit_index -> ordered list of key event_ids from key_events_index."""
    result: Dict[int, List[str]] = {}
    for chapter in key_events_index.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        uid = chapter.get("unit_index")
        if uid is None:
            continue
        eids: List[str] = []
        for event in chapter.get("key_events") or []:
            if not isinstance(event, dict):
                continue
            eid = event.get("event_id", "")
            if eid:
                eids.append(eid)
        result[int(uid)] = eids
    return result


def build_chapter_structure_inputs(
    *,
    chapter_synopses: dict,
    unit_progress_index: dict,
    key_events_index: dict,
    writer_insights: dict,
) -> dict:
    """Build per-chapter packets for narrative unit boundary computation."""
    chapters_raw = chapter_synopses.get("chapters") or []

    unit_meta: Dict[int, dict] = {}
    for uid_str, meta in (unit_progress_index.get("units") or {}).items():
        unit_meta[int(uid_str)] = meta

    key_events_by_unit = _collect_key_event_ids_by_unit(key_events_index)
    writer_events_by_unit = _collect_writer_event_ids_by_unit(writer_insights)

    packets: List[dict] = []
    for ch in chapters_raw:
        uid = ch.get("unit_index")
        if uid is None:
            continue
        uid = int(uid)
        meta = unit_meta.get(uid, {})

        main_roles = ch.get("active_characters") or []
        main_locations = ch.get("locations") or []

        # Top key event IDs: combine key_events_index + writer_insights refs
        key_eids = key_events_by_unit.get(uid, [])
        writer_eids = sorted(writer_events_by_unit.get(uid, set()))
        # Merge: key_events first, then writer-only events
        seen: Set[str] = set()
        merged_eids: List[str] = []
        for eid in key_eids:
            if eid not in seen:
                merged_eids.append(eid)
                seen.add(eid)
        for eid in writer_eids:
            if eid not in seen:
                merged_eids.append(eid)
                seen.add(eid)

        payload: dict = {
            "unit_index": uid,
            "season_name": meta.get("season_name", ch.get("season_name", "")),
            "chapter_title": meta.get("unit_title", ch.get("unit_title", "")),
            "chapter_synopsis": ch.get("synopsis", ""),
            "narrative_function": ch.get("narrative_function", ""),
            "main_roles": main_roles,
            "main_locations": main_locations,
            "top_key_event_ids": merged_eids,
            "progress_start": meta.get("progress_start"),
            "progress_end": meta.get("progress_end"),
            "event_count": ch.get("event_count", 0),
        }
        payload["input_hash"] = _hash_payload(payload)
        packets.append(payload)

    # Sort by unit_index for determinism
    packets.sort(key=lambda p: p["unit_index"])

    return {
        "version": INPUTS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": chapter_synopses.get("book_id", ""),
        "total_chapters": len(packets),
        "chapters": packets,
    }


def build_chapter_structure_inputs_file(
    *,
    chapter_synopses_path: Path,
    unit_progress_index_path: Path,
    key_events_index_path: Path,
    writer_insights_path: Path,
    output_path: Path,
) -> dict:
    chapter_synopses = _load_json(chapter_synopses_path)
    unit_progress_index = _load_json(unit_progress_index_path)
    key_events_index = _load_json(key_events_index_path)
    writer_insights = _load_json(writer_insights_path)

    payload = build_chapter_structure_inputs(
        chapter_synopses=chapter_synopses,
        unit_progress_index=unit_progress_index,
        key_events_index=key_events_index,
        writer_insights=writer_insights,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build chapter_structure_inputs.json – per-chapter packets for narrative unit boundaries."
    )
    parser.add_argument("--chapter-synopses", default="data/chapter_synopses.json")
    parser.add_argument("--unit-progress-index", default="data/unit_progress_index.json")
    parser.add_argument("--key-events-index", default="data/key_events_index.json")
    parser.add_argument("--writer-insights", default="data/writer_insights.json")
    parser.add_argument("--output", default="data/chapter_structure_inputs.json")
    args = parser.parse_args()

    payload = build_chapter_structure_inputs_file(
        chapter_synopses_path=Path(args.chapter_synopses),
        unit_progress_index_path=Path(args.unit_progress_index),
        key_events_index_path=Path(args.key_events_index),
        writer_insights_path=Path(args.writer_insights),
        output_path=Path(args.output),
    )
    print(
        f"Chapter structure inputs: {payload['total_chapters']} chapters -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
