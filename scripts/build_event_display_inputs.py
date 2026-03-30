#!/usr/bin/env python3
"""
Build event_display_inputs.json — per-event input packs used by the local
agent to generate grounded display titles for recurring-pattern events.

Events whose ``pattern_key`` appears only once in the whole book are
*unique* and keep ``display_name == name`` without needing a catalog entry.
Only events with ``name_occurrence_count > 1`` get an input pack here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.unified import UnifiedEvent, UnifiedKnowledgeBase


INPUTS_VERSION = "event-display-inputs-v1"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_kb(path: Path) -> UnifiedKnowledgeBase:
    return UnifiedKnowledgeBase(**load_json(path))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _progress_label_for_event(event: UnifiedEvent) -> str:
    """Return a human-readable progress label or fall back to source units."""
    if event.progress_label:
        return event.progress_label
    units = sorted(event.source_units or event.source_juans)
    if units:
        return f"章节 {units[0]}"
    return ""


def build_event_display_inputs(
    *,
    kb: UnifiedKnowledgeBase,
) -> dict:
    """Build input packs for events that share a recurring pattern_key.

    Returns a dict ready to be serialised as ``event_display_inputs.json``.
    """
    # Identify recurring pattern_keys (name_occurrence_count > 1)
    pattern_counts: Dict[str, int] = {}
    for event in kb.events.values():
        pk = event.pattern_key or event.name
        pattern_counts[pk] = pattern_counts.get(pk, 0) + 1

    recurring_keys = {pk for pk, count in pattern_counts.items() if count > 1}

    packs: List[dict] = []
    for event in sorted(kb.events.values(), key=lambda e: (e.name, e.id)):
        pk = event.pattern_key or event.name
        if pk not in recurring_keys:
            continue

        source_units = sorted(event.source_units or event.source_juans)
        # Determine a representative source_unit_title from the progress label
        progress_label = _progress_label_for_event(event)

        payload: dict = {
            "event_id": event.id,
            "pattern_key": pk,
            "participants": sorted(event.participants),
            "location": event.location,
            "source_unit_title": progress_label,
            "progress_label": progress_label,
            "evidence_excerpt": (event.evidence_excerpt or event.description or "")[:200],
            "significance": event.significance or "",
            "source_units": source_units,
            "grounding_excerpt_ids": sorted(
                f"{seg}"
                for seg in (event.source_segments or [])
            )[:4],
        }
        payload["input_hash"] = _hash_payload(payload)
        packs.append(payload)

    return {
        "version": INPUTS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "total_recurring_patterns": len(recurring_keys),
        "total_event_packs": len(packs),
        "packs": packs,
    }


def build_event_display_inputs_file(
    *,
    kb_input_path: Path,
    output_path: Path,
) -> dict:
    kb = load_kb(kb_input_path)
    payload = build_event_display_inputs(kb=kb)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Event display inputs -> {output_path}  ({payload['total_event_packs']} packs for {payload['total_recurring_patterns']} patterns)")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build event_display_inputs.json for recurring-pattern events."
    )
    parser.add_argument(
        "--kb-input",
        default="data/unified_knowledge.json",
        help="Unified knowledge JSON path.",
    )
    parser.add_argument(
        "--output",
        default="data/event_display_inputs.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()
    build_event_display_inputs_file(
        kb_input_path=Path(args.kb_input),
        output_path=Path(args.output),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
