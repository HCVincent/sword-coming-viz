#!/usr/bin/env python3
"""Build event_dossier_inputs.json – select Top 500 events via unified scoring.

Scoring tiers (reference-source bonuses):
  story_beats / anchor_events        +6
  turning_point_candidates           +5
  key_events_index                   +4
  character_arcs / conflict_chains / foreshadowing  +3
  representative_events / phase_arc  +2

Multi-source bonus: +2 per additional source, cap +6.
Quality: catalog +3, significance +2, evidence_excerpt +1, location +1,
         min(participants, 3), source_units span>1 +1.

Dedup: display_name max 1, pattern_key max 3.
Greedy selection to 500 with score desc → earliest unit → event_id.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.unified import UnifiedEvent, UnifiedKnowledgeBase
from scripts.character_quality import is_pseudo_role_name

INPUTS_VERSION = "event-dossier-inputs-v1"
TOP_N = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _event_display_name(event: UnifiedEvent) -> str:
    return (event.display_name or event.name or "").strip()


def _event_units(event: UnifiedEvent) -> List[int]:
    return sorted(event.source_units or event.source_juans)


# ---------------------------------------------------------------------------
# Reference-source extraction
# ---------------------------------------------------------------------------

def _collect_referenced_event_ids(
    *,
    writer_insights: dict,
    key_events_index: dict,
) -> Dict[str, Set[str]]:
    """Extract event IDs per reference source.

    Returns { source_label: set(event_id) }.
    """
    sources: Dict[str, Set[str]] = defaultdict(set)

    def _safe_iter(items: Any) -> list:
        """Yield only non-None dicts from a list that may contain None."""
        return [item for item in (items or []) if item is not None and isinstance(item, dict)]

    # ── writer_insights ──────────────────────────────────────────────────
    for season_overview in _safe_iter(writer_insights.get("season_overviews")):
        # story_beats
        for beat in _safe_iter(season_overview.get("story_beats")):
            event = beat.get("event") or {}
            eid = event.get("event_id", "")
            if eid:
                sources["story_beats"].add(eid)
        # anchor_events
        for event in _safe_iter(season_overview.get("anchor_events")):
            eid = event.get("event_id", "")
            if eid:
                sources["anchor_events"].add(eid)

    for arc in _safe_iter(writer_insights.get("character_arcs")):
        for event in _safe_iter(arc.get("key_events")):
            eid = event.get("event_id", "")
            if eid:
                sources["character_arcs"].add(eid)
        # turning_point_candidates (if present)
        for event in _safe_iter(arc.get("turning_point_candidates")):
            eid = event.get("event_id", "")
            if eid:
                sources["turning_point_candidates"].add(eid)

    for chain in _safe_iter(writer_insights.get("conflict_chains")):
        for beat in _safe_iter(chain.get("beats")):
            eid = beat.get("event_id", "")
            if eid:
                sources["conflict_chains"].add(eid)

    for thread in _safe_iter(writer_insights.get("foreshadowing_threads")):
        for event in _safe_iter(thread.get("clue_events")):
            eid = event.get("event_id", "")
            if eid:
                sources["foreshadowing"].add(eid)
        for event in _safe_iter(thread.get("payoff_events")):
            eid = event.get("event_id", "")
            if eid:
                sources["foreshadowing"].add(eid)

    for rel in _safe_iter(writer_insights.get("curated_relationships")):
        for event in _safe_iter(rel.get("key_events")):
            eid = event.get("event_id", "")
            if eid:
                sources["representative_events"].add(eid)
        for beat in _safe_iter(rel.get("manual_beats")):
            eid = beat.get("event_id", "")
            if eid:
                sources["representative_events"].add(eid)

    # ── key_events_index ─────────────────────────────────────────────────
    for chapter in _safe_iter(key_events_index.get("chapters")):
        for event in _safe_iter(chapter.get("key_events")):
            eid = event.get("event_id", "")
            if eid:
                sources["key_events_index"].add(eid)

    return sources


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Reference-source tier points
_SOURCE_POINTS: Dict[str, int] = {
    "story_beats": 6,
    "anchor_events": 6,
    "turning_point_candidates": 5,
    "key_events_index": 4,
    "character_arcs": 3,
    "conflict_chains": 3,
    "foreshadowing": 3,
    "representative_events": 2,
    "phase_arc": 2,
}
_MULTI_SOURCE_CAP = 6


def _score_event(
    event: UnifiedEvent,
    source_membership: Dict[str, Set[str]],
) -> Tuple[int, int]:
    """Return (total_score, earliest_unit) for an event."""
    eid = event.id
    units = _event_units(event)
    earliest = units[0] if units else 10**9

    # Reference-source bonus: take the max tier hit + multi-source bonus
    hit_sources: List[str] = []
    for src, ids in source_membership.items():
        if eid in ids:
            hit_sources.append(src)

    ref_score = 0
    if hit_sources:
        # Best single tier
        ref_score = max(_SOURCE_POINTS.get(s, 0) for s in hit_sources)
        # Multi-source bonus: +2 per extra source, capped
        extra_sources = len(hit_sources) - 1
        ref_score += min(extra_sources * 2, _MULTI_SOURCE_CAP)

    # Quality bonuses
    quality = 0
    quality += 3 if event.title_source == "catalog" else 0
    quality += 2 if event.significance else 0
    quality += 1 if event.evidence_excerpt else 0
    quality += 1 if event.location else 0
    quality += min(len(event.participants), 3)
    quality += 1 if len(units) > 1 else 0

    return ref_score + quality, earliest


def _select_top_n(
    events: Dict[str, UnifiedEvent],
    source_membership: Dict[str, Set[str]],
    *,
    top_n: int = TOP_N,
) -> List[str]:
    """Greedy Top-N selection with display_name max-1 and pattern_key max-3."""
    scored: List[Tuple[int, int, str, UnifiedEvent]] = []
    for eid, event in events.items():
        total, earliest = _score_event(event, source_membership)
        scored.append((total, earliest, eid, event))

    # Sort: score desc, earliest unit asc, event_id asc
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))

    selected: List[str] = []
    display_name_used: Counter[str] = Counter()
    pattern_key_used: Counter[str] = Counter()

    for total, earliest, eid, event in scored:
        if len(selected) >= top_n:
            break

        dn = _event_display_name(event)
        pk = (event.pattern_key or event.name or "").strip()

        # display_name max 1
        if dn and display_name_used[dn] >= 1:
            continue
        # pattern_key max 3
        if pk and pattern_key_used[pk] >= 3:
            continue

        selected.append(eid)
        if dn:
            display_name_used[dn] += 1
        if pk:
            pattern_key_used[pk] += 1

    return selected


# ---------------------------------------------------------------------------
# Input packet builder
# ---------------------------------------------------------------------------

def _build_event_packet(
    event: UnifiedEvent,
    *,
    source_membership: Dict[str, Set[str]],
    event_score: int,
    canonical_role_ids: Set[str] | None = None,
) -> dict:
    """Build a Gemini-consumable packet for one event.

    If *canonical_role_ids* is given, only participants present in that set
    are included – this strips noisy pseudo-names from the packet.
    """
    eid = event.id
    units = _event_units(event)
    reference_sources = sorted(
        s for s, ids in source_membership.items() if eid in ids
    )

    participants = list(event.participants)
    if canonical_role_ids is not None:
        participants = [p for p in participants if p in canonical_role_ids]

    payload: dict = {
        "event_id": eid,
        "name": event.name,
        "display_name": _event_display_name(event),
        "pattern_key": event.pattern_key or "",
        "location": event.location,
        "participants": participants,
        "description": event.description,
        "significance": event.significance or "",
        "background": event.background or "",
        "evidence_excerpt": event.evidence_excerpt or "",
        "progress_start": event.progress_start,
        "progress_end": event.progress_end,
        "progress_label": event.progress_label or "",
        "source_units": units,
        "reference_sources": reference_sources,
        "event_score": event_score,
    }
    payload["input_hash"] = _hash_payload(payload)
    return payload


def build_event_dossier_inputs(
    *,
    kb: UnifiedKnowledgeBase,
    writer_insights: dict,
    key_events_index: dict,
    top_n: int = TOP_N,
) -> dict:
    source_membership = _collect_referenced_event_ids(
        writer_insights=writer_insights,
        key_events_index=key_events_index,
    )

    selected_ids = _select_top_n(
        kb.events, source_membership, top_n=top_n,
    )

    canonical_role_ids: Set[str] = set(kb.roles.keys())
    event_packets: List[dict] = []
    for eid in selected_ids:
        event = kb.events.get(eid)
        if not event:
            continue
        score, _ = _score_event(event, source_membership)
        packet = _build_event_packet(
            event,
            source_membership=source_membership,
            event_score=score,
            canonical_role_ids=canonical_role_ids,
        )
        event_packets.append(packet)

    return {
        "version": INPUTS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "total_events_in_kb": len(kb.events),
        "total_selected": len(event_packets),
        "top_n": top_n,
        "events": event_packets,
    }


def build_event_dossier_inputs_file(
    *,
    kb_path: Path,
    writer_insights_path: Path,
    key_events_index_path: Path,
    output_path: Path,
    top_n: int = TOP_N,
) -> dict:
    raw = _load_json(kb_path)
    kb = UnifiedKnowledgeBase(**raw)
    writer_insights = _load_json(writer_insights_path)
    key_events_index = _load_json(key_events_index_path)

    payload = build_event_dossier_inputs(
        kb=kb,
        writer_insights=writer_insights,
        key_events_index=key_events_index,
        top_n=top_n,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build event_dossier_inputs.json – Top 500 events via unified scoring."
    )
    parser.add_argument("--kb", default="data/unified_knowledge.json")
    parser.add_argument("--writer-insights", default="data/writer_insights.json")
    parser.add_argument("--key-events-index", default="data/key_events_index.json")
    parser.add_argument("--output", default="data/event_dossier_inputs.json")
    parser.add_argument("--top-n", type=int, default=TOP_N)
    args = parser.parse_args()

    payload = build_event_dossier_inputs_file(
        kb_path=Path(args.kb),
        writer_insights_path=Path(args.writer_insights),
        key_events_index_path=Path(args.key_events_index),
        output_path=Path(args.output),
        top_n=args.top_n,
    )
    print(
        f"Event dossier inputs: {payload['total_selected']}/{payload['total_events_in_kb']}"
        f" events -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
