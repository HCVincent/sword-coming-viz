#!/usr/bin/env python3
"""Build relation_profile_inputs.json from unified_knowledge.json.

Each of the 496 relations gets an input packet suitable for Gemini dossier
generation.  The packet includes the core relation fields plus three derived
helper fields (action_type_counts, contexts_by_phase, shared_event_refs) that
give the LLM structured material for the *interaction_patterns* field.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.unified import UnifiedEvent, UnifiedKnowledgeBase

INPUTS_VERSION = "relation-profile-inputs-v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bucket_name(position: int, total: int) -> str:
    if total <= 1:
        return "early"
    ratio = position / max(total - 1, 1)
    if ratio < 1 / 3:
        return "early"
    if ratio < 2 / 3:
        return "middle"
    return "late"


def _event_display_name(event: UnifiedEvent) -> str:
    return (event.display_name or event.name or "").strip()


def _event_units(event: UnifiedEvent) -> List[int]:
    return sorted(event.source_units or event.source_juans)


# ---------------------------------------------------------------------------
# Shared event selection
# ---------------------------------------------------------------------------

def _find_shared_events(
    source_name: str,
    target_name: str,
    events: Sequence[UnifiedEvent],
    *,
    limit: int = 6,
) -> List[dict]:
    """Select up to *limit* high-value events that involve both entities,
    spread across early / middle / late phases."""

    shared: List[UnifiedEvent] = []
    for event in events:
        if source_name in event.participants and target_name in event.participants:
            shared.append(event)

    if not shared:
        return []

    shared.sort(key=lambda e: (_event_units(e)[0] if _event_units(e) else 10**12, e.id))
    all_units = sorted({u for e in shared for u in _event_units(e)})

    # Score each event
    scored: List[Tuple[int, str, UnifiedEvent]] = []
    for event in shared:
        score = 0
        score += 3 if event.significance else 0
        score += 2 if event.title_source == "catalog" else 0
        score += 1 if event.location else 0
        score += min(len(event.participants), 3)
        scored.append((score, event.id, event))

    scored.sort(key=lambda t: (-t[0], t[1]))

    # Greedy pick with phase coverage
    chosen: List[dict] = []
    phase_counts: Dict[str, int] = {"early": 0, "middle": 0, "late": 0}
    used_patterns: set[str] = set()

    for _, _, event in scored:
        if len(chosen) >= limit:
            break
        pattern_key = (event.pattern_key or event.name or "").strip()
        if pattern_key in used_patterns:
            continue
        units = _event_units(event)
        anchor = units[0] if units else None
        phase = "middle"
        if anchor is not None and all_units:
            try:
                pos = all_units.index(anchor)
            except ValueError:
                pos = 0
            phase = _bucket_name(pos, len(all_units))

        # Prefer under-represented phases
        if phase_counts[phase] >= 2 and any(v < 2 for v in phase_counts.values()):
            continue

        chosen.append({
            "event_id": event.id,
            "name": _event_display_name(event),
            "description": event.description[:200],
            "significance": event.significance[:200] if event.significance else "",
            "location": event.location,
            "source_units": units,
            "phase": phase,
        })
        phase_counts[phase] += 1
        used_patterns.add(pattern_key)

    # If we haven't filled limit, do a second pass without phase constraint
    if len(chosen) < limit:
        chosen_ids = {c["event_id"] for c in chosen}
        for _, _, event in scored:
            if len(chosen) >= limit:
                break
            if event.id in chosen_ids:
                continue
            pattern_key = (event.pattern_key or event.name or "").strip()
            if pattern_key in used_patterns:
                continue
            units = _event_units(event)
            anchor = units[0] if units else None
            phase = "middle"
            if anchor is not None and all_units:
                try:
                    pos = all_units.index(anchor)
                except ValueError:
                    pos = 0
                phase = _bucket_name(pos, len(all_units))
            chosen.append({
                "event_id": event.id,
                "name": _event_display_name(event),
                "description": event.description[:200],
                "significance": event.significance[:200] if event.significance else "",
                "location": event.location,
                "source_units": units,
                "phase": phase,
            })
            used_patterns.add(pattern_key)

    chosen.sort(key=lambda c: (c["source_units"][0] if c["source_units"] else 10**12, c["event_id"]))
    return chosen


# ---------------------------------------------------------------------------
# Helper fields for interaction_patterns
# ---------------------------------------------------------------------------

def _action_type_counts(action_types: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for at in action_types:
        counts[at] = counts.get(at, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _contexts_by_phase(
    contexts: Sequence[str],
    source_units: Sequence[int],
) -> Dict[str, List[str]]:
    """Partition contexts into early/middle/late based on their index ratio."""
    sorted_units = sorted(source_units)
    total = len(contexts)
    phases: Dict[str, List[str]] = {"early": [], "middle": [], "late": []}
    for idx, ctx in enumerate(contexts):
        phase = _bucket_name(idx, total)
        phases[phase].append(ctx[:200])
    return {k: v for k, v in phases.items() if v}


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_relation_profile_inputs(
    *,
    kb: UnifiedKnowledgeBase,
) -> dict:
    all_events = list(kb.events.values())
    relation_inputs: List[dict] = []
    canonical_role_ids: set[str] = set(kb.roles.keys())
    skipped_non_canonical = 0

    for relation in sorted(kb.relations.values(), key=lambda r: (-r.interaction_count, r.id)):
        source_name = relation.from_entity
        target_name = relation.to_entity

        # Canonical endpoint gate: both endpoints must be known roles
        if source_name not in canonical_role_ids or target_name not in canonical_role_ids:
            skipped_non_canonical += 1
            continue

        source_units = sorted(relation.source_units or relation.source_juans)

        # Core fields
        selected_contexts = list(relation.contexts[:5])
        shared = _find_shared_events(source_name, target_name, all_events, limit=6)

        payload: dict = {
            "relation_id": relation.id,
            "source_name": source_name,
            "target_name": target_name,
            "primary_action": relation.primary_action,
            "action_types": relation.action_types,
            "interaction_count": relation.interaction_count,
            "progress_start": relation.progress_start,
            "progress_end": relation.progress_end,
            "source_units": source_units,
            "contexts": selected_contexts,
            "shared_event_refs": shared,
            # Helper fields for interaction_patterns generation
            "action_type_counts": _action_type_counts(relation.action_types),
            "contexts_by_phase": _contexts_by_phase(selected_contexts, source_units),
        }
        payload["input_hash"] = _hash_payload(payload)
        relation_inputs.append(payload)

    return {
        "version": INPUTS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "total_relations": len(relation_inputs),
        "skipped_non_canonical": skipped_non_canonical,
        "relations": relation_inputs,
    }


def build_relation_profile_inputs_file(
    *,
    kb_path: Path,
    output_path: Path,
) -> dict:
    raw = _load_json(kb_path)
    kb = UnifiedKnowledgeBase(**raw)
    payload = build_relation_profile_inputs(kb=kb)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build relation_profile_inputs.json from unified_knowledge.json."
    )
    parser.add_argument(
        "--kb", default="data/unified_knowledge.json",
        help="Unified knowledge base path",
    )
    parser.add_argument(
        "--output", default="data/relation_profile_inputs.json",
        help="Output path",
    )
    args = parser.parse_args()

    payload = build_relation_profile_inputs_file(
        kb_path=Path(args.kb),
        output_path=Path(args.output),
    )
    print(f"Relation profile inputs: {payload['total_relations']} relations -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
