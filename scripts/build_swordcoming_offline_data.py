#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from entity_resolution import load_and_resolve, save_unified_knowledge_base
from knowledge_store import ChunkExtraction
from model.action import Action
from model.event import Event
from model.location import Location
from model.role import Role
from scripts.build_swordcoming_writer_insights import build_writer_insights_file
from scripts.validate_unified_knowledge import validate_unified_knowledge


DEFAULT_SYNC_FILES = [
    "book_config.json",
    "unit_progress_index.json",
    "unified_knowledge.json",
    "writer_insights.json",
    "swordcoming_book.json",
]

SYMMETRIC_ACTIONS = {"对话", "会见", "冲突", "同行"}


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


def build_matchers(items: Sequence[dict], aliases_key: str = "aliases") -> List[Tuple[str, str]]:
    matchers: List[Tuple[str, str]] = []
    for item in items:
        canonical = str(item["name"]).strip()
        aliases = unique_names([canonical, *item.get(aliases_key, [])])
        for alias in aliases:
            matchers.append((alias, canonical))
    return sorted(matchers, key=lambda item: (-len(item[0]), item[0]))


def match_entities(text: str, matchers: Sequence[Tuple[str, str]]) -> List[Tuple[str, str, int, int]]:
    matches: List[Tuple[str, str, int, int]] = []
    occupied: List[Tuple[int, int]] = []

    for alias, canonical in matchers:
        start = 0
        while True:
            index = text.find(alias, start)
            if index < 0:
                break
            end = index + len(alias)
            overlaps = any(not (end <= left or index >= right) for left, right in occupied)
            if not overlaps:
                matches.append((canonical, alias, index, end))
                occupied.append((index, end))
            start = index + len(alias)

    return sorted(matches, key=lambda item: item[2])


def build_sentence_mentions(
    sentences: Sequence[str],
    character_matchers: Sequence[Tuple[str, str]],
    location_matchers: Sequence[Tuple[str, str]],
) -> Tuple[List[List[str]], List[List[str]]]:
    sentence_characters: List[List[str]] = []
    sentence_locations: List[List[str]] = []

    for sentence in sentences:
        character_matches = match_entities(sentence, character_matchers)
        location_matches = match_entities(sentence, location_matchers)
        sentence_characters.append(unique_names(match[0] for match in character_matches))
        sentence_locations.append(unique_names(match[0] for match in location_matches))

    return sentence_characters, sentence_locations


def choose_summary_sentences(
    sentences: Sequence[str],
    sentence_characters: Sequence[Sequence[str]],
    sentence_locations: Sequence[Sequence[str]],
    limit: int = 3,
) -> List[str]:
    prioritized: List[str] = []
    fallback: List[str] = []

    for sentence, characters, locations in zip(sentences, sentence_characters, sentence_locations):
        if characters or locations:
            prioritized.append(sentence)
        elif sentence:
            fallback.append(sentence)

    selected = prioritized[:limit]
    if len(selected) < limit:
        selected.extend(fallback[: limit - len(selected)])
    return selected


def classify_relation_action(sentence: str, relation_keywords: Sequence[dict]) -> Optional[str]:
    best_action: Optional[str] = None
    best_hits = 0
    for item in relation_keywords:
        keywords = [str(keyword).strip() for keyword in item.get("keywords", []) if str(keyword).strip()]
        hits = sum(1 for keyword in keywords if keyword in sentence)
        if hits > best_hits:
            best_hits = hits
            best_action = str(item["action"])
    return best_action


def orient_relation(characters: Sequence[str], sentence: str, action: str) -> List[Tuple[str, str]]:
    if len(characters) < 2:
        return []

    positions = sorted((sentence.find(name), name) for name in characters)
    ordered_names = unique_names(name for position, name in positions if position >= 0)
    if len(ordered_names) < 2:
        ordered_names = unique_names(characters)

    if action in SYMMETRIC_ACTIONS:
        limited = ordered_names[:4]
        return [(left, right) for left, right in combinations(limited, 2)]

    source = ordered_names[0]
    targets = ordered_names[1:4]
    return [(source, target) for target in targets if target != source]


def classify_event_type(
    unit_title: str,
    sentences: Sequence[str],
    event_type_rules: Sequence[dict],
    relation_actions: Sequence[Action],
) -> str:
    haystack = "\n".join([unit_title, *sentences])
    best_type = ""
    best_score = 0

    for rule in event_type_rules:
        event_type = str(rule.get("type", "")).strip()
        if not event_type:
            continue
        keywords = [str(keyword).strip() for keyword in rule.get("keywords", []) if str(keyword).strip()]
        hits = sum(1 for keyword in keywords if keyword in haystack)
        if hits > best_score:
            best_score = hits
            best_type = event_type

    if best_type:
        return best_type
    if relation_actions:
        return relation_actions[0].action
    return "剧情推进"


def match_event_rule(unit_title: str, sentences: Sequence[str], rules: Sequence[dict]) -> Optional[dict]:
    haystack = "\n".join([unit_title, *sentences])
    best_rule: Optional[dict] = None
    best_score = 0

    for rule in rules:
        keywords = rule.get("keywords", [])
        hits = sum(1 for keyword in keywords if keyword and keyword in haystack)
        min_keywords = int(rule.get("min_keywords", len(keywords) or 1))
        if hits >= min_keywords and hits > best_score:
            best_rule = rule
            best_score = hits

    return best_rule


def build_event_name(
    *,
    unit_title: str,
    event_type: str,
    participants: Sequence[str],
    location: Optional[str],
) -> str:
    if len(participants) >= 2 and location:
        base = f"{participants[0]}与{participants[1]}在{location}{event_type}"
    elif len(participants) >= 2:
        base = f"{participants[0]}与{participants[1]}{event_type}"
    elif participants and location:
        base = f"{participants[0]}在{location}{event_type}"
    elif participants:
        base = f"{participants[0]}{event_type}"
    elif location:
        base = f"{location}{event_type}"
    else:
        base = event_type or "关键场景"
    return f"{unit_title} · {base}"


def infer_significance(
    *,
    event_type: str,
    participants: Sequence[str],
    location: Optional[str],
) -> str:
    if len(participants) >= 2 and location:
        return f"在{location}推动{participants[0]}与{participants[1]}之间的{event_type}线。"
    if len(participants) >= 2:
        return f"推动{participants[0]}与{participants[1]}之间的{event_type}关系。"
    if participants:
        return f"对应{participants[0]}在叙事中的关键{event_type}节点。"
    if location:
        return f"对应{location}相关的关键{event_type}场景。"
    return f"对应当前章节中的关键{event_type}节点。"


def select_event_participants(
    *,
    sentence_characters: Sequence[Sequence[str]],
    relation_actions: Sequence[Action],
    rule: Optional[dict],
) -> List[str]:
    seeded = unique_names(rule.get("participants", []) if rule else [])
    if relation_actions:
        relation_participants = unique_names(
            name
            for relation in relation_actions
            for name in [*relation.from_roles, *relation.to_roles]
        )
        participants = unique_names([*seeded, *relation_participants])
        if participants:
            return participants[:4]

    counts = Counter(name for names in sentence_characters for name in names)
    ranked = [name for name, _ in counts.most_common(4)]
    return unique_names([*seeded, *ranked])[:4]


def build_event(
    *,
    unit: dict,
    segment: dict,
    sentences: Sequence[str],
    sentence_characters: Sequence[Sequence[str]],
    sentence_locations: Sequence[Sequence[str]],
    relation_actions: Sequence[Action],
    event_rules: Sequence[dict],
    event_type_rules: Sequence[dict],
) -> Optional[Event]:
    characters = unique_names(name for items in sentence_characters for name in items)
    locations = unique_names(name for items in sentence_locations for name in items)
    unit_title = str(unit["unit_title"])
    rule = match_event_rule(unit_title, sentences, event_rules)

    if not characters and not locations and not rule:
        return None

    participants = select_event_participants(
        sentence_characters=sentence_characters,
        relation_actions=relation_actions,
        rule=rule,
    )
    location = (rule.get("location") if rule and rule.get("location") else None) or (locations[0] if locations else None)
    description = " ".join(choose_summary_sentences(sentences, sentence_characters, sentence_locations))
    event_type = str(rule.get("event_type", "")) if rule else ""
    if not event_type:
        event_type = classify_event_type(unit_title, sentences, event_type_rules, relation_actions)
    name = str(rule["name"]) if rule else build_event_name(
        unit_title=unit_title,
        event_type=event_type,
        participants=participants,
        location=location,
    )
    background = str(rule.get("background", "")) if rule else ""
    significance = (
        str(rule["significance"])
        if rule and rule.get("significance")
        else infer_significance(event_type=event_type, participants=participants, location=location)
    )

    return Event(
        name=name,
        time=None,
        location=location,
        participants=participants,
        description=description or unit_title,
        background=background,
        significance=significance,
        related_action_indices=list(range(len(relation_actions))),
        source=f"{unit_title} · 段{int(segment['segment_index'])}",
        sentence_indexes_in_segment=list(range(len(sentences))),
        juan_index=int(unit["juan_index"]),
        segment_index=int(segment["segment_index"]),
    )


def build_segment_chunk(
    unit: dict,
    segment: dict,
    character_config: Dict[str, dict],
    location_config: Dict[str, dict],
    character_matchers: Sequence[Tuple[str, str]],
    location_matchers: Sequence[Tuple[str, str]],
    relation_keywords: Sequence[dict],
    event_rules: Sequence[dict],
    event_type_rules: Sequence[dict],
) -> Optional[ChunkExtraction]:
    sentences = [str(sentence).strip() for sentence in segment.get("sentences", []) if str(sentence).strip()]
    if not sentences:
        return None

    sentence_characters, sentence_locations = build_sentence_mentions(sentences, character_matchers, location_matchers)
    segment_characters = unique_names(name for items in sentence_characters for name in items)
    segment_locations = unique_names(name for items in sentence_locations for name in items)

    roles: List[Role] = []
    for name in segment_characters:
        config = character_config[name]
        indexes = [index for index, names in enumerate(sentence_characters) if name in names]
        description = " ".join(sentences[index] for index in indexes[:2])
        roles.append(
            Role(
                entity_type="person",
                name=name,
                alias=[alias for alias in config.get("aliases", []) if alias != name],
                original_description_in_book=description,
                description=str(config.get("description", "")),
                power=config.get("power"),
                sentence_indexes_in_segment=indexes,
                juan_index=int(unit["juan_index"]),
                segment_index=int(segment["segment_index"]),
            )
        )

    locations: List[Location] = []
    for name in segment_locations:
        config = location_config[name]
        indexes = [index for index, names in enumerate(sentence_locations) if name in names]
        associated = unique_names(character for index in indexes for character in sentence_characters[index])
        locations.append(
            Location(
                name=name,
                alias=[alias for alias in config.get("aliases", []) if alias != name],
                type=str(config.get("type", "")),
                description=str(config.get("description", "")),
                modern_name=str(config.get("modern_name", "")),
                coordinates=None,
                related_entities=associated,
                sentence_indexes_in_segment=indexes,
                juan_index=int(unit["juan_index"]),
                segment_index=int(segment["segment_index"]),
            )
        )

    relations: List[Action] = []
    seen_relations = set()
    for index, sentence in enumerate(sentences):
        characters = sentence_characters[index]
        if len(characters) < 2:
            continue
        action_name = classify_relation_action(sentence, relation_keywords)
        if not action_name:
            continue
        relation_location = sentence_locations[index][0] if sentence_locations[index] else (segment_locations[0] if segment_locations else None)
        for source, target in orient_relation(characters, sentence, action_name):
            key = (source, target, action_name, sentence)
            if key in seen_relations:
                continue
            seen_relations.add(key)
            relations.append(
                Action(
                    time=None,
                    from_roles=[source],
                    to_roles=[target],
                    action=action_name,
                    context=sentence,
                    result=None,
                    event_name=None,
                    location=relation_location,
                    is_commentary=False,
                    sentence_indexes_in_segment=[index],
                    juan_index=int(unit["juan_index"]),
                    segment_index=int(segment["segment_index"]),
                )
            )

    if not relations and len(segment_characters) == 2:
        combined_text = " ".join(sentences)
        action_name = classify_relation_action(combined_text, relation_keywords)
        if action_name:
            source, target = orient_relation(segment_characters, combined_text, action_name)[0]
            relations.append(
                Action(
                    time=None,
                    from_roles=[source],
                    to_roles=[target],
                    action=action_name,
                    context=combined_text,
                    result=None,
                    event_name=None,
                    location=segment_locations[0] if segment_locations else None,
                    is_commentary=False,
                    sentence_indexes_in_segment=list(range(len(sentences))),
                    juan_index=int(unit["juan_index"]),
                    segment_index=int(segment["segment_index"]),
                )
            )

    event = build_event(
        unit=unit,
        segment=segment,
        sentences=sentences,
        sentence_characters=sentence_characters,
        sentence_locations=sentence_locations,
        relation_actions=relations,
        event_rules=event_rules,
        event_type_rules=event_type_rules,
    )

    if event:
        for relation in relations:
            relation.event_name = event.name

    if not roles and not locations and not relations and not event:
        return None

    return ChunkExtraction(
        juan_index=int(unit["juan_index"]),
        segment_index=int(segment["segment_index"]),
        chunk_start_index=0,
        chunk_end_index=len(sentences),
        segment_start_time=str(segment.get("segment_start_time") or unit["unit_title"]),
        source_sentences=sentences,
        entities=roles,
        locations=locations,
        events=[event] if event else [],
        relations=relations,
        model_name="offline-rules-v2",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )


def write_store(chunks_by_juan: Dict[int, Dict[str, dict]], store_dir: Path) -> None:
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)

    last_juan = 0
    last_segment = 0
    total_chunks = 0

    for juan_index, chunks in sorted(chunks_by_juan.items()):
        if not chunks:
            continue
        path = store_dir / f"juan_{juan_index}.json"
        path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        total_chunks += len(chunks)
        last_juan = juan_index
        last_segment = max(item["segment_index"] for item in chunks.values())

    metadata = {
        "created_at": datetime.now().isoformat(),
        "version": "swordcoming-offline-v2",
        "progress": {
            "last_juan": last_juan,
            "last_segment": last_segment,
            "last_chunk": 0,
            "total_chunks_processed": total_chunks,
        },
    }
    (store_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_public_files(source_dir: Path, target_dir: Path, files: Sequence[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in files:
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, target_dir / name)
            print(f"Copied {source} -> {target_dir / name}")


def build_offline_data(
    book_path: Path,
    core_cast_path: Path,
    store_dir: Path,
    kb_output: Path,
    writer_output: Path,
    unit_progress_index_path: Path,
    book_config_path: Path,
    manual_overrides_path: Path,
    sync_output: bool = False,
    public_data_dir: Optional[Path] = None,
    max_units: Optional[int] = None,
) -> dict:
    book = load_json(book_path)
    core_cast = load_json(core_cast_path)

    if max_units is not None:
        book = book[:max_units]

    character_config = {item["name"]: item for item in core_cast.get("characters", [])}
    location_config = {item["name"]: item for item in core_cast.get("locations", [])}
    character_matchers = build_matchers(core_cast.get("characters", []))
    location_matchers = build_matchers(core_cast.get("locations", []))

    chunks_by_juan: Dict[int, Dict[str, dict]] = defaultdict(dict)
    extracted_roles = 0
    extracted_locations = 0
    extracted_events = 0
    extracted_relations = 0

    for unit in book:
        for segment in unit.get("segments", []):
            chunk = build_segment_chunk(
                unit=unit,
                segment=segment,
                character_config=character_config,
                location_config=location_config,
                character_matchers=character_matchers,
                location_matchers=location_matchers,
                relation_keywords=core_cast.get("relation_keywords", []),
                event_rules=core_cast.get("event_rules", []),
                event_type_rules=core_cast.get("event_type_rules", []),
            )
            if chunk is None:
                continue

            key = f"{chunk.juan_index}-{chunk.segment_index}-{chunk.chunk_start_index}"
            chunks_by_juan[chunk.juan_index][key] = chunk.model_dump()
            extracted_roles += len(chunk.entities)
            extracted_locations += len(chunk.locations)
            extracted_events += len(chunk.events)
            extracted_relations += len(chunk.relations)

    write_store(chunks_by_juan, store_dir)

    kb = load_and_resolve(
        str(store_dir),
        unit_progress_index_path=str(unit_progress_index_path),
        book_config_path=str(book_config_path),
        manual_overrides_path=str(manual_overrides_path),
    )
    save_unified_knowledge_base(kb, str(kb_output))

    suspicious = validate_unified_knowledge(kb_output)
    if suspicious:
        raise ValueError(f"Unified knowledge output still contains placeholder question marks: {suspicious[:5]}")

    writer_payload = build_writer_insights_file(
        kb=kb,
        unit_progress_index_path=unit_progress_index_path,
        core_cast_path=core_cast_path,
        output_path=writer_output,
    )
    writer_suspicious = validate_unified_knowledge(writer_output)
    if writer_suspicious:
        raise ValueError(f"Writer insights output still contains placeholder question marks: {writer_suspicious[:5]}")

    if sync_output and public_data_dir is not None:
        sync_public_files(book_path.parent, public_data_dir, DEFAULT_SYNC_FILES)

    return {
        "chunks": sum(len(chunks) for chunks in chunks_by_juan.values()),
        "roles": kb.total_roles,
        "locations": kb.total_locations,
        "events": kb.total_events,
        "relations": kb.total_relations,
        "raw_roles": extracted_roles,
        "raw_locations": extracted_locations,
        "raw_events": extracted_events,
        "raw_relations": extracted_relations,
        "writer_character_arcs": writer_payload["summary"]["character_arc_count"],
        "writer_season_overviews": writer_payload["summary"]["season_overview_count"],
        "writer_curated_relationships": writer_payload["summary"]["curated_relationship_count"],
        "writer_conflict_chains": writer_payload["summary"]["conflict_chain_count"],
        "writer_foreshadowing_threads": writer_payload["summary"]["foreshadowing_thread_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Sword Coming offline knowledge data without model APIs.")
    parser.add_argument("--book", default="data/swordcoming_book.json", help="Input Sword Coming book JSON.")
    parser.add_argument("--core-cast", default="data/swordcoming_core_cast.json", help="Core cast/location config.")
    parser.add_argument("--store-dir", default="data/swordcoming_offline_store", help="Offline extraction store output dir.")
    parser.add_argument("--kb-output", default="data/unified_knowledge.json", help="Unified knowledge output path.")
    parser.add_argument("--writer-output", default="data/writer_insights.json", help="Writer insights output path.")
    parser.add_argument("--unit-progress-index", default="data/unit_progress_index.json", help="Unit progress index path.")
    parser.add_argument("--book-config", default="data/book_config.json", help="Book config path.")
    parser.add_argument("--manual-overrides", default="data/swordcoming_manual_overrides.json", help="Manual overrides path.")
    parser.add_argument("--sync", action="store_true", help="Sync output files into visualization/public/data.")
    parser.add_argument("--public-data-dir", default="visualization/public/data", help="Vite public/data directory.")
    parser.add_argument("--max-units", type=int, default=None, help="Optional limit for quick iteration.")
    args = parser.parse_args()

    stats = build_offline_data(
        book_path=Path(args.book),
        core_cast_path=Path(args.core_cast),
        store_dir=Path(args.store_dir),
        kb_output=Path(args.kb_output),
        writer_output=Path(args.writer_output),
        unit_progress_index_path=Path(args.unit_progress_index),
        book_config_path=Path(args.book_config),
        manual_overrides_path=Path(args.manual_overrides),
        sync_output=args.sync,
        public_data_dir=Path(args.public_data_dir),
        max_units=args.max_units,
    )

    print("Built Sword Coming offline data:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
