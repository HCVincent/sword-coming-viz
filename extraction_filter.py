"""Post-LLM extraction noise filter for Stage B.

Provides ``filter_extraction_noise()`` which removes pseudo-role entities
from an ``EntityRelationExtraction`` and cascades the cleanup to events,
locations, and relations.

This module is deliberately kept free of heavy side-effects (no DeepSeek
client init, no file I/O at import time) so it can be imported cheaply by
both ``knowledge_extraction.py`` and the test suite.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Collection, Set

from model.extraction import EntityRelationExtraction
from scripts.character_quality import (
    is_pseudo_role_name,
    build_allowed_special_designator_names,
)


def load_filter_context(
    core_cast_path: str | Path = "data/swordcoming_core_cast.json",
    manual_overrides_path: str | Path = "data/swordcoming_manual_overrides.json",
    core_cast_top_n: int = 50,
) -> dict:
    """Load data needed for extraction noise filtering.

    Returns a dict with keys:
    - ``blocked_aliases``: list[str]
    - ``allowed_special_names``: set[str]
    - ``canonical_role_set``: set[str]
    - ``known_characters_payload``: list[dict] for prompt injection
    """
    core_cast_path = Path(core_cast_path)
    manual_overrides_path = Path(manual_overrides_path)

    # Core cast
    core_cast_characters: list[dict] = []
    if core_cast_path.exists():
        cc_data = json.loads(core_cast_path.read_text(encoding="utf-8"))
        core_cast_characters = cc_data.get("characters", [])[:core_cast_top_n]

    known_characters_payload = [
        {"name": c["name"], "aliases": c.get("aliases", []), "power": c.get("power", "")}
        for c in core_cast_characters
        if c.get("name")
    ]

    # Manual overrides
    manual_overrides: dict = {}
    if manual_overrides_path.exists():
        manual_overrides = json.loads(manual_overrides_path.read_text(encoding="utf-8"))

    blocked_aliases: list[str] = manual_overrides.get("blocked_aliases", [])
    allowed_special_names: set[str] = build_allowed_special_designator_names(
        manual_overrides.get("allowed_special_designators", [])
    )

    # Build the full known-name set for concat/sticky detection.
    # Must include canonical names, alias keys, alias values, ASD names
    # and their canonical_targets.
    canonical_role_set: set[str] = set()
    for c in core_cast_characters:
        if c.get("name"):
            canonical_role_set.add(c["name"])
        for a in c.get("aliases", []):
            if a:
                canonical_role_set.add(str(a))
    crn = manual_overrides.get("canonical_role_names", {}) or {}
    for k, v in crn.items():
        if k:
            canonical_role_set.add(str(k))
        if v:
            canonical_role_set.add(str(v))
    ra = manual_overrides.get("role_aliases", {}) or {}
    for k, aliases in ra.items():
        if k:
            canonical_role_set.add(str(k))
        for a in aliases:
            if a:
                canonical_role_set.add(str(a))
    asd_entries = manual_overrides.get("allowed_special_designators", []) or []
    for entry in asd_entries:
        if isinstance(entry, dict):
            n = entry.get("name", "")
            if n:
                canonical_role_set.add(str(n))
            t = entry.get("canonical_target", "")
            if t:
                canonical_role_set.add(str(t))
        elif isinstance(entry, str) and entry.strip():
            canonical_role_set.add(entry.strip())

    return {
        "blocked_aliases": blocked_aliases,
        "allowed_special_names": allowed_special_names,
        "canonical_role_set": canonical_role_set,
        "known_characters_payload": known_characters_payload,
    }


def filter_extraction_noise(
    extraction: EntityRelationExtraction,
    *,
    blocked_aliases: Collection[str] = (),
    allowed_special_names: Collection[str] = (),
    canonical_role_set: Collection[str] = (),
) -> EntityRelationExtraction:
    """Post-LLM noise filter: remove pseudo-role entities and cascade cleanup.

    Precedence: allowed_special_designators > canonical/aliases > blocked/generic/noise.

    Cascading rules:
    - Filtered person names are removed from ``event.participants`` and
      ``location.related_entities``.
    - Relations where either endpoint was filtered are discarded entirely.
    """
    _blocked = list(blocked_aliases)
    _allowed = set(str(n) for n in allowed_special_names)
    _canonical = set(str(n) for n in canonical_role_set)

    filtered_names: Set[str] = set()
    surviving_entities = []

    for entity in extraction.entities:
        etype = getattr(entity, "entity_type", "person") or "person"
        if etype != "person":
            surviving_entities.append(entity)
            continue
        name = (entity.name or "").strip()
        if not name:
            continue
        if is_pseudo_role_name(
            name,
            blocked_names=_blocked,
            canonical_roles=_canonical,
            allowed_names=_allowed,
        ):
            filtered_names.add(name)
            continue
        # Also check aliases — drop pseudo aliases but keep the entity
        clean_aliases = []
        for alias in (entity.alias or []):
            alias_s = (alias or "").strip()
            if alias_s and not is_pseudo_role_name(
                alias_s,
                blocked_names=_blocked,
                canonical_roles=_canonical,
                allowed_names=_allowed,
            ):
                clean_aliases.append(alias_s)
        entity.alias = clean_aliases
        surviving_entities.append(entity)

    extraction.entities = surviving_entities

    # Cascade: clean event participants
    for event in extraction.events:
        if event.participants:
            event.participants = [p for p in event.participants if p not in filtered_names]

    # Cascade: clean location related_entities
    for location in extraction.locations:
        if location.related_entities:
            location.related_entities = [
                e for e in location.related_entities if e not in filtered_names
            ]

    # Cascade: drop relations with filtered endpoints
    surviving_relations = []
    for relation in extraction.relations:
        from_clean = [r for r in (relation.from_roles or []) if r not in filtered_names]
        to_clean = [r for r in (relation.to_roles or []) if r not in filtered_names]
        if from_clean and to_clean:
            relation.from_roles = from_clean
            relation.to_roles = to_clean
            surviving_relations.append(relation)
    extraction.relations = surviving_relations

    return extraction
