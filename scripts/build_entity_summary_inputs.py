#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from model.unified import EntityOccurrence, UnifiedEvent, UnifiedKnowledgeBase, UnifiedLocation, UnifiedRole


SUMMARY_INPUTS_VERSION = "entity-summary-inputs-v1"


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
    if not stripped:
        return True
    if len(stripped) < 8:
        return True
    banned_prefixes = (
        "“", "天气", "天色", "清晨", "凌晨", "夜幕", "暮色", "忽然", "突然",
    )
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
        excerpts.extend(
            {"phase": bucket_name, **item}
            for item in buckets[bucket_name]
        )
    return excerpts, excerpt_ids


def _role_top_locations(role: UnifiedRole, events: Iterable[UnifiedEvent]) -> List[str]:
    counter: Counter[str] = Counter()
    names = {role.canonical_name, *role.all_names}
    for event in events:
        if event.location and names.intersection(event.participants):
            counter[event.location] += 1
    return [name for name, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:8]]


def _role_representative_events(role: UnifiedRole, events: Iterable[UnifiedEvent]) -> List[dict]:
    related: List[Tuple[int, dict]] = []
    names = {role.canonical_name, *role.all_names}
    for event in events:
        if not names.intersection(event.participants):
            continue
        score = 0
        score += 3 if event.significance else 0
        score += 2 if event.location else 0
        score += min(len(event.participants), 3)
        score += len(event.source_units or event.source_juans)
        related.append(
            (
                score,
                {
                    "event_id": event.id,
                    "name": event.name,
                    "location": event.location,
                    "participants": sorted(event.participants),
                    "description": event.description,
                    "significance": event.significance,
                    "source_units": sorted(event.source_units or event.source_juans),
                },
            )
        )
    related.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [item for _, item in related[:8]]


def _location_top_roles(location: UnifiedLocation, events: Iterable[UnifiedEvent]) -> List[str]:
    counter: Counter[str] = Counter(location.associated_entities)
    for event in events:
        if event.location == location.canonical_name:
            for participant in event.participants:
                counter[participant] += 1
    return [name for name, _ in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:8]]


def _location_top_events(location: UnifiedLocation, events: Iterable[UnifiedEvent]) -> List[dict]:
    related: List[Tuple[int, dict]] = []
    for event in events:
        if event.location != location.canonical_name:
            continue
        score = 0
        score += 3 if event.significance else 0
        score += min(len(event.participants), 3)
        score += len(event.source_units or event.source_juans)
        related.append(
            (
                score,
                {
                    "event_id": event.id,
                    "name": event.name,
                    "participants": sorted(event.participants),
                    "description": event.description,
                    "significance": event.significance,
                    "source_units": sorted(event.source_units or event.source_juans),
                },
            )
        )
    related.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [item for _, item in related[:8]]


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_entity_summary_inputs(
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
        payload = {
            "entity_type": "role",
            "entity_id": role.id,
            "canonical_name": role.canonical_name,
            "all_names": sorted(role.all_names),
            "primary_power": role.primary_power,
            "powers": role.powers,
            "first_appearance_juan": role.first_appearance_juan,
            "last_appearance_juan": role.last_appearance_juan,
            "total_mentions": role.total_mentions,
            "top_related_entities": sorted(role.related_entities)[:12],
            "top_locations": _role_top_locations(role, all_events),
            "representative_events": _role_representative_events(role, all_events),
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
            "representative_original_excerpts": excerpts,
            "top_roles": _location_top_roles(location, all_events),
            "top_events": _location_top_events(location, all_events),
            "original_descriptions": location.original_descriptions[:12],
        }
        payload["input_hash"] = _hash_payload(payload)
        payload["evidence_excerpt_ids"] = excerpt_ids
        location_inputs.append(payload)

    return {
        "version": SUMMARY_INPUTS_VERSION,
        "generated_at": datetime.now().isoformat(),
        "book_id": kb.book_id,
        "roles": role_inputs,
        "locations": location_inputs,
    }


def build_entity_summary_inputs_file(
    *,
    kb_input_path: Path,
    output_path: Path,
    max_entities: Optional[int] = None,
) -> dict:
    kb = load_kb(kb_input_path)
    payload = build_entity_summary_inputs(kb=kb, max_entities=max_entities)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Entity summary inputs -> {output_path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build post-resolve entity summary input packs.")
    parser.add_argument("--kb-input", default="data/unified_knowledge.json", help="Unified knowledge JSON path.")
    parser.add_argument("--store-dir", default="data/swordcoming_offline_store", help="Reserved for compatibility.")
    parser.add_argument("--output", default="data/entity_summary_inputs.json", help="Output JSON path.")
    parser.add_argument("--book-config", default="data/book_config.json", help="Reserved for compatibility.")
    parser.add_argument("--max-entities", type=int, default=None, help="Optional limit for quick iteration.")
    args = parser.parse_args()

    build_entity_summary_inputs_file(
        kb_input_path=Path(args.kb_input),
        output_path=Path(args.output),
        max_entities=args.max_entities,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
