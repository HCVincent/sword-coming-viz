#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List


OUTPUT_VERSION = "entity-display-summaries-v1"
GENERATOR_NAME = "local-agent"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _join_names(values: Iterable[str], limit: int = 2) -> str:
    items = [str(value).strip() for value in values if str(value).strip()]
    return "、".join(items[:limit])


def _trim_summary(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    for marker in ("；", "，", "。"):
        pos = truncated.rfind(marker)
        if pos >= max_chars // 2:
            return truncated[: pos + 1].rstrip("；，。") + "。"
    return truncated.rstrip("；，。") + "。"


def _role_summary(item: dict) -> str:
    name = item.get("canonical_name", "")
    power = str(item.get("primary_power") or "").strip()
    locations = _join_names(item.get("top_locations", []), limit=2)
    related = _join_names(item.get("top_related_entities", []), limit=2)
    event_names = _join_names([evt.get("name", "") for evt in item.get("representative_events", [])], limit=2)

    parts: List[str] = []
    if power and locations:
        parts.append(f"{name}是前三季中活跃于{locations}的{power}线关键人物")
    elif power:
        parts.append(f"{name}是前三季中{power}线的关键人物")
    elif locations:
        parts.append(f"{name}是前三季中活跃于{locations}的关键人物")
    else:
        parts.append(f"{name}是前三季叙事中的关键人物")

    if related and event_names:
        parts.append(f"与{related}等人关系紧密，围绕{event_names}等节点推动人物线与主线展开")
    elif related:
        parts.append(f"与{related}等人关系紧密，持续推动相关人物线发展")
    elif event_names:
        parts.append(f"围绕{event_names}等节点持续推进自身人物线")

    return _trim_summary("，".join(parts) + "。", 110)


def _location_summary(item: dict) -> str:
    name = item.get("canonical_name", "")
    location_type = str(item.get("location_type") or "地点").strip() or "地点"
    top_roles = _join_names(item.get("top_roles", []), limit=3)
    top_events = _join_names([evt.get("name", "") for evt in item.get("top_events", [])], limit=2)

    parts: List[str] = [f"{name}是前三季叙事中的关键{location_type}"]
    if top_roles:
        parts.append(f"与{top_roles}等人物联系紧密")
    if top_events:
        parts.append(f"承载{top_events}等重要情节，反复作为人物关系与事件推进的场域")
    else:
        parts.append("反复作为人物关系与事件推进的重要场域")
    return _trim_summary("，".join(parts) + "。", 120)


def _keywords(item: dict, summary: str) -> List[str]:
    candidates: List[str] = []
    for key in ("canonical_name", "primary_power", "location_type"):
        value = str(item.get(key) or "").strip()
        if value:
            candidates.append(value)
    candidates.extend(item.get("all_names", [])[:2])
    candidates.extend(item.get("top_related_entities", [])[:2])
    candidates.extend(item.get("top_locations", [])[:2])
    candidates.extend(item.get("top_roles", [])[:2])
    deduped: List[str] = []
    for value in candidates:
        normalized = str(value).strip()
        if normalized and normalized not in deduped and normalized in summary:
            deduped.append(normalized)
    return deduped[:5]


def build_entity_display_summaries(inputs_payload: dict) -> dict:
    summaries: List[dict] = []
    for item in inputs_payload.get("roles", []):
        summary = _role_summary(item)
        summaries.append(
            {
                "entity_type": "role",
                "entity_id": item["entity_id"],
                "display_summary": summary,
                "summary_keywords": _keywords(item, summary),
                "evidence_excerpt_ids": item.get("evidence_excerpt_ids", [])[:6],
                "generated_from_input_hash": item["input_hash"],
                "generator": GENERATOR_NAME,
                "generated_at": datetime.now().isoformat(),
            }
        )
    for item in inputs_payload.get("locations", []):
        summary = _location_summary(item)
        summaries.append(
            {
                "entity_type": "location",
                "entity_id": item["entity_id"],
                "display_summary": summary,
                "summary_keywords": _keywords(item, summary),
                "evidence_excerpt_ids": item.get("evidence_excerpt_ids", [])[:6],
                "generated_from_input_hash": item["input_hash"],
                "generator": GENERATOR_NAME,
                "generated_at": datetime.now().isoformat(),
            }
        )
    return {
        "version": OUTPUT_VERSION,
        "generated_at": datetime.now().isoformat(),
        "generator": GENERATOR_NAME,
        "summaries": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate static entity_display_summaries.json from entity_summary_inputs.json.")
    parser.add_argument("--input", default="data/entity_summary_inputs.json", help="Entity summary inputs path.")
    parser.add_argument("--output", default="data/entity_display_summaries.json", help="Summary artifact output path.")
    args = parser.parse_args()

    payload = load_json(Path(args.input))
    output = build_entity_display_summaries(payload)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Entity display summaries -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
