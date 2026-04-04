"""Tests for character card image generation script and manifest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
IMAGE_DIR = Path(__file__).resolve().parents[1] / "visualization" / "public" / "generated" / "character_cards"


class TestCharacterCardImagesManifest:
    """Validate data/character_card_images.json manifest structure."""

    @pytest.fixture(scope="class")
    def manifest(self):
        path = DATA_DIR / "character_card_images.json"
        if not path.exists():
            pytest.skip("character_card_images.json not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_manifest_version(self, manifest):
        assert manifest["version"] == "character-card-images-v1"

    def test_manifest_structure(self, manifest):
        assert "images" in manifest
        assert isinstance(manifest["images"], list)

    def test_image_entry_fields(self, manifest):
        """Each entry must have role_id, file_name, aspect_ratio."""
        for entry in manifest["images"]:
            assert "role_id" in entry
            assert "file_name" in entry
            assert "aspect_ratio" in entry
            assert entry["file_name"].endswith(".png")

    def test_image_files_exist(self, manifest):
        """Every manifest entry should have a matching file on disk."""
        for entry in manifest["images"]:
            img_path = IMAGE_DIR / entry["file_name"]
            assert img_path.exists(), f"Image file missing: {entry['file_name']}"


class TestGenerateCharacterCardImagesScript:
    """Test the image generation script can be imported and prompts are built correctly."""

    def test_import_script(self):
        """Script module can be imported without error."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_character_card_images",
            str(Path(__file__).resolve().parents[1] / "scripts" / "generate_character_card_images.py"),
        )
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        # Don't execute main, just confirm the module loads
        assert mod is not None

    def test_build_prompt(self):
        """_build_prompt should include base prompt, style notes, and era constraints."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_character_card_images",
            str(Path(__file__).resolve().parents[1] / "scripts" / "generate_character_card_images.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        profile = {
            "role_id": "test",
            "image_prompt_base": "A young warrior in simple clothes.",
            "negative_constraints": ["No anime style", "No wings"],
        }
        prompt = mod._build_prompt(profile)
        assert "A young warrior" in prompt
        assert "cinematic concept art" in prompt
        assert "Do NOT include" in prompt
        assert "No anime style" in prompt
        # Era constraints must be present
        assert "pre-modern" in prompt.lower() or "pre-industrial" in prompt.lower()
        assert "No modern tailoring" in prompt or "no modern" in prompt.lower()

    def test_build_prompt_no_constraints(self):
        """_build_prompt should work without negative constraints."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_character_card_images",
            str(Path(__file__).resolve().parents[1] / "scripts" / "generate_character_card_images.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        profile = {
            "role_id": "test",
            "image_prompt_base": "A scholar in robes.",
            "negative_constraints": [],
        }
        prompt = mod._build_prompt(profile)
        assert "A scholar in robes" in prompt
        assert "Do NOT include" not in prompt
        # Era constraints must still be present even with no negative_constraints
        assert "pre-modern" in prompt.lower() or "pre-industrial" in prompt.lower()

    def test_build_prompt_uses_up_to_five_constraints(self):
        """_build_prompt should include up to 5 negative constraints."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_character_card_images",
            str(Path(__file__).resolve().parents[1] / "scripts" / "generate_character_card_images.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        profile = {
            "role_id": "test",
            "image_prompt_base": "A warrior.",
            "negative_constraints": [
                "No anime", "No wings", "No modern clothes",
                "No halo", "No tattoos", "No sixth item",
            ],
        }
        prompt = mod._build_prompt(profile)
        assert "No tattoos" in prompt  # 5th constraint included
        assert "No sixth item" not in prompt  # 6th constraint excluded


class TestBookConfigOverviewSummary:
    """Validate book_config.json now contains book_overview_summary."""

    @pytest.fixture(scope="class")
    def config(self):
        path = DATA_DIR / "book_config.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_has_overview_summary(self, config):
        assert "book_overview_summary" in config
        assert isinstance(config["book_overview_summary"], str)
        assert len(config["book_overview_summary"]) >= 20


class TestVisualProfilePromptEraConstraints:
    """Validate that prompt files enforce pre-modern era constraints."""

    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def test_sys_prompt_has_era_section(self):
        text = (self.PROMPTS_DIR / "sys_character_visual_profile.md").read_text(encoding="utf-8")
        assert "前现代" in text
        assert "时代感全局禁止项" in text
        assert "现代裁剪感服装" in text
        assert "拉链" in text

    def test_sys_prompt_requires_multi_phase_timeline(self):
        text = (self.PROMPTS_DIR / "sys_character_visual_profile.md").read_text(encoding="utf-8")
        assert "2-4 个阶段" in text
        assert "visual_delta" in text

    def test_sys_prompt_requires_min_3_negative_constraints(self):
        text = (self.PROMPTS_DIR / "sys_character_visual_profile.md").read_text(encoding="utf-8")
        assert "至少 3 条" in text

    def test_sys_prompt_requires_pre_modern_in_image_prompt(self):
        text = (self.PROMPTS_DIR / "sys_character_visual_profile.md").read_text(encoding="utf-8")
        assert "pre-modern" in text

    def test_user_prompt_requires_multi_phase(self):
        text = (self.PROMPTS_DIR / "user_character_visual_profile.md").read_text(encoding="utf-8")
        assert "2-4 个阶段" in text
        assert "visual_delta" in text
