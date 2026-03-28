#!/usr/bin/env python3

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from model.unified import UnifiedEvent, UnifiedKnowledgeBase, UnifiedRelation, UnifiedRole


RELATION_KIND_LABELS = {
    "mirror": "镜像",
    "emotion": "情感",
    "mentor": "引路",
    "friend": "同伴",
    "guide": "指引",
    "mystery": "隐线",
    "opposition": "对立",
}

DISPLAY_COPY_REPLACEMENTS = {
    "抓手": "线索",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unique_names(names: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for name in names:
        normalized = str(name).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def get_role_units(role: UnifiedRole) -> List[int]:
    return sorted(role.units_appeared or role.juans_appeared)


def get_event_units(event: UnifiedEvent) -> List[int]:
    return sorted(event.source_units or event.source_juans)


def get_relation_units(relation: UnifiedRelation) -> List[int]:
    return sorted(relation.source_units or relation.source_juans)


def normalize_relationship_kind(kind: Any) -> str:
    normalized = str(kind or "").strip()
    if not normalized:
        return "关系"
    return RELATION_KIND_LABELS.get(normalized.lower(), normalized)


def normalize_display_copy(text: Any) -> str:
    normalized = str(text or "").strip()
    for source, target in DISPLAY_COPY_REPLACEMENTS.items():
        normalized = normalized.replace(source, target)
    return normalized


def range_overlaps(
    current_range: Tuple[Optional[int], Optional[int]],
    filter_range: Tuple[Optional[int], Optional[int]],
) -> bool:
    current_start, current_end = current_range
    filter_start, filter_end = filter_range
    if filter_start is None and filter_end is None:
        return True
    if current_start is None and current_end is None:
        return False

    effective_current_start = current_start if current_start is not None else current_end
    effective_current_end = current_end if current_end is not None else current_start
    if effective_current_start is None or effective_current_end is None:
        return False

    normalized_current_start = min(effective_current_start, effective_current_end)
    normalized_current_end = max(effective_current_start, effective_current_end)
    normalized_filter_start = filter_start if filter_start is not None else -10**12
    normalized_filter_end = filter_end if filter_end is not None else 10**12

    return normalized_current_end >= normalized_filter_start and normalized_current_start <= normalized_filter_end


def classify_event_type(event: UnifiedEvent, rules: Sequence[dict]) -> str:
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

    best_type = None
    best_score = 0
    for rule in rules:
        keywords = [str(keyword).strip() for keyword in rule.get("keywords", []) if str(keyword).strip()]
        hits = sum(1 for keyword in keywords if keyword in text)
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


def build_priority_pair_scores(writer_focus: dict) -> Dict[frozenset[str], int]:
    pair_scores: Dict[frozenset[str], int] = {}
    for item in writer_focus.get("priority_pairs", []):
        roles = [str(name).strip() for name in item.get("roles", []) if str(name).strip()]
        if len(roles) != 2:
            continue
        pair_scores[frozenset(roles)] = int(item.get("weight", 1))
    return pair_scores


def get_season_focus(writer_focus: dict, season_name: str) -> dict:
    season_focus = writer_focus.get("season_focus", {})
    if not isinstance(season_focus, dict):
        return {}
    focused = season_focus.get(season_name, {})
    return focused if isinstance(focused, dict) else {}


def build_season_priority_roles(
    *,
    top_roles: Sequence[dict],
    season_focus: dict,
    limit: int = 8,
) -> Tuple[List[dict], List[str]]:
    """Build priority roles for a season overview.

    Returns ``(priority_roles, dropped_names)`` where *dropped_names*
    lists any season_focus names that had **zero** unit appearances in
    the season (evidence-gated: only roles actually present in the
    season's chapter data are included).
    """
    role_index = {item["role_name"]: item for item in top_roles}
    priority_roles: List[dict] = []
    dropped_names: List[str] = []
    seen: set[str] = set()

    for role_name in [str(name).strip() for name in season_focus.get("priority_roles", []) if str(name).strip()]:
        role = role_index.get(role_name)
        if role_name in seen:
            continue
        if role is None:
            # Evidence gate: name is in season_focus but has no appearances
            # in this season's chapters — drop it.
            dropped_names.append(role_name)
            continue
        priority_roles.append(role)
        seen.add(role_name)
        if len(priority_roles) >= limit:
            return priority_roles[:limit], dropped_names

    for item in top_roles:
        if item["role_name"] in seen:
            continue
        priority_roles.append(item)
        seen.add(item["role_name"])
        if len(priority_roles) >= limit:
            break

    return priority_roles[:limit], dropped_names


def get_season_pair_priority(season_focus: dict, left: str, right: str) -> int:
    for index, pair in enumerate(season_focus.get("priority_relationship_pairs", [])):
        normalized = [str(name).strip() for name in pair if str(name).strip()]
        if len(normalized) != 2:
            continue
        if frozenset(normalized) == frozenset({left, right}):
            return max(24 - index * 3, 12)
    return 0


def overlap_size(
    current_range: Tuple[Optional[int], Optional[int]],
    filter_range: Tuple[Optional[int], Optional[int]],
) -> int:
    current_start, current_end = current_range
    filter_start, filter_end = filter_range
    if current_start is None and current_end is None:
        return 0

    effective_current_start = current_start if current_start is not None else current_end
    effective_current_end = current_end if current_end is not None else current_start
    if effective_current_start is None or effective_current_end is None:
        return 0

    normalized_current_start = min(effective_current_start, effective_current_end)
    normalized_current_end = max(effective_current_start, effective_current_end)
    normalized_filter_start = filter_start if filter_start is not None else normalized_current_start
    normalized_filter_end = filter_end if filter_end is not None else normalized_current_end

    overlap_start = max(normalized_current_start, normalized_filter_start)
    overlap_end = min(normalized_current_end, normalized_filter_end)
    if overlap_end < overlap_start:
        return 0
    return overlap_end - overlap_start + 1


def season_relationship_score(
    relationship: dict,
    *,
    season_name: str,
    season_focus: dict,
    season_unit_range: Tuple[int, int],
    season_progress_range: Tuple[int, int],
    priority_role_names: Sequence[str],
    anchor_event_ids: Sequence[str],
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
) -> int:
    source_name = str(relationship.get("source_role_name", "")).strip()
    target_name = str(relationship.get("target_role_name", "")).strip()
    participants = {source_name, target_name}
    participants.discard("")
    priority_role_set = {name for name in priority_role_names if name}
    anchor_event_id_set = {event_id for event_id in anchor_event_ids if event_id}

    score = 0
    score += min(overlap_size(tuple(relationship["unit_span"]), season_unit_range), 40)
    score += min(overlap_size(tuple(relationship["progress_span"]), season_progress_range) // 10, 20)
    score += len(participants & priority_role_set) * 9
    score += min(
        sum(1 for beat in relationship.get("manual_beats", []) if beat.get("season_name") == season_name),
        3,
    ) * 6
    score += min(
        sum(1 for event_ref in relationship.get("key_events", []) if event_ref.get("event_id") in anchor_event_id_set),
        3,
    ) * 5
    if source_name and target_name:
        score += min(get_pair_priority(source_name, target_name, priority_pair_scores), 10)
        score += get_season_pair_priority(season_focus, source_name, target_name)

    if relationship.get("spotlight"):
        score += 5
    if spotlight_role and spotlight_role in participants:
        score += 4

    return score


def build_curated_relationship_configs(writer_focus: dict) -> List[dict]:
    configs: List[dict] = []
    raw_configs = writer_focus.get("curated_relationships", [])
    for index, item in enumerate(raw_configs):
        roles = [str(name).strip() for name in item.get("roles", []) if str(name).strip()]
        if len(roles) != 2:
            continue
        manual_beats = []
        for beat in item.get("manual_beats", []):
            phase_label = str(beat.get("phase_label", "")).strip()
            summary = str(beat.get("summary", "")).strip()
            if not phase_label or not summary:
                continue
            manual_beats.append(
                {
                    "season_name": str(beat.get("season_name", "")).strip() or None,
                    "phase_label": phase_label,
                    "summary": summary,
                    "event_keywords": [
                        str(keyword).strip()
                        for keyword in beat.get("event_keywords", [])
                        if str(keyword).strip()
                    ],
                    "location": str(beat.get("location", "")).strip() or None,
                }
            )
        configs.append(
            {
                "id": str(item.get("id") or f"curated-{index + 1}"),
                "order": index,
                "roles": roles,
                "kind": normalize_relationship_kind(item.get("kind", "主线")),
                "title": str(item.get("title") or f"{roles[0]}与{roles[1]}关系线").strip(),
                "focus": normalize_display_copy(item.get("focus", "")),
                "adaptation_value": normalize_display_copy(item.get("adaptation_value", "")),
                "manual_beats": manual_beats,
            }
        )

    if configs:
        return configs

    for index, item in enumerate(writer_focus.get("priority_pairs", [])[:8]):
        roles = [str(name).strip() for name in item.get("roles", []) if str(name).strip()]
        if len(roles) != 2:
            continue
        configs.append(
            {
                "id": str(item.get("id") or f"priority-{index + 1}"),
                "order": index,
                "roles": roles,
                "kind": normalize_relationship_kind(item.get("kind", "主线")),
                "title": f"{roles[0]}与{roles[1]}关系线",
                "focus": "",
                "adaptation_value": "",
                "manual_beats": [],
            }
        )
    return configs


def get_pair_priority(
    left: str,
    right: str,
    priority_pair_scores: Dict[frozenset[str], int],
) -> int:
    return priority_pair_scores.get(frozenset({left, right}), 0)


def is_spotlight_pair(left: str, right: str, spotlight_role: Optional[str]) -> bool:
    return bool(spotlight_role) and spotlight_role in {left, right}


def build_season_entries(unit_meta: Dict[int, dict]) -> List[dict]:
    by_season: Dict[str, dict] = {}
    for metadata in unit_meta.values():
        season_name = metadata.get("season_name")
        if not season_name:
            continue
        entry = by_season.setdefault(
            season_name,
            {
                "season_name": season_name,
                "unit_range": [metadata["unit_index"], metadata["unit_index"]],
                "progress_range": [metadata["progress_start"], metadata["progress_end"]],
            },
        )
        entry["unit_range"][0] = min(entry["unit_range"][0], metadata["unit_index"])
        entry["unit_range"][1] = max(entry["unit_range"][1], metadata["unit_index"])
        entry["progress_range"][0] = min(entry["progress_range"][0], metadata["progress_start"])
        entry["progress_range"][1] = max(entry["progress_range"][1], metadata["progress_end"])

    return sorted(by_season.values(), key=lambda item: (item["unit_range"][0], item["season_name"]))


def make_event_ref(
    event: UnifiedEvent,
    *,
    event_type_rules: Sequence[dict],
    unit_meta: Dict[int, dict],
) -> dict:
    units = get_event_units(event)
    unit_index = units[0] if units else None
    meta = unit_meta.get(unit_index or -1, {})
    event_type = classify_event_type(event, event_type_rules)

    # Collect all chapter titles this event spans — serves as audit evidence
    source_unit_titles = []
    for u in units:
        m = unit_meta.get(u)
        if m and m.get("unit_title"):
            source_unit_titles.append(m["unit_title"])

    return {
        "event_id": event.id,
        "name": event.name,
        "event_type": event_type,
        "unit_index": unit_index,
        "unit_title": meta.get("unit_title"),
        "season_name": meta.get("season_name"),
        "progress_start": event.progress_start,
        "progress_end": event.progress_end,
        "progress_label": event.progress_label,
        "location": event.location,
        "participants": sorted(event.participants),
        "description": event.description,
        "significance": event.significance,
        "source_unit_titles": source_unit_titles,
    }


def event_score(
    event_ref: dict,
    *,
    role_name: Optional[str] = None,
    writer_focus: Optional[dict] = None,
    priority_pair_scores: Optional[Dict[frozenset[str], int]] = None,
    spotlight_role: Optional[str] = None,
) -> int:
    type_weight = {
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
    score = (
        type_weight.get(event_ref.get("event_type", ""), 1)
        + min(len(event_ref.get("participants", [])), 4)
        + (1 if event_ref.get("location") else 0)
        + (1 if event_ref.get("significance") else 0)
    )

    if writer_focus:
        type_overrides = writer_focus.get("event_type_weights", {})
        if isinstance(type_overrides, dict):
            score += int(type_overrides.get(event_ref.get("event_type", ""), 0))

        if role_name:
            preferred_keywords = [
                str(keyword).strip()
                for keyword in writer_focus.get("role_event_preferences", {}).get(role_name, [])
                if str(keyword).strip()
            ]
            haystack = " ".join(
                [
                    str(event_ref.get("name", "")),
                    str(event_ref.get("description", "")),
                    str(event_ref.get("significance", "")),
                    str(event_ref.get("location", "")),
                ]
            )
            score += sum(2 for keyword in preferred_keywords if keyword in haystack)

    if spotlight_role and spotlight_role in event_ref.get("participants", []):
        score += 3

    if role_name and priority_pair_scores:
        for participant in event_ref.get("participants", []):
            if participant == role_name:
                continue
            score += get_pair_priority(role_name, participant, priority_pair_scores)

    return score


def summarize_locations(event_refs: Sequence[dict], limit: int = 4) -> List[str]:
    counter = Counter(ref["location"] for ref in event_refs if ref.get("location"))
    return [name for name, _ in counter.most_common(limit)]


def event_ref_haystack(event_ref: dict) -> str:
    return " ".join(
        str(part)
        for part in [
            event_ref.get("name", ""),
            event_ref.get("description", ""),
            event_ref.get("significance", ""),
            event_ref.get("location", ""),
            event_ref.get("unit_title", ""),
            event_ref.get("season_name", ""),
        ]
        if part
    )


def classify_phase(
    *,
    relation: Optional[UnifiedRelation],
    event_ref: Optional[dict],
    phase_rules: Sequence[dict],
    shared_event_index: int,
) -> str:
    texts: List[str] = []
    actions: List[str] = []

    if relation is not None:
        actions.extend(relation.action_types)
        texts.extend(relation.contexts[:3])
        if relation.primary_action:
            texts.append(relation.primary_action)

    if event_ref is not None:
        texts.extend(
            [
                str(event_ref.get("name", "")),
                str(event_ref.get("event_type", "")),
                str(event_ref.get("description", "")),
                str(event_ref.get("significance", "")),
            ]
        )

    haystack = " ".join(texts)

    best_label = None
    best_score = 0
    for rule in phase_rules:
        label = str(rule.get("label", "")).strip()
        if not label:
            continue
        score = 0
        for keyword in rule.get("keywords", []):
            normalized = str(keyword).strip()
            if normalized and normalized in haystack:
                score += 1
        for action in rule.get("actions", []):
            normalized = str(action).strip()
            if normalized and normalized in actions:
                score += 2
        if score > best_score:
            best_score = score
            best_label = label

    if best_label:
        return best_label
    if shared_event_index == 0:
        return "初识"
    if relation is not None and relation.primary_action:
        return relation.primary_action
    if event_ref is not None and event_ref.get("event_type"):
        return str(event_ref["event_type"])
    return "关系推进"


def build_relationship_phases(
    *,
    role_name: str,
    relation: UnifiedRelation,
    shared_events: Sequence[dict],
    phase_rules: Sequence[dict],
    role_name_to_id: Dict[str, str],
) -> List[dict]:
    counterpart_name = relation.to_entity if relation.from_entity == role_name else relation.from_entity
    counterpart_id = role_name_to_id.get(counterpart_name, counterpart_name)
    phases: List[dict] = []
    previous_label = None

    if shared_events:
        for index, event_ref in enumerate(shared_events):
            phase_label = classify_phase(
                relation=relation,
                event_ref=event_ref,
                phase_rules=phase_rules,
                shared_event_index=index,
            )
            if phase_label == previous_label:
                continue
            previous_label = phase_label
            phases.append(
                {
                    "relation_id": relation.id,
                    "counterpart_id": counterpart_id,
                    "counterpart_name": counterpart_name,
                    "phase_label": phase_label,
                    "trigger_event_id": event_ref["event_id"],
                    "trigger_event_name": event_ref["name"],
                    "unit_index": event_ref["unit_index"],
                    "progress_start": event_ref["progress_start"],
                    "location": event_ref["location"],
                    "summary": f"{role_name}与{counterpart_name}在“{event_ref['name']}”中进入“{phase_label}”阶段。",
                }
            )
            if len(phases) >= 4:
                break
        return phases

    phase_label = classify_phase(
        relation=relation,
        event_ref=None,
        phase_rules=phase_rules,
        shared_event_index=0,
    )
    units = get_relation_units(relation)
    phases.append(
        {
            "relation_id": relation.id,
            "counterpart_id": counterpart_id,
            "counterpart_name": counterpart_name,
            "phase_label": phase_label,
            "trigger_event_id": None,
            "trigger_event_name": None,
            "unit_index": units[0] if units else None,
            "progress_start": relation.progress_start,
            "location": None,
            "summary": f"{role_name}与{counterpart_name}主要呈现“{phase_label}”关系。",
        }
    )
    return phases


def build_character_arc(
    *,
    role: UnifiedRole,
    role_name_to_id: Dict[str, str],
    unit_meta: Dict[int, dict],
    role_events: Sequence[dict],
    role_relations: Sequence[UnifiedRelation],
    pair_event_map: Dict[frozenset[str], List[dict]],
    phase_rules: Sequence[dict],
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
) -> dict:
    units = get_role_units(role)
    seasons = []
    for unit in units:
        season_name = unit_meta.get(unit, {}).get("season_name")
        if season_name and season_name not in seasons:
            seasons.append(season_name)

    sorted_events = sorted(
        role_events,
        key=lambda ref: (
            ref["progress_start"] if ref["progress_start"] is not None else 10**12,
            ref["unit_index"] if ref["unit_index"] is not None else 10**12,
            ref["name"],
        ),
    )
    ranked_events = sorted(
        sorted_events,
        key=lambda ref: (
            -event_score(
                ref,
                role_name=role.canonical_name,
                writer_focus=writer_focus,
                priority_pair_scores=priority_pair_scores,
                spotlight_role=spotlight_role,
            ),
            ref["progress_start"] or 10**12,
        ),
    )
    chosen_event_ids = {ref["event_id"] for ref in ranked_events[:8]}
    key_events = [ref for ref in sorted_events if ref["event_id"] in chosen_event_ids]

    relationship_phases: List[dict] = []
    seen_pairs = set()
    for relation in role_relations:
        counterpart_name = relation.to_entity if relation.from_entity == role.canonical_name else relation.from_entity
        if counterpart_name in seen_pairs:
            continue
        seen_pairs.add(counterpart_name)
        shared_events = pair_event_map.get(frozenset({role.canonical_name, counterpart_name}), [])
        relationship_phases.extend(
            build_relationship_phases(
                role_name=role.canonical_name,
                relation=relation,
                shared_events=shared_events,
                phase_rules=phase_rules,
                role_name_to_id=role_name_to_id,
            )
        )

    relationship_phases.sort(
        key=lambda item: (
            0 if get_pair_priority(role.canonical_name, item["counterpart_name"], priority_pair_scores) > 0 else 1,
            -get_pair_priority(role.canonical_name, item["counterpart_name"], priority_pair_scores),
            0 if spotlight_role and role.canonical_name == spotlight_role else 1,
            item["progress_start"] if item["progress_start"] is not None else 10**12,
            item["unit_index"] if item["unit_index"] is not None else 10**12,
            item["counterpart_name"],
        )
    )

    main_counterparts = unique_names(item["counterpart_name"] for item in relationship_phases)[:4]
    key_locations = summarize_locations(sorted_events, limit=5)
    progress_values = [ref["progress_start"] for ref in sorted_events if ref["progress_start"] is not None]
    progress_span = [min(progress_values), max(progress_values)] if progress_values else [None, None]

    if main_counterparts:
        summary = (
            f"{role.canonical_name}在{('、'.join(seasons) if seasons else '当前范围')}的主线活动，"
            f"主要围绕{('、'.join(main_counterparts[:3]))}展开，"
            f"关键场域集中在{('、'.join(key_locations[:3]) if key_locations else '多处场景')}。"
        )
    else:
        summary = (
            f"{role.canonical_name}在{('、'.join(seasons) if seasons else '当前范围')}持续推进主线，"
            f"关键场域集中在{('、'.join(key_locations[:3]) if key_locations else '多处场景')}。"
        )

    return {
        "role_id": role.id,
        "role_name": role.canonical_name,
        "spotlight": role.canonical_name == spotlight_role,
        "aliases": sorted(name for name in role.all_names if name != role.canonical_name),
        "primary_power": role.primary_power,
        "description": role.description,
        "unit_span": [units[0], units[-1]] if units else [None, None],
        "progress_span": progress_span,
        "season_names": seasons,
        "key_locations": key_locations,
        "key_events": key_events,
        "relationship_phases": relationship_phases[:12],
        "summary": summary,
    }


def build_conflict_chains(
    *,
    relations: Iterable[UnifiedRelation],
    role_name_to_id: Dict[str, str],
    pair_event_map: Dict[frozenset[str], List[dict]],
    phase_rules: Sequence[dict],
    conflict_actions: Sequence[str],
    unit_meta: Dict[int, dict],
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
) -> List[dict]:
    conflict_action_set = {str(action).strip() for action in conflict_actions if str(action).strip()}
    conflict_labels = set(conflict_action_set).union({"冲突", "对立", "分离"})
    chains: List[dict] = []

    for relation in relations:
        if not relation.from_entity or not relation.to_entity:
            continue
        pair_priority = get_pair_priority(relation.from_entity, relation.to_entity, priority_pair_scores)
        spotlight = is_spotlight_pair(relation.from_entity, relation.to_entity, spotlight_role)

        shared_events = pair_event_map.get(frozenset({relation.from_entity, relation.to_entity}), [])
        shared_events = sorted(
            shared_events,
            key=lambda ref: (
                ref["progress_start"] if ref["progress_start"] is not None else 10**12,
                ref["unit_index"] if ref["unit_index"] is not None else 10**12,
                ref["name"],
            ),
        )

        beats: List[dict] = []
        conflict_like = relation.primary_action in conflict_action_set
        conflict_indexes: List[int] = []
        previous_label = None
        for index, event_ref in enumerate(shared_events):
            phase_label = classify_phase(
                relation=relation,
                event_ref=event_ref,
                phase_rules=phase_rules,
                shared_event_index=index,
            )
            if phase_label == previous_label:
                continue
            previous_label = phase_label
            if phase_label in conflict_labels:
                conflict_like = True
                conflict_indexes.append(len(beats))
            beats.append(
                {
                    "phase_label": phase_label,
                    "event_id": event_ref["event_id"],
                    "event_name": event_ref["name"],
                    "unit_index": event_ref["unit_index"],
                    "unit_title": event_ref["unit_title"],
                    "season_name": event_ref["season_name"],
                    "progress_start": event_ref["progress_start"],
                    "location": event_ref["location"],
                    "action_types": relation.action_types,
                    "summary": f"{relation.from_entity}与{relation.to_entity}在“{event_ref['name']}”中进入“{phase_label}”阶段。",
                }
            )

        if not conflict_like:
            continue

        if pair_priority <= 0 and not spotlight and len(conflict_indexes) < 2 and relation.interaction_count < 2:
            continue

        if conflict_indexes:
            start = max(0, conflict_indexes[0] - 1)
            end = min(len(beats), conflict_indexes[-1] + 2)
            visible_beats = beats[start:end]
        else:
            visible_beats = beats[:6]

        seasons = []
        for beat in visible_beats:
            season_name = beat.get("season_name")
            if season_name and season_name not in seasons:
                seasons.append(season_name)

        units = get_relation_units(relation)
        progress_values = [beat["progress_start"] for beat in visible_beats if beat["progress_start"] is not None]
        progress_span = [min(progress_values), max(progress_values)] if progress_values else [relation.progress_start, relation.progress_end]
        title = f"{relation.from_entity}与{relation.to_entity}的关系冲突链"
        locations = summarize_locations(shared_events, limit=4)
        conflict_beat_count = max(1, len(conflict_indexes))
        summary = (
            f"{relation.from_entity}与{relation.to_entity}的关系主轴以“{relation.primary_action or '关系推进'}”为核心，"
            f"在{('、'.join(locations[:3]) if locations else '多处场景')}形成了{conflict_beat_count}处关键张力节点。"
        )

        chains.append(
            {
                "id": relation.id,
                "title": title,
                "spotlight": spotlight,
                "source_role_id": role_name_to_id.get(relation.from_entity, relation.from_entity),
                "target_role_id": role_name_to_id.get(relation.to_entity, relation.to_entity),
                "source_role_name": relation.from_entity,
                "target_role_name": relation.to_entity,
                "conflict_type": relation.primary_action,
                "action_types": relation.action_types,
                "unit_span": [units[0], units[-1]] if units else [None, None],
                "progress_span": progress_span,
                "season_names": seasons,
                "locations": locations,
                "tension_score": max(
                    1,
                    min(10, conflict_beat_count * 2 + min(len(relation.action_types), 4) + min(pair_priority, 3) + (2 if spotlight else 0)),
                ),
                "beats": visible_beats[:8],
                "summary": summary,
            }
        )

    deduped_chains: Dict[frozenset[str], dict] = {}
    for chain in chains:
        pair_key = frozenset({chain["source_role_name"], chain["target_role_name"]})
        current_priority = get_pair_priority(chain["source_role_name"], chain["target_role_name"], priority_pair_scores)
        current_rank = (
            1 if chain.get("spotlight") else 0,
            current_priority,
            chain["tension_score"],
            len(chain["beats"]),
            1 if spotlight_role and chain["source_role_name"] == spotlight_role else 0,
        )
        existing = deduped_chains.get(pair_key)
        if existing is None:
            deduped_chains[pair_key] = chain
            continue
        existing_priority = get_pair_priority(existing["source_role_name"], existing["target_role_name"], priority_pair_scores)
        existing_rank = (
            1 if existing.get("spotlight") else 0,
            existing_priority,
            existing["tension_score"],
            len(existing["beats"]),
            1 if spotlight_role and existing["source_role_name"] == spotlight_role else 0,
        )
        if current_rank > existing_rank:
            deduped_chains[pair_key] = chain

    chains = list(deduped_chains.values())

    chains.sort(
        key=lambda item: (
            0 if item.get("spotlight") else 1,
            0 if get_pair_priority(item["source_role_name"], item["target_role_name"], priority_pair_scores) > 0 else 1,
            -get_pair_priority(item["source_role_name"], item["target_role_name"], priority_pair_scores),
            0 if item["conflict_type"] in conflict_action_set else 1,
            -item["tension_score"],
            item["title"],
        )
    )
    return chains


def build_curated_relationships(
    *,
    curated_configs: Sequence[dict],
    relations_by_pair: Dict[frozenset[str], List[UnifiedRelation]],
    pair_event_map: Dict[frozenset[str], List[dict]],
    all_event_refs: Sequence[dict],
    event_ref_index: Dict[str, dict],
    phase_rules: Sequence[dict],
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    role_name_to_id: Dict[str, str],
    season_meta: Dict[str, dict],
    spotlight_role: Optional[str],
) -> List[dict]:
    curated_relationships: List[dict] = []

    for config in curated_configs:
        source_name, target_name = config["roles"]
        pair_key = frozenset({source_name, target_name})
        shared_events = sorted(
            pair_event_map.get(pair_key, []),
            key=lambda ref: (
                ref["progress_start"] if ref["progress_start"] is not None else 10**12,
                ref["unit_index"] if ref["unit_index"] is not None else 10**12,
                ref["name"],
            ),
        )
        pair_relations = relations_by_pair.get(pair_key, [])
        has_manual_beats = bool(config.get("manual_beats"))
        if not shared_events and not pair_relations and not has_manual_beats:
            continue

        manual_beats: List[dict] = []
        if config.get("manual_beats"):
            fallback_candidates = [
                ref
                for ref in all_event_refs
                if source_name in ref.get("participants", []) or target_name in ref.get("participants", [])
            ]
            candidate_pool = shared_events if shared_events else fallback_candidates
            for beat in config["manual_beats"]:
                season_name = beat.get("season_name")
                beat_candidates = candidate_pool
                if season_name:
                    season_filtered = [
                        ref for ref in candidate_pool if ref.get("season_name") == season_name
                    ]
                    if season_filtered:
                        beat_candidates = season_filtered
                    else:
                        beat_candidates = []

                best_event = None
                best_score = 0
                for ref in beat_candidates:
                    score = 0
                    haystack = event_ref_haystack(ref)
                    if season_name and ref.get("season_name") == season_name:
                        score += 2
                    if beat.get("location") and ref.get("location") == beat["location"]:
                        score += 2
                    if source_name in ref.get("participants", []):
                        score += 1
                    if target_name in ref.get("participants", []):
                        score += 1
                    keywords = beat.get("event_keywords", [])
                    if not keywords:
                        score += 1
                    for keyword in keywords:
                        if keyword in str(ref.get("name", "")):
                            score += 3
                        elif keyword in haystack:
                            score += 1
                    if score > best_score:
                        best_score = score
                        best_event = ref

                beat_unit_index = None
                beat_progress_start = None
                beat_location = beat.get("location")
                beat_event_id = None
                beat_event_name = None
                if best_event is not None and best_score > 0:
                    beat_unit_index = best_event.get("unit_index")
                    beat_progress_start = best_event.get("progress_start")
                    beat_location = best_event.get("location") or beat_location
                    beat_event_id = best_event.get("event_id")
                    beat_event_name = best_event.get("name")
                elif season_name and season_name in season_meta:
                    beat_unit_index = season_meta[season_name]["unit_range"][0]
                    beat_progress_start = season_meta[season_name]["progress_range"][0]

                manual_beats.append(
                    {
                        "season_name": season_name,
                        "phase_label": beat["phase_label"],
                        "summary": beat["summary"],
                        "event_id": beat_event_id,
                        "event_name": beat_event_name,
                        "unit_index": beat_unit_index,
                        "progress_start": beat_progress_start,
                        "location": beat_location,
                    }
                )

        primary_relation = max(
            pair_relations,
            key=lambda relation: (
                relation.interaction_count,
                len(relation.action_types),
                1 if relation.from_entity == source_name else 0,
            ),
            default=None,
        )

        if primary_relation is not None:
            relationship_phases = build_relationship_phases(
                role_name=source_name,
                relation=primary_relation,
                shared_events=shared_events,
                phase_rules=phase_rules,
                role_name_to_id=role_name_to_id,
            )
        else:
            relationship_phases = []
            previous_label = None
            for index, event_ref in enumerate(shared_events):
                phase_label = classify_phase(
                    relation=None,
                    event_ref=event_ref,
                    phase_rules=phase_rules,
                    shared_event_index=index,
                )
                if phase_label == previous_label:
                    continue
                previous_label = phase_label
                relationship_phases.append(
                    {
                        "relation_id": config["id"],
                        "counterpart_id": role_name_to_id.get(target_name, target_name),
                        "counterpart_name": target_name,
                        "phase_label": phase_label,
                        "trigger_event_id": event_ref["event_id"],
                        "trigger_event_name": event_ref["name"],
                        "unit_index": event_ref["unit_index"],
                        "progress_start": event_ref["progress_start"],
                        "location": event_ref["location"],
                        "summary": f"{source_name}与{target_name}在“{event_ref['name']}”中进入“{phase_label}”阶段。",
                    }
                )

        ranked_events = sorted(
            shared_events,
            key=lambda ref: (
                -(
                    event_score(
                        ref,
                        role_name=source_name,
                        writer_focus=writer_focus,
                        priority_pair_scores=priority_pair_scores,
                        spotlight_role=spotlight_role,
                    )
                    + event_score(
                        ref,
                        role_name=target_name,
                        writer_focus=writer_focus,
                        priority_pair_scores=priority_pair_scores,
                        spotlight_role=spotlight_role,
                    )
                    + (4 if source_name in ref.get("participants", []) and target_name in ref.get("participants", []) else 0)
                ),
                ref["progress_start"] if ref["progress_start"] is not None else 10**12,
                ref["unit_index"] if ref["unit_index"] is not None else 10**12,
                ref["name"],
            ),
        )
        key_events: List[dict] = []
        seen_event_ids = set()
        for beat in manual_beats:
            event_id = beat.get("event_id")
            if not event_id or event_id in seen_event_ids or event_id not in event_ref_index:
                continue
            key_events.append(event_ref_index[event_id])
            seen_event_ids.add(event_id)
        for ref in ranked_events:
            if ref["event_id"] in seen_event_ids:
                continue
            key_events.append(ref)
            seen_event_ids.add(ref["event_id"])
            if len(key_events) >= 5:
                break

        units = [ref["unit_index"] for ref in shared_events if ref["unit_index"] is not None]
        units.extend(beat["unit_index"] for beat in manual_beats if beat.get("unit_index") is not None)
        if not units and primary_relation is not None:
            units = get_relation_units(primary_relation)
        progress_values = [ref["progress_start"] for ref in shared_events if ref["progress_start"] is not None]
        progress_values.extend(
            beat["progress_start"] for beat in manual_beats if beat.get("progress_start") is not None
        )
        if not progress_values and primary_relation is not None:
            progress_values = [value for value in [primary_relation.progress_start, primary_relation.progress_end] if value is not None]

        season_names = unique_names(
            [
                *(beat.get("season_name") for beat in manual_beats if beat.get("season_name")),
                *(ref.get("season_name") for ref in shared_events if ref.get("season_name")),
            ]
        )
        key_locations = unique_names(
            [
                *(beat.get("location") for beat in manual_beats if beat.get("location")),
                *summarize_locations(shared_events, limit=4),
            ]
        )
        summary = config["focus"] or (
            f"{source_name}与{target_name}的关系主要在"
            f"{('、'.join(season_names) if season_names else '当前范围')}推进，"
            f"关键场域集中在{('、'.join(key_locations[:3]) if key_locations else '多处场景')}。"
        )
        adaptation_value = config["adaptation_value"] or (
            f"适合围绕{source_name}与{target_name}补强阶段变化和关键事件承接。"
        )

        curated_relationships.append(
            {
                "id": config["id"],
                "title": config["title"],
                "kind": config["kind"],
                "spotlight": is_spotlight_pair(source_name, target_name, spotlight_role),
                "source_role_id": role_name_to_id.get(source_name, source_name),
                "target_role_id": role_name_to_id.get(target_name, target_name),
                "source_role_name": source_name,
                "target_role_name": target_name,
                "unit_span": [min(units), max(units)] if units else [None, None],
                "progress_span": [min(progress_values), max(progress_values)] if progress_values else [None, None],
                "season_names": season_names,
                "key_locations": key_locations,
                "phase_labels": unique_names(
                    item["phase_label"] for item in (manual_beats if manual_beats else relationship_phases)
                ),
                "manual_beats": manual_beats,
                "key_events": key_events,
                "summary": summary,
                "adaptation_value": adaptation_value,
                "sort_order": config.get("order", 10**6),
            }
        )

    curated_relationships.sort(
        key=lambda item: (
            item.get("sort_order", 10**6),
            0 if item.get("spotlight") else 1,
            0 if get_pair_priority(item["source_role_name"], item["target_role_name"], priority_pair_scores) > 0 else 1,
            -get_pair_priority(item["source_role_name"], item["target_role_name"], priority_pair_scores),
            item["progress_span"][0] if item["progress_span"][0] is not None else 10**12,
            item["title"],
        )
    )
    return curated_relationships


def find_events_for_pattern(
    *,
    event_refs: Sequence[dict],
    focus_roles: Sequence[str],
    keywords: Sequence[str],
    unit_range: Optional[List[int]] = None,
    event_names: Optional[List[str]] = None,
) -> List[dict]:
    """Find events matching a foreshadowing pattern.

    Supports two modes:
    1. keyword + role matching (original)
    2. explicit event_names / unit_range for precise targeting

    When *unit_range* is provided only events whose unit_index falls inside
    ``[min, max]`` are considered.  When *event_names* is given, events
    whose name contains any of those strings are automatically included.
    """
    normalized_keywords = [str(kw).strip() for kw in keywords if str(kw).strip()]
    normalized_roles = {str(n).strip() for n in focus_roles if str(n).strip()}
    normalized_event_names = [str(n).strip() for n in (event_names or []) if str(n).strip()]
    matches: List[dict] = []
    for event_ref in event_refs:
        uid = event_ref.get("unit_index")
        if unit_range and uid is not None:
            if uid < unit_range[0] or uid > unit_range[1]:
                continue
        haystack = " ".join(
            part
            for part in [
                event_ref.get("name") or "",
                event_ref.get("description") or "",
                event_ref.get("significance") or "",
                event_ref.get("location") or "",
            ]
            if part
        )
        name_hit = normalized_event_names and any(
            en in (event_ref.get("name") or "") for en in normalized_event_names
        )
        role_hit = not normalized_roles or any(
            role in event_ref.get("participants", []) for role in normalized_roles
        )
        keyword_hit = normalized_keywords and any(kw in haystack for kw in normalized_keywords)
        if name_hit or (role_hit and keyword_hit):
            matches.append(event_ref)
    return matches


def _score_foreshadow_event(
    event_ref: dict,
    *,
    keywords: Sequence[str],
    focus_roles: Sequence[str],
) -> int:
    """Score an event for relevance to a foreshadowing pattern (higher = better)."""
    score = 0
    name = event_ref.get("name") or ""
    sig = event_ref.get("significance") or ""
    desc = event_ref.get("description") or ""
    participants = event_ref.get("participants", [])
    for kw in keywords:
        if kw in name:
            score += 5
        if kw in sig:
            score += 3
        if kw in desc:
            score += 1
    for role in focus_roles:
        if role in participants:
            score += 3
    etype = event_ref.get("event_type") or ""
    for t in ("揭示", "立势", "转折", "冲突", "会见", "别离"):
        if t in etype:
            score += 2
    n = len(participants)
    if 1 <= n <= 4:
        score += 2
    elif n > 10:
        score -= 3
    return score


def _dedup_events(events: List[dict], *, max_count: int) -> List[dict]:
    """Keep up to *max_count* unique events spread across different units."""
    seen: set = set()
    unique: List[dict] = []
    for ev in events:
        key = (ev.get("name"), ev.get("unit_index"))
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    if len(unique) <= max_count:
        return unique
    by_unit: Dict[int, List[dict]] = {}
    for ev in unique:
        by_unit.setdefault(ev.get("unit_index") or 0, []).append(ev)
    picked: List[dict] = [lst[0] for lst in sorted(by_unit.values(), key=lambda lst: lst[0].get("unit_index") or 0)]
    if len(picked) > max_count:
        step = max(1, len(picked) // max_count)
        picked = picked[::step][:max_count]
    return picked[:max_count]


def build_foreshadowing_threads(
    *,
    event_refs: Sequence[dict],
    patterns: Sequence[dict],
    spotlight_role: Optional[str],
) -> List[dict]:
    threads: List[dict] = []
    for pattern in patterns:
        label = str(pattern.get("label", "")).strip()
        if not label:
            continue
        focus_roles = [str(name).strip() for name in pattern.get("focus_roles", []) if str(name).strip()]

        clue_kw = pattern.get("clue_keywords", [])
        payoff_kw = pattern.get("payoff_keywords", [])

        clue_events = find_events_for_pattern(
            event_refs=event_refs,
            focus_roles=focus_roles,
            keywords=clue_kw,
            unit_range=pattern.get("clue_unit_range"),
            event_names=pattern.get("clue_event_names"),
        )
        payoff_events = find_events_for_pattern(
            event_refs=event_refs,
            focus_roles=focus_roles,
            keywords=payoff_kw,
            unit_range=pattern.get("payoff_unit_range"),
            event_names=pattern.get("payoff_event_names"),
        )

        # score and sort by relevance
        clue_events.sort(
            key=lambda r: (
                -_score_foreshadow_event(r, keywords=clue_kw, focus_roles=focus_roles),
                r.get("progress_start") or 10**12,
                r.get("unit_index") or 10**12,
            )
        )
        payoff_events.sort(
            key=lambda r: (
                -_score_foreshadow_event(r, keywords=payoff_kw, focus_roles=focus_roles),
                r.get("progress_start") or 10**12,
                r.get("unit_index") or 10**12,
            )
        )

        if not clue_events or not payoff_events:
            continue

        first_clue_unit = min(
            (r.get("unit_index") for r in clue_events if r.get("unit_index") is not None),
            default=None,
        )
        if first_clue_unit is not None:
            payoff_events = [
                r for r in payoff_events
                if r.get("unit_index") is None or r["unit_index"] >= first_clue_unit
            ]
        if not payoff_events:
            continue

        clue_events = _dedup_events(clue_events, max_count=5)
        payoff_events = _dedup_events(payoff_events, max_count=5)

        # chronological order for display
        for grp in (clue_events, payoff_events):
            grp.sort(key=lambda r: (r.get("progress_start") or 10**12, r.get("unit_index") or 10**12))

        seasons: List[str] = []
        for grp in (clue_events, payoff_events):
            for ev in grp:
                sn = ev.get("season_name")
                if sn and sn not in seasons:
                    seasons.append(sn)

        all_evts = clue_events + payoff_events
        prog = [r["progress_start"] for r in all_evts if r["progress_start"] is not None]
        progress_span = [min(prog), max(prog)] if prog else [None, None]
        units = [r["unit_index"] for r in all_evts if r["unit_index"] is not None]

        threads.append(
            {
                "id": str(pattern.get("id") or label),
                "label": label,
                "spotlight": bool(spotlight_role) and spotlight_role in focus_roles,
                "focus_roles": focus_roles,
                "motif_keywords": [str(k).strip() for k in pattern.get("motif_keywords", []) if str(k).strip()],
                "unit_span": [min(units), max(units)] if units else [None, None],
                "progress_span": progress_span,
                "season_names": seasons,
                "clue_events": clue_events,
                "payoff_events": payoff_events,
                "summary": (
                    f"{label}在{('、'.join(seasons) if seasons else '当前范围')}形成“前段埋线，后段兑现”的推进结构，"
                    f"重点角色包括{('、'.join(focus_roles) if focus_roles else '多位人物')}。"
                ),
            }
        )

    threads.sort(key=lambda item: (0 if item.get("spotlight") else 1, item["label"]))
    return threads

def focused_event_score(
    event_ref: dict,
    *,
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
    name_occurrence_counts: Optional[Dict[str, int]] = None,
) -> int:
    score = event_score(
        event_ref,
        role_name=spotlight_role,
        writer_focus=writer_focus,
        priority_pair_scores=priority_pair_scores,
        spotlight_role=spotlight_role,
    )
    # Penalize event names that appear in many chapters (likely references,
    # not distinct events).  A name appearing in >5 chapters is suspicious;
    # each extra occurrence beyond 5 costs 2 points, capped at -30.
    if name_occurrence_counts:
        event_name = str(event_ref.get("name", "")).strip()
        name_freq = name_occurrence_counts.get(event_name, 1)
        if name_freq > 5:
            score -= min(name_freq - 5, 15) * 2
    participants = [str(name).strip() for name in event_ref.get("participants", []) if str(name).strip()]
    participant_count = len(participants)
    priority_characters = {
        str(name).strip()
        for name in writer_focus.get("priority_characters", [])
        if str(name).strip()
    }
    if participant_count == 0:
        score -= 2
    elif participant_count <= 4:
        score += 4
    elif participant_count <= 8:
        score += 2
    elif participant_count <= 12:
        score -= 4
    elif participant_count <= 20:
        score -= 14
    else:
        score -= 28

    type_bonus = {
        "冲突": 4,
        "揭示": 4,
        "立势": 4,
        "师承": 3,
        "迁移": 3,
        "遭遇": 3,
        "护持": 3,
        "指点": 2,
        "会见": 1,
        "对话": 1,
    }
    score += type_bonus.get(str(event_ref.get("event_type", "")), 0)

    if spotlight_role and spotlight_role in participants:
        score += 3
    elif spotlight_role:
        score -= 3

    priority_hits = [name for name in participants if name in priority_characters]
    score += min(len(priority_hits), 3) * 3

    strongest_pair_bonus = 0
    for index, left in enumerate(priority_hits):
        for right in priority_hits[index + 1 :]:
            strongest_pair_bonus = max(
                strongest_pair_bonus,
                get_pair_priority(left, right, priority_pair_scores),
            )
    score += min(strongest_pair_bonus, 10)

    if event_ref.get("location"):
        score += 1

    return score


def extract_focus_roles(
    event_ref: dict,
    *,
    writer_focus: dict,
    spotlight_role: Optional[str],
    limit: int = 3,
) -> List[str]:
    participants = [str(name).strip() for name in event_ref.get("participants", []) if str(name).strip()]
    priority_characters = [
        str(name).strip()
        for name in writer_focus.get("priority_characters", [])
        if str(name).strip()
    ]

    ordered: List[str] = []
    if spotlight_role and spotlight_role in participants:
        ordered.append(spotlight_role)
    for name in priority_characters:
        if name in participants and name not in ordered:
            ordered.append(name)
        if len(ordered) >= limit:
            return ordered[:limit]
    for name in participants:
        if name not in ordered:
            ordered.append(name)
        if len(ordered) >= limit:
            break
    return ordered[:limit]


def match_relationships_for_event(
    event_ref: dict,
    *,
    curated_relationships: Sequence[dict],
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
    limit: int = 3,
) -> List[dict]:
    participants = {
        str(name).strip()
        for name in event_ref.get("participants", [])
        if str(name).strip()
    }
    ranked: List[Tuple[int, dict]] = []

    for item in curated_relationships:
        source_name = str(item.get("source_role_name", "")).strip()
        target_name = str(item.get("target_role_name", "")).strip()
        pair = {source_name, target_name}
        overlap = len(pair & participants)
        if overlap == 0:
            continue

        score = 0
        if overlap == 2:
            score += 10
        elif spotlight_role and spotlight_role in participants and spotlight_role in pair:
            score += 5
        else:
            continue

        score += get_pair_priority(source_name, target_name, priority_pair_scores)
        if item.get("spotlight"):
            score += 3
        ranked.append((score, item))

    ranked.sort(key=lambda pair: (-pair[0], pair[1].get("title", "")))
    return [item for _, item in ranked[:limit]]


def screenplay_event_score(
    event_ref: dict,
    *,
    season_curated: Sequence[dict],
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
    name_occurrence_counts: Optional[Dict[str, int]] = None,
) -> int:
    score = focused_event_score(
        event_ref,
        writer_focus=writer_focus,
        priority_pair_scores=priority_pair_scores,
        spotlight_role=spotlight_role,
        name_occurrence_counts=name_occurrence_counts,
    )
    matched_relationships = match_relationships_for_event(
        event_ref,
        curated_relationships=season_curated,
        priority_pair_scores=priority_pair_scores,
        spotlight_role=spotlight_role,
        limit=3,
    )
    if matched_relationships:
        score += len(matched_relationships) * 4
        if any(item.get("spotlight") for item in matched_relationships):
            score += 3
    return score


def build_story_beat_summary(
    *,
    beat_type: str,
    event_ref: dict,
    spotlight_role: Optional[str],
) -> str:
    participants = [str(name).strip() for name in event_ref.get("participants", []) if str(name).strip()]
    location = event_ref.get("location")
    focus_pair = None
    if spotlight_role and spotlight_role in participants:
        counterparts = [name for name in participants if name != spotlight_role]
        if counterparts:
            focus_pair = f"{spotlight_role}与{counterparts[0]}"
        else:
            focus_pair = spotlight_role
    elif len(participants) >= 2:
        focus_pair = f"{participants[0]}与{participants[1]}"
    elif participants:
        focus_pair = participants[0]
    elif location:
        focus_pair = location
    else:
        focus_pair = "本季主线"

    if beat_type == "opening":
        return f"建议用“{event_ref['name']}”做开场钩子，先把{focus_pair}在{location or '当前场域'}立住。"
    if beat_type == "midpoint":
        return f"建议把“{event_ref['name']}”作为中段转折，推动{focus_pair}进入新的关系或处境阶段。"
    return f"建议用“{event_ref['name']}”承接后段收束，让{focus_pair}在{location or '关键场域'}形成落点。"


def build_story_beats(
    *,
    season_events: Sequence[dict],
    season_curated: Sequence[dict],
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
    globally_used_names: Optional[set[str]] = None,
    name_occurrence_counts: Optional[Dict[str, int]] = None,
) -> List[dict]:
    if not season_events:
        return []

    _globally_used = globally_used_names or set()

    ranked_events = sorted(
        season_events,
        key=lambda ref: (
            -screenplay_event_score(
                ref,
                season_curated=season_curated,
                writer_focus=writer_focus,
                priority_pair_scores=priority_pair_scores,
                spotlight_role=spotlight_role,
                name_occurrence_counts=name_occurrence_counts,
            ),
            ref.get("progress_start") if ref.get("progress_start") is not None else 10**12,
            ref.get("unit_index") if ref.get("unit_index") is not None else 10**12,
            ref.get("name", ""),
        ),
    )

    progress_values = [ref.get("progress_start") for ref in season_events if ref.get("progress_start") is not None]
    if progress_values:
        start = min(progress_values)
        end = max(progress_values)
    else:
        unit_values = [ref.get("unit_index") for ref in season_events if ref.get("unit_index") is not None]
        start = min(unit_values) if unit_values else 0
        end = max(unit_values) if unit_values else start

    span = max(end - start, 1)

    def event_position(event_ref: dict) -> float:
        value = event_ref.get("progress_start")
        if value is None:
            value = event_ref.get("unit_index")
        if value is None:
            return float(start)
        return float(value)

    windows = [
        ("opening", "开场钩子", lambda pos: pos <= start + span * 0.3),
        ("midpoint", "中段转折", lambda pos: start + span * 0.3 < pos < start + span * 0.7),
        ("payoff", "收束落点", lambda pos: pos >= start + span * 0.7),
    ]

    selected_ids: set[str] = set()
    selected_names: set[str] = set()
    beats: List[dict] = []
    for beat_type, label, predicate in windows:
        # Prefer events whose name is fresh (not used in this season AND not used
        # in previous seasons)
        candidates = [
            ref
            for ref in ranked_events
            if ref.get("event_id") not in selected_ids
            and ref.get("name", "") not in selected_names
            and ref.get("name", "") not in _globally_used
            and predicate(event_position(ref))
        ]
        # Fallback 1: allow names used in previous seasons, but not this season
        if not candidates:
            candidates = [
                ref
                for ref in ranked_events
                if ref.get("event_id") not in selected_ids
                and ref.get("name", "") not in selected_names
                and predicate(event_position(ref))
            ]
        # Fallback 2: allow same-name if we can't find distinct ones in this window
        if not candidates:
            candidates = [
                ref
                for ref in ranked_events
                if ref.get("event_id") not in selected_ids and predicate(event_position(ref))
            ]
        # Final fallback: any remaining event
        if not candidates:
            candidates = [
                ref
                for ref in ranked_events
                if ref.get("event_id") not in selected_ids and ref.get("name", "") not in selected_names
            ]
        if not candidates:
            candidates = [ref for ref in ranked_events if ref.get("event_id") not in selected_ids]
        if not candidates:
            beats.append({"beat_type": beat_type, "label": label, "summary": "当前范围暂无合适锚点。", "event": None})
            continue

        chosen = candidates[0]
        selected_ids.add(chosen.get("event_id"))
        selected_names.add(chosen.get("name", ""))
        beats.append(
            {
                "beat_type": beat_type,
                "label": label,
                "summary": build_story_beat_summary(
                    beat_type=beat_type,
                    event_ref=chosen,
                    spotlight_role=spotlight_role,
                ),
                "event": chosen,
            }
        )

    return beats


def build_must_keep_scene_reason(
    *,
    beat_type: str,
    event_ref: Optional[dict],
    focus_roles: Sequence[str],
    matched_relationships: Sequence[dict],
) -> str:
    if event_ref is None:
        return "当前范围暂无足够明确的季别锚点，建议后续人工补一场主线场景。"

    role_text = "、".join(focus_roles) if focus_roles else "核心角色"
    relationship_text = "、".join(item["title"] for item in matched_relationships[:2])
    location = event_ref.get("location") or "关键场域"

    if beat_type == "opening":
        return (
            f"适合拿来立人、立场和立场域，先把{role_text}在{location}的关系张力交代清楚。"
            if not relationship_text
            else f"适合做季初立戏，先把{relationship_text}在{location}的底色拍稳。"
        )
    if beat_type == "midpoint":
        return (
            f"适合承担季中的转折推进，让{role_text}的处境或关系在这一场里发生偏移。"
            if not relationship_text
            else f"适合做中段转折戏，把{relationship_text}从静态关系推到新的冲突或选择。"
        )
    return (
        f"适合拿来收束本季阶段目标，让{role_text}在{location}形成明确落点。"
        if not relationship_text
        else f"适合做季终落点戏，让{relationship_text}在{location}完成阶段性回响。"
    )


def build_must_keep_scenes(
    *,
    season_name: str,
    story_beats: Sequence[dict],
    season_curated: Sequence[dict],
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
) -> List[dict]:
    label_map = {
        "opening": "开场必保留戏",
        "midpoint": "中段必保留戏",
        "payoff": "收束必保留戏",
    }
    scenes: List[dict] = []
    for beat in story_beats:
        event_ref = beat.get("event")
        focus_roles = (
            extract_focus_roles(
                event_ref,
                writer_focus=writer_focus,
                spotlight_role=spotlight_role,
                limit=3,
            )
            if event_ref
            else []
        )
        matched_relationships = (
            match_relationships_for_event(
                event_ref,
                curated_relationships=season_curated,
                priority_pair_scores=priority_pair_scores,
                spotlight_role=spotlight_role,
                limit=2,
            )
            if event_ref
            else []
        )
        if event_ref and matched_relationships:
            participants = set(focus_roles)
            strict_relationships = [
                item
                for item in matched_relationships
                if {
                    str(item.get("source_role_name", "")).strip(),
                    str(item.get("target_role_name", "")).strip(),
                }.issubset(participants)
            ]
            if strict_relationships:
                matched_relationships = strict_relationships
        scene_id_suffix = str(beat.get("beat_type", "scene"))
        scenes.append(
            {
                "scene_id": f"{season_name}-{scene_id_suffix}",
                "beat_type": scene_id_suffix,
                "label": label_map.get(scene_id_suffix, str(beat.get("label", "必保留戏"))),
                "event": event_ref,
                "focus_roles": focus_roles,
                "related_relationship_titles": [item["title"] for item in matched_relationships],
                "adaptation_reason": build_must_keep_scene_reason(
                    beat_type=scene_id_suffix,
                    event_ref=event_ref,
                    focus_roles=focus_roles,
                    matched_relationships=matched_relationships,
                ),
            }
        )
    return scenes


def build_season_overviews(
    *,
    seasons: Sequence[dict],
    kb: UnifiedKnowledgeBase,
    all_event_refs: Sequence[dict],
    event_refs_by_role: Dict[str, List[dict]],
    relations_by_role: Dict[str, List[UnifiedRelation]],
    conflict_chains: Sequence[dict],
    curated_relationships: Sequence[dict],
    role_name_to_id: Dict[str, str],
    writer_focus: dict,
    priority_pair_scores: Dict[frozenset[str], int],
    spotlight_role: Optional[str],
) -> List[dict]:
    overviews: List[dict] = []

    # Pre-compute how many distinct event_ids share each event name across
    # the entire knowledge base.  Names that appear in many chapters are
    # likely references/flashbacks rather than genuinely distinct events.
    _name_counter: Dict[str, int] = {}
    for ref in all_event_refs:
        _ename = str(ref.get("name", "")).strip()
        if _ename:
            _name_counter[_ename] = _name_counter.get(_ename, 0) + 1
    name_occurrence_counts: Dict[str, int] = _name_counter

    # Track event names already selected by previous seasons so that later
    # seasons prefer fresh names for their story beats and anchor events.
    globally_used_beat_names: set[str] = set()
    globally_used_anchor_names: set[str] = set()

    for season in seasons:
        unit_start, unit_end = season["unit_range"]
        progress_start, progress_end = season["progress_range"]
        season_name = season["season_name"]
        season_focus = get_season_focus(writer_focus, season_name)

        season_events = [
            ref
            for ref in all_event_refs
            if range_overlaps(
                (ref.get("unit_index"), ref.get("unit_index")),
                (unit_start, unit_end),
            )
        ]
        season_conflicts = [
            chain
            for chain in conflict_chains
            if any(
                beat.get("unit_index") is not None and unit_start <= beat["unit_index"] <= unit_end
                for beat in chain.get("beats", [])
            )
        ]
        season_curated = [
            item
            for item in curated_relationships
            if any(
                ev.get("unit_index") is not None and unit_start <= ev["unit_index"] <= unit_end
                for ev in item.get("key_events", []) + item.get("manual_beats", [])
            )
        ]

        top_roles = []
        for role in kb.roles.values():
            unit_hits = [unit for unit in get_role_units(role) if unit_start <= unit <= unit_end]
            if not unit_hits:
                continue
            event_count = sum(
                1
                for ref in event_refs_by_role.get(role.canonical_name, [])
                if ref.get("unit_index") is not None and unit_start <= ref["unit_index"] <= unit_end
            )
            relation_count = 0
            for relation in relations_by_role.get(role.canonical_name, []):
                relation_units = get_relation_units(relation)
                relation_unit_span = (
                    (relation_units[0], relation_units[-1]) if relation_units else (None, None)
                )
                if range_overlaps(relation_unit_span, (unit_start, unit_end)):
                    relation_count += 1
            density_score = len(unit_hits) * 3 + event_count * 2 + relation_count * 2 + (
                3 if spotlight_role and role.canonical_name == spotlight_role else 0
            )
            top_roles.append(
                {
                    "role_id": role_name_to_id.get(role.canonical_name, role.canonical_name),
                    "role_name": role.canonical_name,
                    "unit_appearance_count": len(unit_hits),
                    "event_count": event_count,
                    "relation_count": relation_count,
                    "density_score": density_score,
                }
            )

        top_roles.sort(
            key=lambda item: (
                0 if spotlight_role and item["role_name"] == spotlight_role else 1,
                -item["density_score"],
                -item["unit_appearance_count"],
                item["role_name"],
            )
        )
        priority_roles, _dropped_focus_names = build_season_priority_roles(
            top_roles=top_roles,
            season_focus=season_focus,
            limit=8,
        )
        priority_role_names = [item["role_name"] for item in priority_roles]

        location_counter = Counter(ref["location"] for ref in season_events if ref.get("location"))
        location_roles: Dict[str, set[str]] = defaultdict(set)
        for ref in season_events:
            location = ref.get("location")
            if not location:
                continue
            for participant in ref.get("participants", []):
                location_roles[location].add(participant)

        top_locations = [
            {
                "location_name": location_name,
                "event_count": count,
                "role_count": len(location_roles[location_name]),
            }
            for location_name, count in location_counter.most_common(4)
        ]

        def _season_beat_count(chain: dict) -> int:
            return sum(
                1
                for beat in chain.get("beats", [])
                if beat.get("unit_index") is not None and unit_start <= beat["unit_index"] <= unit_end
            )

        main_conflicts = [
            {
                "chain_id": chain["id"],
                "title": chain["title"],
                "source_role_name": chain["source_role_name"],
                "target_role_name": chain["target_role_name"],
                "tension_score": chain["tension_score"],
            }
            for chain in sorted(
                season_conflicts,
                key=lambda item: (
                    0 if item.get("spotlight") else 1,
                    -item["tension_score"],
                    -_season_beat_count(item),
                    item["title"],
                ),
            )[:4]
        ]

        _all_anchor_candidates = sorted(
            season_events,
            key=lambda ref: (
                -screenplay_event_score(
                    ref,
                    season_curated=season_curated,
                    writer_focus=writer_focus,
                    priority_pair_scores=priority_pair_scores,
                    spotlight_role=spotlight_role,
                    name_occurrence_counts=name_occurrence_counts,
                ),
                ref["progress_start"] if ref["progress_start"] is not None else 10**12,
                ref["unit_index"] if ref["unit_index"] is not None else 10**12,
                ref["name"],
            ),
        )
        # Deduplicate by event name to ensure diverse anchor events;
        # also prefer names not already used in previous seasons.
        season_anchor_events: List[dict] = []
        _seen_anchor_names: set[str] = set()
        # First pass: skip names already used globally
        for _aref in _all_anchor_candidates:
            _aname = _aref.get("name", "")
            if _aname in _seen_anchor_names or _aname in globally_used_anchor_names:
                continue
            _seen_anchor_names.add(_aname)
            season_anchor_events.append(_aref)
            if len(season_anchor_events) >= 4:
                break
        # Fallback pass: if we couldn't fill 4 slots, allow globally-used names
        if len(season_anchor_events) < 4:
            for _aref in _all_anchor_candidates:
                _aname = _aref.get("name", "")
                if _aname in _seen_anchor_names:
                    continue
                _seen_anchor_names.add(_aname)
                season_anchor_events.append(_aref)
                if len(season_anchor_events) >= 4:
                    break
        anchor_event_ids = [
            str(ref.get("event_id", "")).strip() for ref in season_anchor_events if str(ref.get("event_id", "")).strip()
        ]
        # Build a set of all role names with at least one chapter appearance
        # in this season. Used to gate relationship participants.
        _season_role_names = {item["role_name"] for item in top_roles}

        priority_relationship_items: List[dict] = []
        seen_relationship_ids = set()
        for pair in season_focus.get("priority_relationship_pairs", []):
            normalized_pair = [str(name).strip() for name in pair if str(name).strip()]
            if len(normalized_pair) != 2:
                continue
            pair_key = frozenset(normalized_pair)
            matched = next(
                (
                    item
                    for item in season_curated
                    if frozenset({item["source_role_name"], item["target_role_name"]}) == pair_key
                ),
                None,
            )
            if not matched or matched["id"] in seen_relationship_ids:
                continue
            # Both participants must have chapter appearances in this season
            if matched["source_role_name"] not in _season_role_names or matched["target_role_name"] not in _season_role_names:
                continue
            priority_relationship_items.append(matched)
            seen_relationship_ids.add(matched["id"])
            if len(priority_relationship_items) >= 4:
                break

        ranked_relationship_items = sorted(
            season_curated,
            key=lambda item: (
                -season_relationship_score(
                    item,
                    season_name=season_name,
                    season_focus=season_focus,
                    season_unit_range=(unit_start, unit_end),
                    season_progress_range=(progress_start, progress_end),
                    priority_role_names=priority_role_names,
                    anchor_event_ids=anchor_event_ids,
                    priority_pair_scores=priority_pair_scores,
                    spotlight_role=spotlight_role,
                ),
                item["title"],
            ),
        )
        for item in ranked_relationship_items:
            if len(priority_relationship_items) >= 4:
                break
            if item["id"] in seen_relationship_ids:
                continue
            # Both participants must have chapter appearances in this season
            if item["source_role_name"] not in _season_role_names or item["target_role_name"] not in _season_role_names:
                continue
            priority_relationship_items.append(item)
            seen_relationship_ids.add(item["id"])

        priority_relationships = [
            {
                "relationship_id": item["id"],
                "title": item["title"],
                "source_role_name": item["source_role_name"],
                "target_role_name": item["target_role_name"],
                "kind": item["kind"],
            }
            for item in priority_relationship_items
        ]
        story_beats = build_story_beats(
            season_events=season_events,
            season_curated=season_curated,
            writer_focus=writer_focus,
            priority_pair_scores=priority_pair_scores,
            spotlight_role=spotlight_role,
            globally_used_names=globally_used_beat_names,
            name_occurrence_counts=name_occurrence_counts,
        )
        must_keep_scenes = build_must_keep_scenes(
            season_name=season_name,
            story_beats=story_beats,
            season_curated=season_curated,
            writer_focus=writer_focus,
            priority_pair_scores=priority_pair_scores,
            spotlight_role=spotlight_role,
        )

        top_role_names = [item["role_name"] for item in (priority_roles or top_roles)[:3]]
        top_location_names = [item["location_name"] for item in top_locations[:3]]
        conflict_titles = [item["title"] for item in main_conflicts[:2]]
        summary = (
            f"{season_name}集中呈现{('、'.join(top_role_names) if top_role_names else '多位核心人物')}等人物线，"
            f"主线冲突落在{('、'.join(conflict_titles) if conflict_titles else '多条关系推进')}，"
            f"高频场域为{('、'.join(top_location_names) if top_location_names else '多处场景')}。"
        )

        spotlight_summary = None
        if spotlight_role:
            # Use priority_relationships (curated + scored) first, then fall back
            # to season_curated + season_conflicts for broader coverage
            spotlight_counterpart_pool = [
                *priority_relationship_items,
                *season_curated,
                *season_conflicts,
            ]
            spotlight_counterparts = unique_names(
                (
                    item["target_role_name"]
                    if item.get("source_role_name") == spotlight_role
                    else item.get("source_role_name", "")
                )
                for item in spotlight_counterpart_pool
                if spotlight_role in {item.get("source_role_name"), item.get("target_role_name")}
            )[:3]
            spotlight_summary = (
                f"{spotlight_role}在{season_name}主要与"
                f"{('、'.join(spotlight_counterparts) if spotlight_counterparts else '多位角色')}形成主线互动，"
                f"关键落点集中在{('、'.join(top_location_names) if top_location_names else '多处场景')}。"
            )

        adaptation_hooks = [
            (
                f"人物重点：优先看{('、'.join(top_role_names) if top_role_names else '当季核心人物')}的出场密度与关系变化，"
                f"其中{spotlight_role if spotlight_role else (top_role_names[0] if top_role_names else '核心角色')}应作为叙事主轴。"
            ),
            (
                f"关系重点：重点保留{('、'.join(item['title'] for item in priority_relationships) if priority_relationships else '当季主要关系推进')}，"
                f"并让{('、'.join(conflict_titles) if conflict_titles else '主线冲突')}承担阶段转折。"
            ),
            (
                f"场景重点：优先把{('、'.join(top_location_names) if top_location_names else '关键场域')}拍出明确层次，"
                f"再用{('、'.join(event['name'] for event in season_anchor_events[:2]) if season_anchor_events else '锚点事件')}做结构落点。"
            ),
        ]

        overviews.append(
            {
                "season_name": season_name,
                "unit_range": season["unit_range"],
                "progress_range": season["progress_range"],
                "summary": summary,
                "spotlight_summary": spotlight_summary,
                "adaptation_hooks": adaptation_hooks,
                "story_beats": story_beats,
                "top_roles": top_roles[:8],
                "priority_roles": priority_roles,
                "top_locations": top_locations,
                "main_conflicts": main_conflicts,
                "priority_relationships": priority_relationships,
                "anchor_events": season_anchor_events,
                "must_keep_scenes": must_keep_scenes,
                "data_provenance": {
                    "priority_roles_source": "season_focus+evidence_gated" if season_focus.get("priority_roles") else "density_ranking",
                    "priority_roles_dropped": _dropped_focus_names,
                    "priority_relationships_source": "season_focus+evidence_gated" if season_focus.get("priority_relationship_pairs") else "score_ranking+evidence_gated",
                    "summary_source": "template_from_data",
                    "story_beats_source": "score_ranking+cross_season_dedup",
                    "note": "summary/spotlight/adaptation_hooks are template-generated from ranked data, not manually verified against source text. priority_roles are evidence-gated: season_focus names without in-season chapter appearances are dropped. priority_relationships are evidence-gated: both participants must have chapter appearances in the season. story_beats and anchor_events apply cross-season name dedup and frequency penalty.",
                },
            }
        )

        # Record names used by this season so later seasons avoid them
        for beat in story_beats:
            ev = beat.get("event")
            if ev and ev.get("name"):
                globally_used_beat_names.add(ev["name"])
        for anchor in season_anchor_events:
            if anchor.get("name"):
                globally_used_anchor_names.add(anchor["name"])

    return overviews


def build_writer_insights_payload(
    *,
    kb: UnifiedKnowledgeBase,
    unit_progress_index: dict,
    core_cast: dict,
) -> dict:
    unit_meta = {
        int(unit_index): metadata
        for unit_index, metadata in unit_progress_index.get("units", {}).items()
    }
    event_type_rules = core_cast.get("event_type_rules", [])
    phase_rules = core_cast.get("phase_rules", [])
    writer_focus = core_cast.get("writer_focus", {})
    spotlight_role = str(writer_focus.get("spotlight_role", "")).strip() or None
    priority_pair_scores = build_priority_pair_scores(writer_focus)
    curated_configs = build_curated_relationship_configs(writer_focus)

    all_event_refs = [
        make_event_ref(event, event_type_rules=event_type_rules, unit_meta=unit_meta)
        for event in kb.events.values()
    ]
    all_event_refs.sort(
        key=lambda ref: (
            ref["progress_start"] if ref["progress_start"] is not None else 10**12,
            ref["unit_index"] if ref["unit_index"] is not None else 10**12,
            ref["name"],
        )
    )
    event_ref_index = {ref["event_id"]: ref for ref in all_event_refs}

    event_refs_by_role: Dict[str, List[dict]] = defaultdict(list)
    pair_event_map: Dict[frozenset[str], List[dict]] = defaultdict(list)
    for event_ref in all_event_refs:
        participants = event_ref.get("participants", [])
        for participant in participants:
            event_refs_by_role[participant].append(event_ref)
        for index, source in enumerate(participants):
            for target in participants[index + 1 :]:
                pair_event_map[frozenset({source, target})].append(event_ref)

    role_name_to_id = dict(kb.name_to_role_id)
    relations_by_role: Dict[str, List[UnifiedRelation]] = defaultdict(list)
    relations_by_pair: Dict[frozenset[str], List[UnifiedRelation]] = defaultdict(list)
    for relation in kb.relations.values():
        relations_by_role[relation.from_entity].append(relation)
        relations_by_role[relation.to_entity].append(relation)
        relations_by_pair[frozenset({relation.from_entity, relation.to_entity})].append(relation)

    priority_role_names = [
        str(name).strip()
        for name in writer_focus.get("priority_characters", [])
        if str(name).strip() in kb.name_to_role_id
    ]
    if spotlight_role and spotlight_role in kb.name_to_role_id and spotlight_role not in priority_role_names:
        priority_role_names = [spotlight_role, *priority_role_names]
    if not priority_role_names:
        priority_role_names = [role.canonical_name for role in sorted(kb.roles.values(), key=lambda role: -role.total_mentions)[:12]]

    character_arcs = []
    for role_name in priority_role_names:
        role_id = kb.name_to_role_id.get(role_name)
        if not role_id or role_id not in kb.roles:
            continue
        role = kb.roles[role_id]
        character_arcs.append(
            build_character_arc(
                role=role,
                role_name_to_id=role_name_to_id,
                unit_meta=unit_meta,
                role_events=event_refs_by_role.get(role.canonical_name, []),
                role_relations=relations_by_role.get(role.canonical_name, []),
                pair_event_map=pair_event_map,
                phase_rules=phase_rules,
                writer_focus=writer_focus,
                priority_pair_scores=priority_pair_scores,
                spotlight_role=spotlight_role,
            )
        )

    character_arcs.sort(
        key=lambda arc: (
            0 if arc.get("spotlight") else 1,
            -len(arc.get("relationship_phases", [])),
            arc["role_name"],
        )
    )

    seasons = build_season_entries(unit_meta)
    season_meta = {item["season_name"]: item for item in seasons}

    conflict_chains = build_conflict_chains(
        relations=kb.relations.values(),
        role_name_to_id=role_name_to_id,
        pair_event_map=pair_event_map,
        phase_rules=phase_rules,
        conflict_actions=writer_focus.get("conflict_actions", []),
        unit_meta=unit_meta,
        priority_pair_scores=priority_pair_scores,
        spotlight_role=spotlight_role,
    )

    curated_relationships = build_curated_relationships(
        curated_configs=curated_configs,
        relations_by_pair=relations_by_pair,
        pair_event_map=pair_event_map,
        all_event_refs=all_event_refs,
        event_ref_index=event_ref_index,
        phase_rules=phase_rules,
        writer_focus=writer_focus,
        priority_pair_scores=priority_pair_scores,
        role_name_to_id=role_name_to_id,
        season_meta=season_meta,
        spotlight_role=spotlight_role,
    )

    foreshadowing_threads = build_foreshadowing_threads(
        event_refs=all_event_refs,
        patterns=core_cast.get("foreshadowing_patterns", []),
        spotlight_role=spotlight_role,
    )

    season_overviews = build_season_overviews(
        seasons=seasons,
        kb=kb,
        all_event_refs=all_event_refs,
        event_refs_by_role=event_refs_by_role,
        relations_by_role=relations_by_role,
        conflict_chains=conflict_chains,
        curated_relationships=curated_relationships,
        role_name_to_id=role_name_to_id,
        writer_focus=writer_focus,
        priority_pair_scores=priority_pair_scores,
        spotlight_role=spotlight_role,
    )

    return {
        "version": "swordcoming-writer-insights-v4",
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "unit_label": kb.unit_label,
        "progress_label": kb.progress_label,
        "spotlight_role_name": spotlight_role,
        "summary": {
            "character_arc_count": len(character_arcs),
            "conflict_chain_count": len(conflict_chains),
            "foreshadowing_thread_count": len(foreshadowing_threads),
            "season_overview_count": len(season_overviews),
            "curated_relationship_count": len(curated_relationships),
        },
        "seasons": seasons,
        "season_overviews": season_overviews,
        "character_arcs": character_arcs,
        "curated_relationships": curated_relationships,
        "conflict_chains": conflict_chains,
        "foreshadowing_threads": foreshadowing_threads,
    }


def save_writer_insights(payload: dict, output_path: Path) -> None:
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_writer_insights_file(
    *,
    kb: UnifiedKnowledgeBase,
    unit_progress_index_path: Path,
    core_cast_path: Path,
    output_path: Path,
) -> dict:
    payload = build_writer_insights_payload(
        kb=kb,
        unit_progress_index=load_json(unit_progress_index_path),
        core_cast=load_json(core_cast_path),
    )
    save_writer_insights(payload, output_path)
    return payload
