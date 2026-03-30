#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.unified import EntityOccurrence, UnifiedEvent, UnifiedKnowledgeBase, UnifiedLocation, UnifiedRole


PROFILE_INPUTS_VERSION = "entity-profile-inputs-v1"
LEGACY_ALIAS_VERSION = "entity-summary-inputs-v2"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_kb(path: Path) -> UnifiedKnowledgeBase:
    return UnifiedKnowledgeBase(**load_json(path))


def _clean_text(value: str) -> str:
    return " ".join(str(value).strip().split())


def _occurrence_excerpt(occurrence: EntityOccurrence) -> str:
    return _clean_text(occurrence.original_description or occurrence.source_sentence or "")


def _bucket_name(position: int, total: int) -> str:
    if total <= 1:
        return "early"
    ratio = position / max(total - 1, 1)
    if ratio < 1 / 3:
        return "early"
    if ratio < 2 / 3:
        return "middle"
    return "late"


def _looks_low_signal_excerpt(text: str) -> bool:
    stripped = _clean_text(text)
    if not stripped or len(stripped) < 8:
        return True
    banned_prefixes = ("“", "天气", "天色", "清晨", "凌晨", "夜幕", "暮色", "忽然", "突然")
    action_only_markers = ("说道", "问道", "笑道", "答道", "转头", "点头", "摇头", "看着")
    if stripped.startswith(banned_prefixes):
        return True
    if any(marker in stripped and len(stripped) <= 18 for marker in action_only_markers):
        return True
    return False


def _select_representative_excerpts(
    occurrences: Sequence[EntityOccurrence],
    *,
    per_bucket_limit: int = 3,
) -> Tuple[List[dict], List[str]]:
    sorted_occurrences = sorted(
        occurrences,
        key=lambda item: (item.juan_index, item.segment_index, item.chunk_index),
    )
    buckets: Dict[str, List[dict]] = {"early": [], "middle": [], "late": []}
    excerpt_ids: List[str] = []

    for index, occurrence in enumerate(sorted_occurrences):
        text = _occurrence_excerpt(occurrence)
        if _looks_low_signal_excerpt(text):
            continue
        bucket = _bucket_name(index, len(sorted_occurrences))
        if len(buckets[bucket]) >= per_bucket_limit:
            continue
        excerpt_id = f"{occurrence.juan_index}-{occurrence.segment_index}-{occurrence.chunk_index}-{len(buckets[bucket])}"
        buckets[bucket].append(
            {
                "excerpt_id": excerpt_id,
                "juan_index": occurrence.juan_index,
                "segment_index": occurrence.segment_index,
                "chunk_index": occurrence.chunk_index,
                "text": text[:180],
            }
        )
        excerpt_ids.append(excerpt_id)

    excerpts: List[dict] = []
    for bucket_name in ("early", "middle", "late"):
        excerpts.extend({"phase": bucket_name, **item} for item in buckets[bucket_name])
    return excerpts, excerpt_ids


def _event_display_name(event: UnifiedEvent) -> str:
    return (event.display_name or event.name or "").strip()


def _event_pattern_key(event: UnifiedEvent) -> str:
    return (event.pattern_key or event.name or "").strip()


def _event_units(event: UnifiedEvent) -> List[int]:
    return sorted(event.source_units or event.source_juans)


def _event_phase_bucket(event: UnifiedEvent, all_units: Sequence[int]) -> str:
    units = _event_units(event)
    anchor = units[0] if units else None
    if anchor is None or not all_units:
        return "middle"
    try:
        position = all_units.index(anchor)
    except ValueError:
        position = 0
    return _bucket_name(position, len(all_units))


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _score_event(event: UnifiedEvent, *, spotlight_name: Optional[str] = None) -> int:
    score = 0
    score += 3 if event.significance else 0
    score += 2 if event.location else 0
    score += min(len(event.participants), 4)
    score += min(len(_event_units(event)), 3)
    score += 1 if event.evidence_excerpt else 0
    if spotlight_name and spotlight_name in event.participants:
        score += 1
    return score


def _weighted_related_entities(role: UnifiedRole, kb: UnifiedKnowledgeBase, limit: int = 12) -> List[str]:
    weighted: List[Tuple[int, int, str]] = []
    for relation in kb.relations.values():
        counterpart: Optional[str] = None
        if relation.from_entity == role.canonical_name:
            counterpart = relation.to_entity
        elif relation.to_entity == role.canonical_name:
            counterpart = relation.from_entity
        if not counterpart:
            continue
        weighted.append(
            (
                int(relation.interaction_count or 0),
                len(relation.source_units or relation.source_juans),
                counterpart,
            )
        )
    weighted.sort(key=lambda item: (-item[0], -item[1], item[2]))
    seen: set[str] = set()
    ordered: List[str] = []
    for _, _, counterpart in weighted:
        if counterpart in seen:
            continue
        seen.add(counterpart)
        ordered.append(counterpart)
        if len(ordered) >= limit:
            break
    return ordered


def _role_events(role: UnifiedRole, events: Iterable[UnifiedEvent]) -> List[UnifiedEvent]:
    names = {role.canonical_name, *role.all_names}
    related = [event for event in events if names.intersection(event.participants)]
    return sorted(
        related,
        key=lambda event: (
            _event_units(event)[0] if _event_units(event) else 10**12,
            event.id,
        ),
    )


def _role_top_locations(role: UnifiedRole, events: Iterable[UnifiedEvent]) -> List[str]:
    counter: Counter[str] = Counter()
    names = {role.canonical_name, *role.all_names}
    for event in events:
        if event.location and names.intersection(event.participants):
            counter[event.location] += 1
    return [name for name, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:8]]


def _build_event_ref(event: UnifiedEvent, *, phase: Optional[str] = None) -> dict:
    return {
        "event_id": event.id,
        "name": _event_display_name(event),
        "display_name": _event_display_name(event),
        "pattern_key": _event_pattern_key(event),
        "location": event.location,
        "participants": sorted(event.participants),
        "description": event.description,
        "significance": event.significance,
        "source_units": _event_units(event),
        "phase": phase,
    }


def _role_representative_events(role: UnifiedRole, events: Iterable[UnifiedEvent]) -> List[dict]:
    deduped: List[Tuple[int, str, dict]] = []
    seen_pattern_keys: set[str] = set()
    for event in sorted(_role_events(role, events), key=lambda item: (-_score_event(item, spotlight_name=role.canonical_name), _event_display_name(item))):
        pattern_key = _event_pattern_key(event)
        if pattern_key in seen_pattern_keys:
            continue
        seen_pattern_keys.add(pattern_key)
        deduped.append((_score_event(event, spotlight_name=role.canonical_name), _event_display_name(event), _build_event_ref(event)))
        if len(deduped) >= 8:
            break
    return [item for _, _, item in deduped]


def _select_turning_points(role: UnifiedRole, events: Iterable[UnifiedEvent], limit: int = 5) -> List[dict]:
    role_events = _role_events(role, events)
    if not role_events:
        return []

    all_units = sorted({unit for event in role_events for unit in _event_units(event)})
    bucketed: Dict[str, List[Tuple[int, str, dict]]] = {"early": [], "middle": [], "late": []}
    for event in role_events:
        phase = _event_phase_bucket(event, all_units)
        ref = _build_event_ref(event, phase=phase)
        bucketed[phase].append((_score_event(event, spotlight_name=role.canonical_name), ref["display_name"], ref))

    for phase in bucketed:
        bucketed[phase].sort(key=lambda item: (-item[0], item[1]))

    chosen: List[dict] = []
    used_patterns: set[str] = set()
    used_names: set[str] = set()

    for phase in ("early", "middle", "late"):
        for _, _, ref in bucketed[phase]:
            if ref["pattern_key"] in used_patterns or ref["display_name"] in used_names:
                continue
            chosen.append(ref)
            used_patterns.add(ref["pattern_key"])
            used_names.add(ref["display_name"])
            break

    ranked_all = sorted(
        [item for values in bucketed.values() for item in values],
        key=lambda item: (-item[0], item[1]),
    )
    for _, _, ref in ranked_all:
        if len(chosen) >= limit:
            break
        if ref["pattern_key"] in used_patterns or ref["display_name"] in used_names:
            continue
        chosen.append(ref)
        used_patterns.add(ref["pattern_key"])
        used_names.add(ref["display_name"])

    chosen.sort(key=lambda item: ((item.get("source_units") or [10**12])[0], item["display_name"]))
    return chosen[:limit]


def _build_phase_arc_candidates(role: UnifiedRole, events: Iterable[UnifiedEvent]) -> List[dict]:
    role_events = _role_events(role, events)
    if not role_events:
        return []
    all_units = sorted({unit for event in role_events for unit in _event_units(event)})
    phase_best: Dict[str, Tuple[int, dict]] = {}
    for event in role_events:
        phase = _event_phase_bucket(event, all_units)
        ref = _build_event_ref(event, phase=phase)
        score = _score_event(event, spotlight_name=role.canonical_name)
        current = phase_best.get(phase)
        if current is None or score > current[0] or (score == current[0] and ref["display_name"] < current[1]["display_name"]):
            phase_best[phase] = (score, ref)
    return [phase_best[phase][1] for phase in ("early", "middle", "late") if phase in phase_best]


def _identity_facts(role: UnifiedRole, top_locations: Sequence[str]) -> List[str]:
    facts: List[str] = []
    if role.primary_power:
        facts.append(f"主要归属：{role.primary_power}")
    aliases = sorted(name for name in role.all_names if name != role.canonical_name)
    if aliases:
        facts.append(f"别名：{'、'.join(aliases[:3])}")
    if top_locations:
        facts.append(f"高频场域：{'、'.join(top_locations[:3])}")
    facts.append(f"出场跨度：章节{role.first_appearance_juan}-{role.last_appearance_juan}")
    return facts[:4]


def _appearance_span_payload(units: Sequence[int]) -> dict:
    sorted_units = sorted(units)
    if not sorted_units:
        return {"first_unit": None, "last_unit": None, "unit_count": 0}
    return {
        "first_unit": sorted_units[0],
        "last_unit": sorted_units[-1],
        "unit_count": len(sorted_units),
    }


def _location_top_roles(location: UnifiedLocation, events: Iterable[UnifiedEvent]) -> List[str]:
    counter: Counter[str] = Counter(location.associated_entities)
    for event in events:
        if event.location == location.canonical_name:
            for participant in event.participants:
                counter[participant] += 1
    return [name for name, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:8]]


def _location_top_events(location: UnifiedLocation, events: Iterable[UnifiedEvent]) -> List[dict]:
    ranked: List[Tuple[int, str, dict]] = []
    seen_pattern_keys: set[str] = set()
    location_events = [event for event in events if event.location == location.canonical_name]
    location_events.sort(key=lambda event: (-_score_event(event), _event_display_name(event)))
    for event in location_events:
        pattern_key = _event_pattern_key(event)
        if pattern_key in seen_pattern_keys:
            continue
        seen_pattern_keys.add(pattern_key)
        ranked.append((_score_event(event), _event_display_name(event), _build_event_ref(event)))
        if len(ranked) >= 8:
            break
    return [item for _, _, item in ranked]


def build_entity_profile_inputs(
    *,
    kb: UnifiedKnowledgeBase,
    max_entities: Optional[int] = None,
) -> dict:
    all_events = list(kb.events.values())
    role_inputs: List[dict] = []
    location_inputs: List[dict] = []

    role_items = sorted(kb.roles.values(), key=lambda item: (-item.total_mentions, item.canonical_name))
    location_items = sorted(kb.locations.values(), key=lambda item: (-item.total_mentions, item.canonical_name))
    if max_entities is not None:
        role_items = role_items[:max_entities]
        location_items = location_items[:max_entities]

    for role in role_items:
        excerpts, excerpt_ids = _select_representative_excerpts(role.occurrences)
        top_locations = _role_top_locations(role, all_events)
        weighted_related_entities = _weighted_related_entities(role, kb)
        turning_points = _select_turning_points(role, all_events)
        payload = {
            "entity_type": "role",
            "entity_id": role.id,
            "canonical_name": role.canonical_name,
            "all_names": sorted(role.all_names),
            "primary_power": role.primary_power,
            "powers": role.powers,
            "affiliation_history": list(dict.fromkeys(power for power in role.powers if power)),
            "first_appearance_juan": role.first_appearance_juan,
            "last_appearance_juan": role.last_appearance_juan,
            "appearance_span": _appearance_span_payload(sorted(role.units_appeared or role.juans_appeared)),
            "total_mentions": role.total_mentions,
            "top_related_entities": weighted_related_entities,
            "top_related_entities_weighted": weighted_related_entities,
            "top_locations": top_locations,
            "top_locations_weighted": top_locations,
            "representative_events": _role_representative_events(role, all_events),
            "turning_point_candidates": turning_points,
            "phase_arc_candidates": _build_phase_arc_candidates(role, all_events),
            "identity_facts": _identity_facts(role, top_locations),
            "representative_original_excerpts": excerpts,
            "original_descriptions": role.original_descriptions[:12],
        }
        payload["input_hash"] = _hash_payload(payload)
        payload["evidence_excerpt_ids"] = excerpt_ids
        role_inputs.append(payload)

    for location in location_items:
        excerpts, excerpt_ids = _select_representative_excerpts(location.occurrences)
        payload = {
            "entity_type": "location",
            "entity_id": location.id,
            "canonical_name": location.canonical_name,
            "all_names": sorted(location.all_names),
            "location_type": location.location_type,
            "associated_entities": sorted(location.associated_entities),
            "associated_events": sorted(location.associated_events),
            "appearance_span": _appearance_span_payload(sorted(location.units_appeared or location.juans_appeared)),
            "representative_original_excerpts": excerpts,
            "top_roles": _location_top_roles(location, all_events),
            "top_events": _location_top_events(location, all_events),
            "identity_facts": [fact for fact in [
                f"地点类型：{location.location_type}" if location.location_type else "",
                f"关联人物：{'、'.join(_location_top_roles(location, all_events)[:3])}" if _location_top_roles(location, all_events) else "",
                f"章节跨度：{_appearance_span_payload(sorted(location.units_appeared or location.juans_appeared))['first_unit']}-{_appearance_span_payload(sorted(location.units_appeared or location.juans_appeared))['last_unit']}" if (location.units_appeared or location.juans_appeared) else "",
            ] if fact],
            "original_descriptions": location.original_descriptions[:12],
        }
        payload["input_hash"] = _hash_payload(payload)
        payload["evidence_excerpt_ids"] = excerpt_ids
        location_inputs.append(payload)

    return {
        "version": PROFILE_INPUTS_VERSION,
        "legacy_alias_version": LEGACY_ALIAS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "roles": role_inputs,
        "locations": location_inputs,
    }


def build_entity_profile_inputs_file(
    *,
    kb_input_path: Path,
    output_path: Path,
    max_entities: Optional[int] = None,
) -> dict:
    kb = load_kb(kb_input_path)
    payload = build_entity_profile_inputs(kb=kb, max_entities=max_entities)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Entity profile inputs -> {output_path}")
    return payload


def build_entity_summary_inputs(
    *,
    kb: UnifiedKnowledgeBase,
    max_entities: Optional[int] = None,
) -> dict:
    return build_entity_profile_inputs(kb=kb, max_entities=max_entities)


def build_entity_summary_inputs_file(
    *,
    kb_input_path: Path,
    output_path: Path,
    max_entities: Optional[int] = None,
) -> dict:
    return build_entity_profile_inputs_file(
        kb_input_path=kb_input_path,
        output_path=output_path,
        max_entities=max_entities,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build post-resolve entity profile input packs.")
    parser.add_argument("--kb-input", default="data/unified_knowledge.json", help="Unified knowledge JSON path.")
    parser.add_argument("--output", default="data/entity_profile_inputs.json", help="Output JSON path.")
    parser.add_argument("--max-entities", type=int, default=None, help="Optional limit for quick iteration.")
    args = parser.parse_args()

    build_entity_profile_inputs_file(
        kb_input_path=Path(args.kb_input),
        output_path=Path(args.output),
        max_entities=args.max_entities,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
