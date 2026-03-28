#!/usr/bin/env python3
"""
Build key_events_index.json – a curated index of the most important events
grouped by chapter, with importance tiers.

Output schema per entry:
    unit_index          int
    unit_title          str
    season_name         str
    key_events          list[KeyEvent]

KeyEvent schema:
    event_id            str
    name                str
    event_type          str
    importance          "critical" | "major" | "notable"
    score               int
    location            str | null
    participants        list[str]
    description         str
    significance        str
    involved_characters list[str]    – characters involved in this event
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from model.unified import UnifiedEvent, UnifiedKnowledgeBase


# ---------------------------------------------------------------------------
#  Helpers (self-contained – mirrors writer_insights scoring without import)
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
    """Event importance score (lightweight, no writer_focus)."""
    return (
        _EVENT_TYPE_WEIGHT.get(event_ref.get("event_type", ""), 1)
        + min(len(event_ref.get("participants", [])), 4)
        + (1 if event_ref.get("location") else 0)
        + (1 if event_ref.get("significance") else 0)
    )


def _importance_tier(score: int) -> str:
    """Map numeric score to a tier label."""
    if score >= 10:
        return "critical"
    if score >= 7:
        return "major"
    return "notable"


# ---------------------------------------------------------------------------
#  Core builder
# ---------------------------------------------------------------------------

def build_key_events_index(
    *,
    kb: UnifiedKnowledgeBase,
    unit_progress_index: dict,
    event_type_rules: Sequence[dict] = (),
    max_events_per_chapter: int = 8,
    min_score: int = 4,
) -> List[dict]:
    """Build per-chapter key-events index.

    Returns a list of chapter records sorted by unit_index.
    Only chapters that have at least one qualifying event are included.
    """
    unit_meta: Dict[int, dict] = {
        int(uid): meta
        for uid, meta in unit_progress_index.get("units", {}).items()
    }

    # --- Whole-book name frequency ---
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
        evidence_excerpt = getattr(event, "evidence_excerpt", "") or ""
        matched_rule_name = getattr(event, "matched_rule_name", "") or ""
        noc = name_counts.get(event.name, 1)
        ref = {
            "event_id": event.id,
            "name": event.name,
            "event_type": event_type,
            "location": event.location,
            "participants": sorted(event.participants),
            "description": event.description,
            "significance": event.significance,
            "evidence_excerpt": evidence_excerpt,
            "matched_rule_name": matched_rule_name,
            "name_occurrence_count": noc,
            "first_occurrence_unit": name_first_unit.get(event.name),
        }
        ref["score"] = _event_score(ref)
        # Scoring adjustments for card selection
        if evidence_excerpt:
            ref["score"] += 1
        if noc <= 1:
            ref["score"] += 2  # first/unique occurrence bonus
        elif noc > 8:
            ref["score"] -= min(noc - 8, 10)  # soft penalty for high-freq names
        for uid in _get_event_units(event):
            ref_copy = dict(ref)
            ref_copy["is_first_occurrence"] = (uid == name_first_unit.get(event.name))
            events_by_unit[uid].append(ref_copy)

    chapters: List[dict] = []
    for uid in sorted(unit_meta):
        meta = unit_meta[uid]
        chapter_events = events_by_unit.get(uid, [])
        # Sort descending by score
        ranked = sorted(chapter_events, key=lambda r: r["score"], reverse=True)

        # Deduplicate by name, keeping highest-scoring instance
        seen_names: set[str] = set()
        selected: List[dict] = []
        for ref in ranked:
            if ref["name"] in seen_names:
                continue
            if ref["score"] < min_score:
                continue
            seen_names.add(ref["name"])

            # Build display_summary: evidence_excerpt first, then description truncated
            evidence = ref.get("evidence_excerpt") or ""
            desc = ref.get("description") or ""
            if evidence:
                display_summary = f"{ref['name']}：{evidence}"[:100]
            elif desc:
                display_summary = f"{ref['name']}：{desc}"[:100]
            else:
                display_summary = ref["name"][:100]

            # Determine selection reason
            reasons: List[str] = []
            if ref.get("is_first_occurrence"):
                reasons.append("首次出现")
            if ref.get("matched_rule_name"):
                reasons.append(f"规则命中:{ref['matched_rule_name']}")
            if evidence:
                reasons.append("有证据摘录")
            noc = ref.get("name_occurrence_count", 1)
            if noc > 8:
                reasons.append(f"高频名称({noc})")
            selection_reason = "；".join(reasons) if reasons else "分数排序"

            selected.append({
                "event_id": ref["event_id"],
                "name": ref["name"],
                "event_type": ref["event_type"],
                "importance": _importance_tier(ref["score"]),
                "score": ref["score"],
                "location": ref["location"],
                "participants": ref["participants"],
                "description": ref["description"],
                "significance": ref["significance"],
                "involved_characters": ref["participants"],
                # New card-granularity fields
                "display_summary": display_summary,
                "evidence_excerpt": evidence,
                "matched_rule_name": ref.get("matched_rule_name", ""),
                "name_occurrence_count": ref.get("name_occurrence_count", 1),
                "first_occurrence_unit": ref.get("first_occurrence_unit"),
                "is_first_occurrence": bool(ref.get("is_first_occurrence")),
                "selection_reason": selection_reason,
            })
            if len(selected) >= max_events_per_chapter:
                break

        if not selected:
            continue

        chapters.append({
            "unit_index": uid,
            "unit_title": meta.get("unit_title", ""),
            "season_name": meta.get("season_name", ""),
            "key_events": selected,
        })

    return chapters


# ---------------------------------------------------------------------------
#  File-level entry points
# ---------------------------------------------------------------------------

def build_key_events_index_file(
    *,
    kb: UnifiedKnowledgeBase,
    unit_progress_index_path: Path,
    core_cast_path: Path,
    output_path: Path,
) -> List[dict]:
    """Build and save key_events_index.json. Returns the chapter list."""
    upi = load_json(unit_progress_index_path)
    core_cast = load_json(core_cast_path)
    event_type_rules = core_cast.get("event_type_rules", [])

    chapters = build_key_events_index(
        kb=kb,
        unit_progress_index=upi,
        event_type_rules=event_type_rules,
    )

    total_events = sum(len(ch["key_events"]) for ch in chapters)

    payload = {
        "version": "key-events-index-v1",
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "chapter_count": len(chapters),
        "total_key_events": total_events,
        "chapters": chapters,
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Key events index ({len(chapters)} chapters, {total_events} events) → {output_path}")
    return chapters
