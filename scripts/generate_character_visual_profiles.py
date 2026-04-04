#!/usr/bin/env python3
"""
Generate character_visual_profiles.json for the high-value 24 roster via Gemini.

Reads:
  - data/high_value_role_roster.json   (the 24 targets)
  - data/entity_profiles.json          (rich text profiles)
  - data/unified_knowledge.json        (source excerpts, power, aliases)
  - data/writer_insights.json          (character arcs, season context)
  - prompts/sys_character_visual_profile.md
  - prompts/user_character_visual_profile.md

Outputs:
  - data/character_visual_profiles.json

Usage:
  GEMINI_API_KEY=... uv run python scripts/generate_character_visual_profiles.py
  GEMINI_API_KEY=... uv run python scripts/generate_character_visual_profiles.py --role 陈平安
  GEMINI_API_KEY=... uv run python scripts/generate_character_visual_profiles.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from swordcoming_pipeline.llm_json import LLMJSONParseError, extract_json_from_response
from model.visual_profile import (
    CharacterVisualProfile,
    CharacterVisualProfilesPayload,
)

DEFAULT_MODEL = "gemini-2.5-flash"
OUTPUT_PATH = PROJECT_ROOT / "data" / "character_visual_profiles.json"
MAX_RETRIES = 2
CALL_DELAY = 2.0  # seconds between API calls to avoid rate limiting


# ── Data loaders ─────────────────────────────────────────────────────────

def _load(name: str) -> dict:
    path = PROJECT_ROOT / "data" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _load_prompts():
    sys_path = PROJECT_ROOT / "prompts" / "sys_character_visual_profile.md"
    user_path = PROJECT_ROOT / "prompts" / "user_character_visual_profile.md"
    return (
        sys_path.read_text(encoding="utf-8").strip(),
        user_path.read_text(encoding="utf-8").strip(),
    )


# ── Input assembly ───────────────────────────────────────────────────────

def _get_entity_profile(profiles: list, role_id: str) -> Optional[dict]:
    for p in profiles:
        if p.get("entity_id") == role_id and p.get("entity_type") == "role":
            return p
    return None


def _get_source_excerpts(uk_role: Optional[dict], max_excerpts: int = 8) -> str:
    """Pull a few representative source text excerpts from unified_knowledge."""
    if not uk_role:
        return "（无原文摘录）"
    occs = uk_role.get("occurrences", [])
    if not occs:
        descs = uk_role.get("original_descriptions", [])
        if descs:
            return "\n".join(f"- {d}" for d in descs[:max_excerpts])
        return "（无原文摘录）"
    excerpts = []
    for occ in occs[:max_excerpts]:
        src = occ.get("source_sentence") or occ.get("original_description", "")
        if src:
            excerpts.append(f"- 第{occ.get('juan_index', '?')}卷: {src[:200]}")
    return "\n".join(excerpts) if excerpts else "（无原文摘录）"


def build_user_prompt(
    template: str,
    role_id: str,
    entity_profile: Optional[dict],
    uk_role: Optional[dict],
    character_arc: Optional[dict],
) -> str:
    """Fill the user prompt template with available data for a given role."""
    ep = entity_profile or {}
    uk = uk_role or {}

    power = uk.get("primary_power") or ep.get("primary_power") or "未知"
    rc = ep.get("relationship_clusters", [])
    rc_text = json.dumps(rc, ensure_ascii=False, indent=2) if rc else "（无）"
    tp = ep.get("turning_points", [])
    tp_text = json.dumps(tp, ensure_ascii=False, indent=2) if tp else "（无）"
    excerpts = _get_source_excerpts(uk)

    arc_text = ""
    if character_arc:
        arc_text = (
            f"角色弧线描述: {character_arc.get('description', '')}\n"
            f"主要地点: {', '.join(character_arc.get('key_locations', []))}\n"
        )

    return template.format(
        role_id=role_id,
        canonical_name=ep.get("entity_id", role_id),
        identity_summary=ep.get("identity_summary", "（无）"),
        display_summary=ep.get("display_summary", "（无）"),
        long_description=ep.get("long_description", "（无）"),
        story_function=ep.get("story_function", "（无）"),
        phase_arc=ep.get("phase_arc", "（无）") + ("\n" + arc_text if arc_text else ""),
        power=power,
        relationship_clusters=rc_text,
        turning_points=tp_text,
        source_excerpts=excerpts,
    )


# ── Gemini API call ──────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """Extract text from a Gemini response, tolerating different SDK shapes."""
    if hasattr(response, "text"):
        return response.text or ""
    # Fallback for multi-candidate responses
    for candidate in getattr(response, "candidates", []):
        for part in getattr(candidate, "content", {}).get("parts", []):
            if hasattr(part, "text"):
                return part.text or ""
    return ""


def call_gemini(
    sys_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
) -> dict:
    """Call Gemini API using the google.genai SDK and parse the JSON response."""
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={"system_instruction": sys_prompt},
    )
    text = _extract_text(response)
    if not text:
        raise RuntimeError("Gemini returned empty response text.")
    return extract_json_from_response(text)


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate character visual profiles via Gemini")
    parser.add_argument("--role", type=str, help="Generate for a single role only")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling API")
    parser.add_argument("--model", type=str, default=None, help="Override Gemini model name")
    args = parser.parse_args()

    model = args.model or os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("❌ Missing GEMINI_API_KEY. Set it or use --dry-run.")
        sys.exit(1)

    # Load data sources
    roster = _load("high_value_role_roster.json")
    entity_profiles = _load("entity_profiles.json")
    uk = _load("unified_knowledge.json")
    wi = _load("writer_insights.json")
    sys_prompt, user_template = _load_prompts()

    # Build lookup tables
    arcs_by_name: Dict[str, dict] = {}
    for arc in wi.get("character_arcs", []):
        name = arc.get("role_name") or arc.get("role_id", "")
        if name:
            arcs_by_name[name] = arc

    # Determine targets
    targets = roster.get("roles", [])
    if args.role:
        targets = [r for r in targets if r["role_id"] == args.role]
        if not targets:
            print(f"❌ Role '{args.role}' not found in roster")
            sys.exit(1)

    # Load existing output (for incremental generation)
    existing: Dict[str, dict] = {}
    if OUTPUT_PATH.exists():
        try:
            payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            for p in payload.get("profiles", []):
                existing[p["role_id"]] = p
            print(f"  📂 Loaded {len(existing)} existing profiles from {OUTPUT_PATH.name}")
        except Exception:
            pass

    results: List[dict] = []
    errors: List[str] = []

    for i, entry in enumerate(targets):
        role_id = entry["role_id"]

        # Skip already generated (unless single-role mode)
        if role_id in existing and not args.role:
            print(f"  [{i+1}/{len(targets)}] {role_id} — already exists, skipping")
            results.append(existing[role_id])
            continue

        ep = _get_entity_profile(entity_profiles.get("profiles", []), role_id)
        uk_role = uk.get("roles", {}).get(role_id)
        arc = arcs_by_name.get(role_id)

        user_prompt = build_user_prompt(user_template, role_id, ep, uk_role, arc)

        if args.dry_run:
            print(f"\n{'='*60}")
            print(f"  [{i+1}/{len(targets)}] {role_id} — DRY RUN")
            print(f"{'='*60}")
            print(user_prompt[:500] + "...")
            continue

        print(f"  [{i+1}/{len(targets)}] {role_id} — generating...", end=" ", flush=True)

        success = False
        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = call_gemini(sys_prompt, user_prompt, api_key, model)
                # Validate with Pydantic
                profile = CharacterVisualProfile.model_validate(raw)
                # Ensure role_id matches
                profile.role_id = role_id
                profile.canonical_name = role_id
                results.append(profile.model_dump())
                print("✓")
                success = True
                break
            except (LLMJSONParseError, Exception) as e:
                if attempt < MAX_RETRIES:
                    print(f"retry({attempt+1})...", end=" ", flush=True)
                    time.sleep(CALL_DELAY)
                else:
                    print(f"✗ ({e})")
                    errors.append(f"{role_id}: {e}")

        if not success and role_id in existing:
            results.append(existing[role_id])

        if not args.dry_run:
            time.sleep(CALL_DELAY)

    if args.dry_run:
        print(f"\n  Dry run complete. {len(targets)} roles would be processed.")
        return

    # Merge with any remaining existing profiles not in targets
    target_ids = {r["role_id"] for r in targets}
    for rid, profile_data in existing.items():
        if rid not in target_ids:
            results.append(profile_data)

    # Write output
    payload = CharacterVisualProfilesPayload(
        generated_at=datetime.now().isoformat(),
        model=model,
        profiles=[CharacterVisualProfile.model_validate(r) for r in results],
    )
    OUTPUT_PATH.write_text(
        json.dumps(payload.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  ✓ Wrote {OUTPUT_PATH} ({len(results)} profiles)")
    if errors:
        print(f"  ⚠ {len(errors)} errors:")
        for e in errors:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
