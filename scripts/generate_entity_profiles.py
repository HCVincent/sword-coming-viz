#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Sequence


OUTPUT_VERSION = "entity-profiles-v1"
GENERATOR_NAME = "local-agent"
PROFILE_VERSION = "role-location-profile-v1"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _join_names(values: Iterable[str], limit: int = 3) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    return "、".join(items[:limit])


def _trim_summary(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    truncated = normalized[:max_chars]
    for marker in ("；", "，", "。"):
        pos = truncated.rfind(marker)
        if pos >= max_chars // 2:
            return truncated[: pos + 1].rstrip("；，。") + "。"
    return truncated.rstrip("；，。") + "。"


def _phase_arc_text(events: Sequence[dict]) -> str:
    parts: List[str] = []
    for event in events:
        phase = str(event.get("phase") or "").strip()
        name = str(event.get("display_name") or event.get("name") or "").strip()
        if not name:
            continue
        label = {"early": "前段", "middle": "中段", "late": "后段"}.get(phase, phase or "阶段")
        parts.append(f"{label}落在“{name}”")
    return "，".join(parts[:3])


def _role_profile(item: dict) -> dict:
    name = str(item.get("canonical_name", "")).strip()
    power = str(item.get("primary_power") or "").strip()
    top_locations = item.get("top_locations", [])
    top_related = item.get("top_related_entities", [])
    turning_points = item.get("turning_point_candidates", [])
    phase_arc_candidates = item.get("phase_arc_candidates", [])

    identity_parts: List[str] = []
    if power and top_locations:
        identity_parts.append(f"{name}从{top_locations[0]}一线展开，主要牵连{power}相关人物与处境。")
    elif power:
        identity_parts.append(f"{name}的人物重心长期挂在{power}这条线索上。")
    elif top_locations:
        identity_parts.append(f"{name}的叙事轨迹首先在{top_locations[0]}立住。")
    else:
        identity_parts.append(f"{name}的行动轨迹贯穿当前叙事范围。")

    story_function_parts: List[str] = []
    if top_related:
        story_function_parts.append(f"他与{_join_names(top_related, 3)}的互动，决定了人物线的主要拉扯方向。")
    if turning_points:
        story_function_parts.append(f"“{turning_points[0].get('display_name') or turning_points[0].get('name') or name}”之后，人物位置开始出现明显变化。")
    if not story_function_parts:
        story_function_parts.append(f"他的分量主要体现在持续参与关键节点，并把周边关系慢慢串起来。")

    phase_arc = _phase_arc_text(phase_arc_candidates)
    if phase_arc:
        phase_arc = _trim_summary(f"人物阶段变化大致可见于：{phase_arc}。", 110)
    else:
        phase_arc = ""

    relationship_clusters = []
    if top_related:
        relationship_clusters.append(f"核心关系簇：{_join_names(top_related, 4)}")
    major_locations = list(top_locations[:4])
    turning_point_names = [
        str(event.get("display_name") or event.get("name") or "").strip()
        for event in turning_points[:4]
        if str(event.get("display_name") or event.get("name") or "").strip()
    ]

    display_parts: List[str] = [identity_parts[0]]
    if top_related:
        display_parts.append(f"与{_join_names(top_related, 3)}的牵引最能定义他的处境变化。")
    if turning_point_names:
        display_parts.append(f"关键转折集中在“{turning_point_names[0]}”{f'与“{turning_point_names[1]}”' if len(turning_point_names) > 1 else ''}。")
    display_summary = _trim_summary("".join(display_parts), 138)

    return {
        "entity_type": "role",
        "entity_id": item["entity_id"],
        "display_summary": display_summary,
        "identity_summary": _trim_summary(identity_parts[0], 90),
        "story_function": _trim_summary("".join(story_function_parts), 120),
        "phase_arc": phase_arc,
        "relationship_clusters": relationship_clusters,
        "major_locations": major_locations,
        "turning_points": turning_point_names,
        "summary_keywords": [value for value in [name, power, *top_related[:2], *major_locations[:2]] if value],
        "evidence_excerpt_ids": item.get("evidence_excerpt_ids", [])[:6],
        "generated_from_input_hash": item["input_hash"],
        "generator": GENERATOR_NAME,
        "profile_version": PROFILE_VERSION,
        "generated_at": datetime.now().isoformat(),
    }


def _location_profile(item: dict) -> dict:
    name = str(item.get("canonical_name", "")).strip()
    location_type = str(item.get("location_type") or "地点").strip() or "地点"
    top_roles = item.get("top_roles", [])
    top_events = item.get("top_events", [])
    top_event_names = [
        str(event.get("display_name") or event.get("name") or "").strip()
        for event in top_events[:4]
        if str(event.get("display_name") or event.get("name") or "").strip()
    ]

    identity_summary = f"{name}作为{location_type}，反复承接{_join_names(top_roles, 3) if top_roles else '多组人物'}的活动与停留。"
    story_function = (
        f"这个场域常把“{top_event_names[0]}”{f'与“{top_event_names[1]}”' if len(top_event_names) > 1 else ''}这类节点串在一起，"
        f"让人物关系和情节推进有了稳定落点。"
        if top_event_names
        else f"这个场域的作用在于反复承接人物相遇、停驻和关系转折。"
    )
    display_summary = _trim_summary(identity_summary + story_function, 156)

    return {
        "entity_type": "location",
        "entity_id": item["entity_id"],
        "display_summary": display_summary,
        "identity_summary": _trim_summary(identity_summary, 100),
        "story_function": _trim_summary(story_function, 120),
        "phase_arc": "",
        "relationship_clusters": [],
        "major_locations": [name],
        "turning_points": top_event_names,
        "summary_keywords": [value for value in [name, location_type, *top_roles[:2], *top_event_names[:2]] if value],
        "evidence_excerpt_ids": item.get("evidence_excerpt_ids", [])[:6],
        "generated_from_input_hash": item["input_hash"],
        "generator": GENERATOR_NAME,
        "profile_version": PROFILE_VERSION,
        "generated_at": datetime.now().isoformat(),
    }


def build_entity_profiles(inputs_payload: dict) -> dict:
    profiles: List[dict] = []
    for item in inputs_payload.get("roles", []):
        profiles.append(_role_profile(item))
    for item in inputs_payload.get("locations", []):
        profiles.append(_location_profile(item))
    return {
        "version": OUTPUT_VERSION,
        "generated_at": datetime.now().isoformat(),
        "generator": GENERATOR_NAME,
        "profile_version": PROFILE_VERSION,
        "profiles": profiles,
    }


def build_entity_display_summaries(inputs_payload: dict) -> dict:
    output = build_entity_profiles(inputs_payload)
    return {
        "version": output["version"],
        "generated_at": output["generated_at"],
        "generator": output["generator"],
        "summaries": output["profiles"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate static entity_profiles.json from entity_profile_inputs.json.")
    parser.add_argument("--input", default="data/entity_profile_inputs.json", help="Entity profile inputs path.")
    parser.add_argument("--output", default="data/entity_profiles.json", help="Profile artifact output path.")
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    output = build_entity_profiles(payload)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Entity profiles -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
