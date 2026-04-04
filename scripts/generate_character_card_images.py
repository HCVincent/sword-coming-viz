#!/usr/bin/env python3
"""
Generate character card images for the 24 high-value roster via Nano Banana 2.

Reads:
  - data/character_visual_profiles.json  (image_prompt_base + negative_constraints)

Outputs:
  - visualization/public/generated/character_cards/<role_id>.png  (one per role)
  - data/character_card_images.json                                (manifest)

Usage:
  GEMINI_API_KEY=... uv run python scripts/generate_character_card_images.py
  GEMINI_API_KEY=... uv run python scripts/generate_character_card_images.py --role 陈平安
  GEMINI_API_KEY=... uv run python scripts/generate_character_card_images.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
IMAGE_DIR = PROJECT_ROOT / "visualization" / "public" / "generated" / "character_cards"
MANIFEST_PATH = PROJECT_ROOT / "data" / "character_card_images.json"
ASPECT_RATIO = "3:4"
IMAGE_SIZE = "1K"
MAX_RETRIES = 2
CALL_DELAY = 4.0  # seconds between API calls to avoid rate limiting


def _load_profiles() -> list[dict]:
    path = PROJECT_ROOT / "data" / "character_visual_profiles.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("profiles", [])


def _build_prompt(profile: dict) -> str:
    """Build the full image prompt from a visual profile entry."""
    base = profile.get("image_prompt_base", "")
    constraints = profile.get("negative_constraints", [])
    neg_text = " ".join(f"Do NOT include: {c}." for c in constraints[:5]) if constraints else ""
    # Era-enforcing style block
    style = (
        "Style: cinematic concept art, realistic, muted tones, Chinese historical fantasy, "
        "character portrait, Databank-style character card. "
        "Pre-modern setting — all clothing, accessories, and materials must look authentically "
        "ancient / pre-industrial: hand-woven cotton, linen, silk, leather, iron, wood, bamboo. "
        "No modern tailoring, no zippers, no modern shoes, no modern hairstyles or makeup. "
        "No text overlays, no watermarks, no borders, no background clutter. "
        "Clean background with soft gradient. Upper body / bust framing."
    )
    return f"{base}\n\n{style}\n\n{neg_text}".strip()


def generate_image(
    prompt: str,
    api_key: str,
    model: str,
    output_path: Path,
) -> None:
    """Call Nano Banana 2 to generate one character card image."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=ASPECT_RATIO,
                image_size=IMAGE_SIZE,
            ),
        ),
    )

    # Extract and save the image
    saved = False
    for part in response.parts:
        if part.inline_data is not None:
            image = part.as_image()
            image.save(str(output_path))
            saved = True
            break

    if not saved:
        raise RuntimeError("Nano Banana 2 response contained no image data.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate character card images via Nano Banana 2")
    parser.add_argument("--role", type=str, help="Generate for a single role only")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling API")
    parser.add_argument("--model", type=str, default=None, help="Override model name")
    args = parser.parse_args()

    model = args.model or os.getenv("GEMINI_IMAGE_MODEL", "").strip() or DEFAULT_MODEL
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        print("❌ Missing GEMINI_API_KEY. Set it or use --dry-run.")
        sys.exit(1)

    profiles = _load_profiles()
    if not profiles:
        print("❌ No profiles found in character_visual_profiles.json")
        sys.exit(1)

    # Filter if single role
    if args.role:
        profiles = [p for p in profiles if p["role_id"] == args.role]
        if not profiles:
            print(f"❌ Role '{args.role}' not found in profiles")
            sys.exit(1)

    # Create output directory
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing manifest (for incremental generation)
    existing: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for entry in manifest.get("images", []):
                existing[entry["role_id"]] = entry
            print(f"  📂 Loaded {len(existing)} existing entries from manifest")
        except Exception:
            pass

    results: list[dict] = []
    errors: list[str] = []

    for i, profile in enumerate(profiles):
        role_id = profile["role_id"]
        file_name = f"{role_id}.png"
        output_path = IMAGE_DIR / file_name

        # Skip if already generated (unless single-role mode)
        if role_id in existing and output_path.exists() and not args.role:
            print(f"  [{i+1}/{len(profiles)}] {role_id} — already exists, skipping")
            results.append(existing[role_id])
            continue

        prompt = _build_prompt(profile)

        if args.dry_run:
            print(f"\n{'='*60}")
            print(f"  [{i+1}/{len(profiles)}] {role_id} — DRY RUN")
            print(f"{'='*60}")
            print(prompt[:400] + "...")
            continue

        print(f"  [{i+1}/{len(profiles)}] {role_id} — generating image...", end=" ", flush=True)

        success = False
        for attempt in range(MAX_RETRIES + 1):
            try:
                generate_image(prompt, api_key, model, output_path)
                entry = {
                    "role_id": role_id,
                    "file_name": file_name,
                    "prompt_used": prompt[:500],
                    "aspect_ratio": ASPECT_RATIO,
                    "generated_at": datetime.now().isoformat(),
                }
                results.append(entry)
                print("✓")
                success = True
                break
            except Exception as e:
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
        print(f"\n  Dry run complete. {len(profiles)} roles would be processed.")
        return

    # Merge with existing entries not in this run
    run_ids = {p["role_id"] for p in profiles}
    for rid, entry in existing.items():
        if rid not in run_ids:
            results.append(entry)

    # Write manifest
    manifest = {
        "version": "character-card-images-v1",
        "generated_at": datetime.now().isoformat(),
        "model": model,
        "images": sorted(results, key=lambda x: x["role_id"]),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  ✓ Wrote manifest: {MANIFEST_PATH} ({len(results)} images)")
    if errors:
        print(f"  ⚠ {len(errors)} errors:")
        for e in errors:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
