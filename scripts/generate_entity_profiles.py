#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Sequence


OUTPUT_VERSION = "entity-profiles-v1"
GENERATOR_NAME = "local-template-fallback"
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


def _clean_sentence(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"[\u0000-\u001f]", "", value)
    return value


def _trim_paragraph(text: str, max_chars: int) -> str:
    normalized = _clean_sentence(text)
    if len(normalized) <= max_chars:
        return normalized
    truncated = normalized[:max_chars]
    for marker in ("。", "；", "，"):
        pos = truncated.rfind(marker)
        if pos >= max_chars // 2:
            return truncated[: pos + 1].rstrip("；，。") + "。"
    return truncated.rstrip("；，。") + "。"


def _trim_multiline(text: str, max_chars: int) -> str:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    if not blocks:
        return ""
    result_blocks: List[str] = []
    budget = max_chars
    for index, block in enumerate(blocks):
        reserved_separators = 2 * max(0, len(blocks) - index - 1)
        allowed = max(20, budget - reserved_separators)
        trimmed = _trim_paragraph(block, min(allowed, 170))
        result_blocks.append(trimmed)
        budget -= len(trimmed)
        if index < len(blocks) - 1:
            budget -= 2
        if budget <= 0:
            break
    return "\n\n".join(result_blocks)


def _ensure_min_chars(text: str, min_chars: int, fallback: str) -> str:
    normalized = _clean_sentence(text)
    if len(normalized) >= min_chars:
        return normalized
    candidate = normalized + fallback
    return _clean_sentence(candidate)


def _extract_sentences(text: str, limit: int = 3) -> List[str]:
    normalized = _clean_sentence(text)
    if not normalized:
        return []
    parts = [segment.strip() for segment in re.split(r"(?<=[。！？!?；;])", normalized) if segment.strip()]
    return parts[:limit]


def _pick_excerpt_lines(excerpts: Sequence[dict], *, preferred_phases: Sequence[str], limit: int) -> List[str]:
    ranked: List[str] = []
    for phase in preferred_phases:
        for excerpt in excerpts:
            if str(excerpt.get("phase") or "") != phase:
                continue
            text = _clean_sentence(excerpt.get("text") or "")
            if not text:
                continue
            ranked.append(text)
            if len(ranked) >= limit:
                return ranked
    for excerpt in excerpts:
        text = _clean_sentence(excerpt.get("text") or "")
        if not text or text in ranked:
            continue
        ranked.append(text)
        if len(ranked) >= limit:
            break
    return ranked


def _build_identity_summary(item: dict) -> str:
    name = str(item.get("canonical_name", "")).strip()
    power = str(item.get("primary_power") or "").strip()
    first_juan = item.get("first_appearance_juan")
    last_juan = item.get("last_appearance_juan")
    unit_count = int((item.get("appearance_span") or {}).get("unit_count") or 0)

    parts: List[str] = []
    if power:
        parts.append(f"{name}是三季叙事中长期活跃的人物，主要关联{power}线索")
    else:
        parts.append(f"{name}是三季叙事中持续出现的关键人物")
    if first_juan and last_juan:
        parts.append(f"出场跨度覆盖第{first_juan}至第{last_juan}章")
    if unit_count:
        parts.append(f"累计出现场景约{unit_count}个单元")
    text = "，".join(parts).rstrip("，。") + "。"
    text = _trim_summary(text, 90)
    text = _ensure_min_chars(text, 40, "在现有三季文本内可形成稳定的人物识别。")
    return _trim_summary(text, 90)


def _build_role_long_description(item: dict) -> str:
    name = str(item.get("canonical_name", "")).strip()
    power = str(item.get("primary_power") or "").strip()
    top_related = [str(value).strip() for value in item.get("top_related_entities", []) if str(value).strip()]
    top_locations = [str(value).strip() for value in item.get("top_locations", []) if str(value).strip()]
    turning_points = [
        str(event.get("display_name") or event.get("name") or "").strip()
        for event in item.get("turning_point_candidates", [])
        if str(event.get("display_name") or event.get("name") or "").strip()
    ]
    phase_arc_candidates = item.get("phase_arc_candidates", [])
    excerpts = item.get("representative_original_excerpts", [])
    original_descriptions = [str(value).strip() for value in item.get("original_descriptions", []) if str(value).strip()]

    intro_lines: List[str] = []
    if power and top_locations:
        intro_lines.append(
            f"{name}在现有三季材料里始终是高频角色，人物活动主要落在{_join_names(top_locations, 3)}，并与{power}相关脉络反复交叠。"
        )
    elif top_locations:
        intro_lines.append(
            f"{name}在现有三季材料里持续出现，主要活动场域集中在{_join_names(top_locations, 3)}。"
        )
    else:
        intro_lines.append(f"{name}在现有三季材料里以连续出场的方式参与主干叙事。")

    if original_descriptions:
        intro_sentences = _extract_sentences(original_descriptions[0], limit=2)
        if intro_sentences:
            intro_lines.append(f"文本早段对其的描写偏重于“{intro_sentences[0].rstrip('。！？!?；;')}”，强调其出场时的具体处境。")

    relation_lines: List[str] = []
    if top_related:
        relation_lines.append(
            f"人物关系上，{name}与{_join_names(top_related, 4)}的互动最密集，这些关系共同构成其行动选择的外部压力与支持网络。"
        )
    if top_locations:
        relation_lines.append(
            f"空间分布上，{_join_names(top_locations, 4)}形成了其叙事重心的迁移轨迹，人物状态通常随着场域切换而发生调整。"
        )

    phase_lines: List[str] = []
    phase_text = _phase_arc_text(phase_arc_candidates)
    if phase_text:
        phase_lines.append(f"从阶段走势看，{phase_text}，显示其人物线并非单点爆发，而是沿多次节点逐步推高。")
    if turning_points:
        phase_lines.append(f"可识别的关键节点包括“{turning_points[0]}”{f"、“{turning_points[1]}”" if len(turning_points) > 1 else ""}，这些节点更多体现为身份位置与关系结构的重排。")

    excerpt_lines = _pick_excerpt_lines(excerpts, preferred_phases=("early", "middle", "late"), limit=2)
    if excerpt_lines:
        phase_lines.append(
            f"从原文片段看，其叙事特征常落在“{excerpt_lines[0][:36]}...”这类具体场景中，呈现方式以人物处境和对话推进为主。"
        )

    blocks = [
        _trim_paragraph("".join(intro_lines), 150),
        _trim_paragraph("".join(relation_lines), 150) if relation_lines else "",
        _trim_paragraph("".join(phase_lines), 150) if phase_lines else "",
    ]
    blocks = [block for block in blocks if block]
    if len(blocks) < 2:
        blocks.append(_trim_paragraph(f"总体上，{name}在当前三季中的叙事作用主要体现为人物关系与行动线索的连接点。", 120))

    long_description = "\n\n".join(blocks[:3])
    long_description = _trim_multiline(long_description, 420)
    if len(long_description.replace("\n", "")) < 180:
        supplement = _trim_paragraph(f"就可见材料而言，{name}的身份定位、关系结构与阶段变化能够互相印证，读者可据此把握其在前三季中的基本位置。", 120)
        long_description = _trim_multiline(long_description + "\n\n" + supplement, 420)
    return long_description


def _build_role_display_summary(item: dict, identity_summary: str, long_description: str) -> str:
    name = str(item.get("canonical_name", "")).strip()
    top_related = [str(value).strip() for value in item.get("top_related_entities", []) if str(value).strip()]
    top_locations = [str(value).strip() for value in item.get("top_locations", []) if str(value).strip()]
    turning_points = [
        str(event.get("display_name") or event.get("name") or "").strip()
        for event in item.get("turning_point_candidates", [])
        if str(event.get("display_name") or event.get("name") or "").strip()
    ]

    lines: List[str] = [identity_summary.rstrip("。") + "。"]
    if top_related:
        lines.append(f"在当前三季可见文本中，{name}与{_join_names(top_related, 3)}的关系线最具持续性。")
    if top_locations:
        lines.append(f"其叙事活动主要分布在{_join_names(top_locations, 3)}。")
    if turning_points:
        lines.append(f"阶段性变化可从“{turning_points[0]}”等节点观察。")

    text = "".join(lines)
    if len(text) < 100:
        text = _trim_summary(long_description.replace("\n\n", " "), 200)
    if len(text) < 100:
        text = _ensure_min_chars(text, 100, f"{name}在现有三季叙事中保持了稳定可追踪的人物线。")
    return _trim_summary(text, 220)


def _build_location_identity_summary(item: dict) -> str:
    name = str(item.get("canonical_name", "")).strip()
    location_type = str(item.get("location_type") or "地点").strip() or "地点"
    top_roles = [str(value).strip() for value in item.get("top_roles", []) if str(value).strip()]
    appearance_span = item.get("appearance_span") or {}
    first_unit = appearance_span.get("first_unit")
    last_unit = appearance_span.get("last_unit")

    parts: List[str] = [f"{name}是三季叙事中的{location_type}"]
    if top_roles:
        parts.append(f"与{_join_names(top_roles, 3)}等人物线高度重合")
    if first_unit and last_unit:
        parts.append(f"有效出现场景覆盖单元{first_unit}-{last_unit}")
    text = _trim_summary("，".join(parts).rstrip("，。") + "。", 90)
    text = _ensure_min_chars(text, 40, "在前三季文本中具有明确叙事功能。")
    return _trim_summary(text, 90)


def _build_location_long_description(item: dict) -> str:
    name = str(item.get("canonical_name", "")).strip()
    location_type = str(item.get("location_type") or "地点").strip() or "地点"
    top_roles = [str(value).strip() for value in item.get("top_roles", []) if str(value).strip()]
    top_events = [
        str(event.get("display_name") or event.get("name") or "").strip()
        for event in item.get("top_events", [])
        if str(event.get("display_name") or event.get("name") or "").strip()
    ]
    excerpts = item.get("representative_original_excerpts", [])
    original_descriptions = [str(value).strip() for value in item.get("original_descriptions", []) if str(value).strip()]

    block1_parts = [f"{name}在当前三季文档中被持续标注为{location_type}，并不是一次性背景板，而是多条人物线反复汇合的场域。"]
    if original_descriptions:
        intro_sentences = _extract_sentences(original_descriptions[0], limit=1)
        if intro_sentences:
            block1_parts.append(f"原文常以“{intro_sentences[0].rstrip('。！？!?；;')}”这类细节描写进入该地点。")

    block2_parts: List[str] = []
    if top_roles:
        block2_parts.append(f"关联人物方面，{_join_names(top_roles, 4)}在此地的交集最明显，地点功能因此兼具相遇、对峙与转场三种叙事用途。")
    if top_events:
        block2_parts.append(f"在可追踪事件里，“{top_events[0]}”{f"与“{top_events[1]}”" if len(top_events) > 1 else ""}等节点共同定义了该地在三季中的剧情位置。")

    excerpt_lines = _pick_excerpt_lines(excerpts, preferred_phases=("early", "middle", "late"), limit=2)
    block3_parts: List[str] = []
    if excerpt_lines:
        block3_parts.append(f"从代表性片段看，{name}的书写重点往往落在人物行动与空间氛围的并置上，例如“{excerpt_lines[0][:36]}...”。")
    block3_parts.append("因此在阅读层面，它更像一处持续生长的叙事坐标，而非单次事件的容器。")

    blocks = [
        _trim_paragraph("".join(block1_parts), 150),
        _trim_paragraph("".join(block2_parts), 150) if block2_parts else "",
        _trim_paragraph("".join(block3_parts), 150),
    ]
    blocks = [block for block in blocks if block]
    if len(blocks) < 2:
        blocks.append(_trim_paragraph(f"在三季范围内，{name}持续承担人物汇聚与叙事转场的空间职能。", 120))

    text = _trim_multiline("\n\n".join(blocks[:3]), 420)
    if len(text.replace("\n", "")) < 180:
        text = _trim_multiline(
            text + "\n\n" + _trim_paragraph(f"结合现有章节证据，{name}能够支撑对人物关系和阶段推进的连续阅读。", 120),
            420,
        )
    return text


def _role_profile(item: dict) -> dict:
    name = str(item.get("canonical_name", "")).strip()
    power = str(item.get("primary_power") or "").strip()
    top_locations = item.get("top_locations", [])
    top_related = item.get("top_related_entities", [])
    turning_points = item.get("turning_point_candidates", [])
    phase_arc_candidates = item.get("phase_arc_candidates", [])

    identity_summary = _build_identity_summary(item)
    long_description = _build_role_long_description(item)
    display_summary = _build_role_display_summary(item, identity_summary, long_description)

    story_function = ""
    if top_related:
        story_function = f"{name}的人物功能主要体现在与{_join_names(top_related, 4)}等关系链条的持续联动。"
    elif top_locations:
        story_function = f"{name}的人物功能主要体现在跨越{_join_names(top_locations, 3)}的连续行动轨迹。"
    else:
        story_function = f"{name}的人物功能主要体现在关键节点中的持续在场。"

    phase_arc = _phase_arc_text(phase_arc_candidates)
    if phase_arc:
        phase_arc = _trim_summary(f"阶段走势：{phase_arc}。", 110)
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

    return {
        "entity_type": "role",
        "entity_id": item["entity_id"],
        "display_summary": display_summary,
        "identity_summary": identity_summary,
        "long_description": long_description,
        "story_function": _trim_summary(story_function, 120),
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

    identity_summary = _build_location_identity_summary(item)
    long_description = _build_location_long_description(item)
    story_function = (
        f"{name}在三季叙事中承接了“{top_event_names[0]}”{f'与“{top_event_names[1]}”' if len(top_event_names) > 1 else ''}等高频节点。"
        if top_event_names
        else f"{name}在三季叙事中主要承担人物聚合与情节转场功能。"
    )
    display_summary = _trim_summary(identity_summary + story_function, 220)
    if len(display_summary) < 100:
        display_summary = _trim_summary(display_summary + _trim_paragraph(long_description.replace("\n\n", " "), 120), 220)

    return {
        "entity_type": "location",
        "entity_id": item["entity_id"],
        "display_summary": display_summary,
        "identity_summary": _trim_summary(identity_summary, 90),
        "long_description": long_description,
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
