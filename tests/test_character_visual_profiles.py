"""Tests for CharacterVisualProfile model and high_value_role_roster."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from model.visual_profile import (
    AppearanceDetails,
    AppearanceTimelineEntry,
    CharacterVisualProfile,
    CharacterVisualProfilesPayload,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# ── Model validation tests ────────────────────────────────────────────────

class TestCharacterVisualProfile:
    """Test Pydantic model construction and validation."""

    def test_minimal_profile(self):
        profile = CharacterVisualProfile(
            role_id="test",
            canonical_name="测试角色",
            card_title="测试",
            visual_hook="一句话视觉钩子",
            initial_appearance="初始形象描述。",
            appearance_details=AppearanceDetails(
                age_and_build="少年，瘦削",
                facial_features="普通面容",
                hair="短发黑色",
                clothing_and_materials="粗布短衫",
                color_palette="灰褐色调",
                aura_and_camera_feel="沉稳内敛",
            ),
            image_prompt_base="A young man in simple clothes.",
        )
        assert profile.role_id == "test"
        assert profile.negative_constraints == []
        assert profile.appearance_timeline == []

    def test_profile_with_timeline(self):
        profile = CharacterVisualProfile(
            role_id="陈平安",
            canonical_name="陈平安",
            card_title="陈平安",
            visual_hook="泥瓶巷走出的少年剑客",
            initial_appearance="小镇少年，瘦削矮小。",
            appearance_details=AppearanceDetails(
                age_and_build="少年",
                facial_features="朴素",
                hair="黑色短发",
                clothing_and_materials="粗布",
                color_palette="灰土色",
                aura_and_camera_feel="沉默坚韧",
            ),
            negative_constraints=["不要仙侠飘带", "不要成年人体态"],
            image_prompt_base="A young boy in coarse cloth.",
            appearance_timeline=[
                AppearanceTimelineEntry(
                    phase_label="泥瓶巷少年",
                    range_hint="第一卷",
                    change_summary="初始形象",
                    visual_delta="无变化",
                    use_as_default_card=True,
                ),
            ],
        )
        assert len(profile.appearance_timeline) == 1
        assert profile.appearance_timeline[0].use_as_default_card is True

    def test_payload_container(self):
        payload = CharacterVisualProfilesPayload(
            generated_at="2025-01-01T00:00:00",
            model="gemini-test",
            profiles=[],
        )
        assert payload.version == "character-visual-profiles-v1"
        assert payload.profiles == []


# ── Artifact validation tests ─────────────────────────────────────────────

class TestHighValueRoleRoster:
    """Validate data/high_value_role_roster.json artifact."""

    @pytest.fixture(scope="class")
    def roster(self):
        path = DATA_DIR / "high_value_role_roster.json"
        if not path.exists():
            pytest.skip("high_value_role_roster.json not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_roster_size(self, roster):
        assert roster["roster_size"] == 24
        assert len(roster["roles"]) == 24

    def test_roster_fields(self, roster):
        for entry in roster["roles"]:
            assert "role_id" in entry
            assert "canonical_name" in entry
            assert "rank" in entry
            assert isinstance(entry["selection_score"], (int, float))
            assert entry["selection_score"] > 0

    def test_roster_ranks_unique(self, roster):
        ranks = [r["rank"] for r in roster["roles"]]
        assert ranks == sorted(set(ranks))

    def test_陈平安_is_rank_1(self, roster):
        assert roster["roles"][0]["role_id"] == "陈平安"
        assert roster["roles"][0]["rank"] == 1


class TestCharacterVisualProfilesArtifact:
    """Validate data/character_visual_profiles.json artifact."""

    @pytest.fixture(scope="class")
    def profiles_data(self):
        path = DATA_DIR / "character_visual_profiles.json"
        if not path.exists():
            pytest.skip("character_visual_profiles.json not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_profile_count(self, profiles_data):
        profiles = profiles_data.get("profiles", [])
        assert len(profiles) >= 23, f"Expected at least 23 profiles, got {len(profiles)}"

    def test_all_profiles_validate(self, profiles_data):
        for raw in profiles_data["profiles"]:
            profile = CharacterVisualProfile.model_validate(raw)
            assert profile.role_id
            assert profile.canonical_name
            assert profile.visual_hook
            assert len(profile.visual_hook) <= 30, f"{profile.role_id} hook too long: {profile.visual_hook}"
            assert profile.initial_appearance
            assert profile.image_prompt_base
            assert len(profile.negative_constraints) >= 1, f"{profile.role_id} needs negative_constraints"

    def test_appearance_details_complete(self, profiles_data):
        for raw in profiles_data["profiles"]:
            profile = CharacterVisualProfile.model_validate(raw)
            ad = profile.appearance_details
            assert ad.age_and_build, f"{profile.role_id}: missing age_and_build"
            assert ad.facial_features, f"{profile.role_id}: missing facial_features"
            assert ad.hair, f"{profile.role_id}: missing hair"
            assert ad.clothing_and_materials, f"{profile.role_id}: missing clothing_and_materials"
            assert ad.color_palette, f"{profile.role_id}: missing color_palette"
            assert ad.aura_and_camera_feel, f"{profile.role_id}: missing aura_and_camera_feel"

    def test_appearance_timeline_has_default(self, profiles_data):
        for raw in profiles_data["profiles"]:
            profile = CharacterVisualProfile.model_validate(raw)
            if profile.appearance_timeline:
                default_phases = [e for e in profile.appearance_timeline if e.use_as_default_card]
                assert len(default_phases) >= 1, f"{profile.role_id}: no default card phase"

    def test_image_prompt_is_english(self, profiles_data):
        """image_prompt_base should be predominantly English."""
        for raw in profiles_data["profiles"]:
            profile = CharacterVisualProfile.model_validate(raw)
            prompt = profile.image_prompt_base
            # Simple heuristic: more than 50% ASCII chars
            ascii_ratio = sum(1 for c in prompt if ord(c) < 128) / max(len(prompt), 1)
            assert ascii_ratio > 0.5, f"{profile.role_id}: image_prompt_base seems non-English"

    def test_core_characters_present(self, profiles_data):
        """Key characters must be in the visual profiles."""
        role_ids = {p["role_id"] for p in profiles_data["profiles"]}
        for name in ["陈平安", "宁姚", "宋集薪", "齐静春", "杨老头"]:
            assert name in role_ids, f"{name} missing from visual profiles"
