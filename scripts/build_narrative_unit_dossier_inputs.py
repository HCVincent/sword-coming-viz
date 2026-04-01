#!/usr/bin/env python3
"""Build narrative_unit_dossier_inputs.json – input packets for Gemini-based
narrative unit dossier generation.

Each packet aggregates:
  - boundary result (from narrative_unit_boundaries.json)
  - chapter synopses for the unit's chapters
  - key events from those chapters
  - writer insights references
  - event dossiers for source events (when available)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INPUTS_VERSION = "narrative-unit-dossier-inputs-v1"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _index_chapter_synopses(synopses: dict) -> Dict[int, dict]:
    """Index chapter synopses by unit_index."""
    result: Dict[int, dict] = {}
    for ch in synopses.get("chapters") or []:
        uid = ch.get("unit_index")
        if uid is not None:
            result[int(uid)] = ch
    return result


def _index_event_dossiers(dossiers: dict) -> Dict[str, dict]:
    """Index event dossiers by event_id."""
    result: Dict[str, dict] = {}
    for d in dossiers.get("dossiers") or []:
        eid = d.get("event_id", "")
        if eid:
            result[eid] = d
    return result


def _index_key_events(key_events_index: dict) -> Dict[int, List[dict]]:
    """Index key events by unit_index."""
    result: Dict[int, List[dict]] = {}
    for chapter in key_events_index.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        uid = chapter.get("unit_index")
        if uid is not None:
            result[int(uid)] = chapter.get("key_events") or []
    return result


def build_narrative_unit_dossier_inputs(
    *,
    boundaries: dict,
    chapter_synopses: dict,
    key_events_index: dict,
    writer_insights: dict,
    event_dossiers: dict,
) -> dict:
    """Build input packets for narrative unit dossier generation."""
    units = boundaries.get("units") or []
    synopsis_index = _index_chapter_synopses(chapter_synopses)
    dossier_index = _index_event_dossiers(event_dossiers)
    key_events_by_unit = _index_key_events(key_events_index)

    packets: List[dict] = []
    for unit in units:
        unit_id = unit.get("unit_id", "")
        source_indexes = unit.get("source_unit_indexes") or []

        # Gather chapter synopses
        unit_synopses: List[dict] = []
        for uid in source_indexes:
            syn = synopsis_index.get(uid)
            if syn:
                unit_synopses.append({
                    "unit_index": uid,
                    "unit_title": syn.get("unit_title", ""),
                    "synopsis": syn.get("synopsis", ""),
                    "narrative_function": syn.get("narrative_function", ""),
                    "key_developments": (syn.get("key_developments") or [])[:5],
                    "active_characters": syn.get("active_characters") or [],
                    "locations": syn.get("locations") or [],
                    "event_count": syn.get("event_count", 0),
                })

        # Gather key events for this unit's chapters
        unit_key_events: List[dict] = []
        seen_events: Set[str] = set()
        for uid in source_indexes:
            for ev in key_events_by_unit.get(uid, []):
                eid = ev.get("event_id", "")
                if eid and eid not in seen_events:
                    seen_events.add(eid)
                    unit_key_events.append({
                        "event_id": eid,
                        "event_name": ev.get("event_name") or ev.get("name", ""),
                        "importance_tier": ev.get("importance_tier", ""),
                    })

        # Gather event dossier summaries for source events
        source_eids = unit.get("source_event_ids") or []
        event_dossier_summaries: List[dict] = []
        for eid in source_eids:
            doss = dossier_index.get(eid)
            if doss:
                event_dossier_summaries.append({
                    "event_id": eid,
                    "identity_summary": doss.get("identity_summary", ""),
                    "display_summary": doss.get("display_summary", ""),
                    "story_function": doss.get("story_function", ""),
                })

        payload: dict = {
            "unit_id": unit_id,
            "unit_index": unit.get("unit_index"),
            "season_name": unit.get("season_name", ""),
            "start_unit_index": unit.get("start_unit_index"),
            "end_unit_index": unit.get("end_unit_index"),
            "source_unit_indexes": source_indexes,
            "chapter_titles": unit.get("chapter_titles") or [],
            "main_roles": unit.get("main_roles") or [],
            "main_locations": unit.get("main_locations") or [],
            "progress_start": unit.get("progress_start"),
            "progress_end": unit.get("progress_end"),
            "chapter_synopses": unit_synopses,
            "key_events": unit_key_events,
            "event_dossier_summaries": event_dossier_summaries,
            "source_event_ids": source_eids,
        }
        payload["input_hash"] = _hash_payload(payload)
        packets.append(payload)

    return {
        "version": INPUTS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": boundaries.get("book_id", ""),
        "total_units": len(packets),
        "units": packets,
    }


def build_narrative_unit_dossier_inputs_file(
    *,
    boundaries_path: Path,
    chapter_synopses_path: Path,
    key_events_index_path: Path,
    writer_insights_path: Path,
    event_dossiers_path: Path,
    output_path: Path,
) -> dict:
    boundaries = _load_json(boundaries_path)
    chapter_synopses = _load_json(chapter_synopses_path)
    key_events_index = _load_json(key_events_index_path)
    writer_insights = _load_json(writer_insights_path)
    event_dossiers = _load_json(event_dossiers_path)

    payload = build_narrative_unit_dossier_inputs(
        boundaries=boundaries,
        chapter_synopses=chapter_synopses,
        key_events_index=key_events_index,
        writer_insights=writer_insights,
        event_dossiers=event_dossiers,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build narrative_unit_dossier_inputs.json."
    )
    parser.add_argument("--boundaries", default="data/narrative_unit_boundaries.json")
    parser.add_argument("--chapter-synopses", default="data/chapter_synopses.json")
    parser.add_argument("--key-events-index", default="data/key_events_index.json")
    parser.add_argument("--writer-insights", default="data/writer_insights.json")
    parser.add_argument("--event-dossiers", default="data/event_dossiers.json")
    parser.add_argument("--output", default="data/narrative_unit_dossier_inputs.json")
    args = parser.parse_args()

    payload = build_narrative_unit_dossier_inputs_file(
        boundaries_path=Path(args.boundaries),
        chapter_synopses_path=Path(args.chapter_synopses),
        key_events_index_path=Path(args.key_events_index),
        writer_insights_path=Path(args.writer_insights),
        event_dossiers_path=Path(args.event_dossiers),
        output_path=Path(args.output),
    )
    print(
        f"Narrative unit dossier inputs: {payload['total_units']} units -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
