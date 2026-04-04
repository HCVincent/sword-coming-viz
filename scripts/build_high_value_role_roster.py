#!/usr/bin/env python3
"""
Build high_value_role_roster.json — deterministically select the top-24
high-value characters for homepage visual cards and character visual profiles.

Selection logic (scored, not hand-picked):
  1. writer_insights season_overviews → priority_roles (8 pts) + top_roles (5 pts)
  2. writer_insights spotlight_role_name (10 pts)
  3. narrative_units main_roles frequency (1 pt per unit appearance)
  4. key_events_index participant density (0.2 pts per event participation)
  5. entity_profiles existence bonus (3 pts — must have rich profile to be useful)
  6. swordcoming_core_cast membership bonus (1 pt — canonical registry)
  7. relation density from unified_knowledge (0.1 pts per relation endpoint)

Output: data/high_value_role_roster.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

ROSTER_SIZE = 24


def _load(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        print(f"  ⚠ {name} not found, skipping")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    scores: Counter[str] = Counter()

    # ── 1. writer_insights: season_overviews priority_roles / top_roles ──
    wi = _load("writer_insights.json")
    spotlight = wi.get("spotlight_role_name", "")
    if spotlight:
        scores[spotlight] += 10
        print(f"  ★ spotlight: {spotlight} (+10)")

    for so in wi.get("season_overviews", []):
        for entry in so.get("priority_roles", []):
            role = entry["role_id"] if isinstance(entry, dict) else entry
            scores[role] += 8
        for entry in so.get("top_roles", []):
            role = entry["role_id"] if isinstance(entry, dict) else entry
            scores[role] += 5

    # character_arcs: each arc entry adds weight
    for arc in wi.get("character_arcs", []):
        name = arc.get("role_name") or arc.get("role_id", "")
        if name:
            scores[name] += 3  # has a full character arc entry

    # ── 2. narrative_units main_roles frequency ──
    nu = _load("narrative_units.json")
    for unit in nu.get("units", []):
        for role in unit.get("main_roles", []):
            scores[role] += 1

    # ── 3. key_events_index participant density ──
    kei = _load("key_events_index.json")
    for chapter in kei.get("chapters", []):
        for evt in chapter.get("key_events", []):
            for p in evt.get("participants", []):
                scores[p] += 0.2

    # ── 4. entity_profiles existence bonus ──
    ep = _load("entity_profiles.json")
    profiled_ids: set[str] = set()
    for profile in ep.get("profiles", []):
        if profile.get("entity_type") == "role":
            eid = profile.get("entity_id", "")
            profiled_ids.add(eid)
            scores[eid] += 3

    # ── 5. core_cast membership ──
    cc = _load("swordcoming_core_cast.json")
    core_names: set[str] = set()
    for ch in cc.get("characters", []):
        name = ch.get("name", "")
        core_names.add(name)
        scores[name] += 1

    # ── 6. relation density from unified_knowledge ──
    uk = _load("unified_knowledge.json")
    for _rid, rel in uk.get("relations", {}).items():
        fe = rel.get("from_entity", "")
        te = rel.get("to_entity", "")
        if fe:
            scores[fe] += 0.1
        if te:
            scores[te] += 0.1

    # ── Filter: must exist in entity_profiles (need rich data for visual bible) ──
    # If a name scores high but has no profile, flag it but still include if in core_cast
    eligible = {}
    for name, score in scores.items():
        has_profile = name in profiled_ids
        in_core = name in core_names
        if has_profile or in_core:
            eligible[name] = score

    # ── Sort and pick top N ──
    ranked = sorted(eligible.items(), key=lambda x: (-x[1], x[0]))

    print(f"\n  Top {ROSTER_SIZE} candidates (from {len(ranked)} eligible):\n")
    roster_entries = []
    for i, (name, score) in enumerate(ranked[:ROSTER_SIZE]):
        has_profile = name in profiled_ids
        in_core = name in core_names
        print(f"  {i+1:2d}. {name:8s}  score={score:7.1f}  profile={'✓' if has_profile else '✗'}  core={'✓' if in_core else '✗'}")
        roster_entries.append({
            "role_id": name,
            "canonical_name": name,
            "rank": i + 1,
            "selection_score": round(score, 2),
            "has_entity_profile": has_profile,
            "in_core_cast": in_core,
        })

    # Also print the next 10 runners-up for reference
    if len(ranked) > ROSTER_SIZE:
        print(f"\n  Runners-up ({ROSTER_SIZE + 1}–{min(ROSTER_SIZE + 10, len(ranked))}):")
        for i, (name, score) in enumerate(ranked[ROSTER_SIZE : ROSTER_SIZE + 10]):
            print(f"  {ROSTER_SIZE + i + 1:2d}. {name:8s}  score={score:7.1f}")

    payload = {
        "version": "high-value-roster-v1",
        "generated_at": datetime.now().isoformat(),
        "roster_size": ROSTER_SIZE,
        "selection_criteria": (
            "Composite score from: writer_insights spotlight/priority/top roles, "
            "narrative_units main_roles frequency, key_events participants density, "
            "entity_profiles existence, core_cast membership, relation density"
        ),
        "roles": roster_entries,
    }

    out_path = DATA_DIR / "high_value_role_roster.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ Wrote {out_path} ({ROSTER_SIZE} roles)")


if __name__ == "__main__":
    main()
