#!/usr/bin/env python3
"""
Build chapter_synopses.json – an intermediate data layer between raw text and
structured events.

Each chapter gets a synopsis record aggregated from unified_knowledge.json
and unit_progress_index.json.  No LLM calls – pure aggregation.

Output schema per entry:
    unit_index          int
    unit_title          str
    season_name         str
    event_count         int
    active_characters   list[str]      – characters that appear in this chapter
    locations           list[str]      – locations mentioned
    key_developments    list[str]      – top event descriptions, ordered by score
    synopsis            str            – one-paragraph prose summary
    narrative_function  str            – heuristic label (开篇/过渡/高潮/收束)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from model.unified import UnifiedEvent, UnifiedKnowledgeBase


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_event_units(event: UnifiedEvent) -> List[int]:
    return sorted(event.source_units or event.source_juans)


def _classify_event_type(event: UnifiedEvent, rules: Sequence[dict]) -> str:
    text = " ".join(
        part
        for part in [
            event.name,
            event.description,
            event.significance,
            event.background,
            event.location or "",
        ]
        if part
    )
    best_type: Optional[str] = None
    best_score = 0
    for rule in rules:
        keywords = [str(k).strip() for k in rule.get("keywords", []) if str(k).strip()]
        hits = sum(1 for k in keywords if k in text)
        if hits > best_score:
            best_score = hits
            best_type = str(rule.get("type", "")).strip() or None
    if best_type:
        return best_type
    if len(event.participants) >= 2 and event.location:
        return "会见"
    if len(event.participants) >= 2:
        return "关系推进"
    if event.location:
        return "场景推进"
    return "剧情推进"


_EVENT_TYPE_WEIGHT = {
    "冲突": 6,
    "揭示": 5,
    "立势": 5,
    "师承": 5,
    "护持": 4,
    "迁移": 4,
    "遭遇": 4,
    "指点": 4,
    "会见": 3,
    "等待": 2,
    "对话": 2,
    "关系推进": 2,
    "场景推进": 1,
    "剧情推进": 1,
}


def _event_score(event_ref: dict) -> int:
    """Lightweight event score (no writer_focus / spotlight)."""
    return (
        _EVENT_TYPE_WEIGHT.get(event_ref.get("event_type", ""), 1)
        + min(len(event_ref.get("participants", [])), 4)
        + (1 if event_ref.get("location") else 0)
        + (1 if event_ref.get("significance") else 0)
    )


_NARRATIVE_KEYWORDS = {
    "开篇": {"惊蛰", "初见", "相识", "开篇", "初到", "抵达", "初临"},
    "高潮": {"冲突", "大战", "对决", "揭示", "爆发", "击杀", "生死"},
    "收束": {"离别", "告别", "归来", "结束", "远行", "离去", "落幕"},
}


def _classify_narrative_function(
    unit_index: int,
    season_unit_start: int,
    season_unit_end: int,
    event_refs: List[dict],
) -> str:
    """Heuristic narrative function label for the chapter."""
    season_length = max(season_unit_end - season_unit_start + 1, 1)
    position_ratio = (unit_index - season_unit_start) / season_length

    # Keyword signals from event names + descriptions
    combined_text = " ".join(
        f"{ref.get('name', '')} {ref.get('description', '')} {ref.get('significance', '')}"
        for ref in event_refs
    )
    keyword_votes: Counter[str] = Counter()
    for label, keywords in _NARRATIVE_KEYWORDS.items():
        for kw in keywords:
            if kw in combined_text:
                keyword_votes[label] += 1

    # High-tension score
    tension = sum(
        _EVENT_TYPE_WEIGHT.get(ref.get("event_type", ""), 1)
        for ref in event_refs
    )
    avg_tension = tension / max(len(event_refs), 1)

    # Position-based default
    if position_ratio < 0.10:
        default = "开篇"
    elif position_ratio > 0.90:
        default = "收束"
    elif avg_tension >= 5.0 or keyword_votes.get("高潮", 0) >= 2:
        default = "高潮"
    else:
        default = "过渡"

    # Keyword override if strong signal
    if keyword_votes:
        top_label, top_count = keyword_votes.most_common(1)[0]
        if top_count >= 2:
            return top_label

    return default


# ---------------------------------------------------------------------------
#  Core builder
# ---------------------------------------------------------------------------

def build_chapter_synopses(
    *,
    kb: UnifiedKnowledgeBase,
    unit_progress_index: dict,
    event_type_rules: Sequence[dict] = (),
    max_developments: int = 5,
) -> List[dict]:
    """Build per-chapter synopsis records.

    Returns a list sorted by unit_index.
    """
    unit_meta: Dict[int, dict] = {
        int(uid): meta
        for uid, meta in unit_progress_index.get("units", {}).items()
    }

    # --- Whole-book name frequency for occurrence metadata ---
    name_counts: Dict[str, int] = {}
    name_first_unit: Dict[str, int] = {}
    for event in kb.events.values():
        n = event.name
        name_counts[n] = name_counts.get(n, 0) + 1
        first_u = min(event.source_units or event.source_juans, default=None)
        if first_u is not None:
            prev = name_first_unit.get(n)
            if prev is None or first_u < prev:
                name_first_unit[n] = first_u

    # Group events by unit
    events_by_unit: Dict[int, List[dict]] = defaultdict(list)
    for event in kb.events.values():
        event_type = _classify_event_type(event, event_type_rules)
        ref = {
            "event_id": event.id,
            "name": event.name,
            "event_type": event_type,
            "location": event.location,
            "participants": sorted(event.participants),
            "description": event.description,
            "significance": event.significance,
            # Provenance / occurrence metadata
            "evidence_excerpt": getattr(event, "evidence_excerpt", "") or "",
            "matched_rule_name": getattr(event, "matched_rule_name", "") or "",
            "name_occurrence_count": name_counts.get(event.name, 1),
            "first_occurrence_unit": name_first_unit.get(event.name),
        }
        for uid in _get_event_units(event):
            ref_copy = dict(ref)
            ref_copy["is_first_occurrence"] = (uid == name_first_unit.get(event.name))
            events_by_unit[uid].append(ref_copy)

    # Group roles by unit
    roles_by_unit: Dict[int, List[str]] = defaultdict(list)
    for role in kb.roles.values():
        for uid in sorted(role.units_appeared or role.juans_appeared):
            roles_by_unit[uid].append(role.canonical_name)

    # Group locations by unit
    locations_by_unit: Dict[int, List[str]] = defaultdict(list)
    for loc in kb.locations.values():
        for uid in sorted(loc.units_appeared or loc.juans_appeared):
            locations_by_unit[uid].append(loc.canonical_name)

    # Build season ranges for narrative_function classification
    season_ranges: Dict[str, tuple[int, int]] = {}
    for meta in unit_meta.values():
        sn = meta.get("season_name")
        if not sn:
            continue
        lo, hi = season_ranges.get(sn, (10**9, -1))
        uid = meta["unit_index"]
        season_ranges[sn] = (min(lo, uid), max(hi, uid))

    synopses: List[dict] = []
    for uid in sorted(unit_meta):
        meta = unit_meta[uid]
        chapter_events = events_by_unit.get(uid, [])
        scored_events = sorted(chapter_events, key=_event_score, reverse=True)

        # Key developments: top N unique-name events
        seen_names: set[str] = set()
        key_developments: List[str] = []
        key_development_events: List[dict] = []
        for ref in scored_events:
            name = ref["name"]
            if name in seen_names:
                continue
            seen_names.add(name)
            desc = ref.get("description") or ref.get("significance") or ""
            text = f"{name}：{desc}" if desc else name
            key_developments.append(text)

            # Build card-granularity structured development
            evidence = ref.get("evidence_excerpt") or ""
            # display_text: event name + evidence sentence excerpt, max 100 chars
            if evidence:
                display_text = f"{name}：{evidence}"[:100]
            else:
                # Fallback to description truncated
                display_text = f"{name}：{desc}"[:100] if desc else name[:100]
            key_development_events.append({
                "event_id": ref["event_id"],
                "name": name,
                "display_text": display_text,
                "evidence_excerpt": evidence,
                "participants": ref.get("participants", []),
                "location": ref.get("location"),
            })
            if len(key_developments) >= max_developments:
                break

        # Active characters (deduplicated, sorted by mention frequency in events)
        char_counter: Counter[str] = Counter()
        for ref in chapter_events:
            for p in ref.get("participants", []):
                char_counter[p] += 1
        # Also include role appearances even if not in events
        for rn in roles_by_unit.get(uid, []):
            char_counter[rn] += 0  # ensure present
        active_characters = [name for name, _ in char_counter.most_common()]

        # Locations
        loc_counter: Counter[str] = Counter()
        for ref in chapter_events:
            loc = ref.get("location")
            if loc:
                loc_counter[loc] += 1
        for ln in locations_by_unit.get(uid, []):
            loc_counter[ln] += 0
        locations = [name for name, _ in loc_counter.most_common()]

        # Synopsis – card-granularity: max 2 structured developments, 80 chars
        # each, total ≤220 chars
        synopsis_parts: List[str] = []
        running_len = 0
        for dev_event in key_development_events[:2]:
            part = dev_event["display_text"][:80]
            if running_len + len(part) > 210:
                part = part[:max(0, 210 - running_len)]
            if part:
                synopsis_parts.append(part)
                running_len += len(part) + 1  # +1 for separator
        synopsis = "；".join(synopsis_parts) + "。" if synopsis_parts else ""
        # Hard cap at 220
        if len(synopsis) > 220:
            synopsis = synopsis[:217] + "…。"

        # Narrative function
        season_name = meta.get("season_name", "")
        sr = season_ranges.get(season_name, (uid, uid))
        narrative_function = _classify_narrative_function(
            uid, sr[0], sr[1], chapter_events,
        )

        synopses.append({
            "unit_index": uid,
            "unit_title": meta.get("unit_title", ""),
            "season_name": season_name,
            "event_count": len(chapter_events),
            "active_characters": active_characters,
            "locations": locations,
            "key_developments": key_developments,
            "key_development_events": key_development_events,
            "synopsis": synopsis,
            "narrative_function": narrative_function,
        })

    return synopses


# ---------------------------------------------------------------------------
#  File-level entry points
# ---------------------------------------------------------------------------

def build_chapter_synopses_file(
    *,
    kb: UnifiedKnowledgeBase,
    unit_progress_index_path: Path,
    core_cast_path: Path,
    output_path: Path,
) -> List[dict]:
    """Build and save chapter_synopses.json. Returns the payload."""
    upi = load_json(unit_progress_index_path)
    core_cast = load_json(core_cast_path)
    event_type_rules = core_cast.get("event_type_rules", [])

    synopses = build_chapter_synopses(
        kb=kb,
        unit_progress_index=upi,
        event_type_rules=event_type_rules,
    )

    payload = {
        "version": "chapter-synopses-v1",
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "chapter_count": len(synopses),
        "chapters": synopses,
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Chapter synopses ({len(synopses)} chapters) → {output_path}")
    return synopses
