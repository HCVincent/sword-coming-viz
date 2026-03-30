import types

import pytest

from scripts import build_swordcoming_offline_data
from scripts.generate_entity_profiles_via_gemini import (
    choose_candidates,
    ensure_api_key,
    index_existing_profiles,
    resolve_model_name,
)
from scripts.validate_entity_profiles import validate_entity_profiles


def _sample_inputs_payload() -> dict:
    return {
        "roles": [
            {
                "entity_type": "role",
                "entity_id": "陈平安",
                "input_hash": "hash-role-1",
                "original_descriptions": ["陈平安站在泥瓶巷。"],
                "turning_point_candidates": [{"name": "墙头对话"}],
            }
        ],
        "locations": [
            {
                "entity_type": "location",
                "entity_id": "泥瓶巷",
                "input_hash": "hash-loc-1",
                "original_descriptions": ["泥瓶巷院墙低矮。"],
                "turning_point_candidates": [{"name": "老槐树相遇"}],
            }
        ],
    }


def test_resolve_model_name_defaults_to_preview(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert resolve_model_name() == "gemini-3.1-pro-preview"


def test_resolve_model_name_can_be_overridden(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    assert resolve_model_name() == "gemini-2.5-pro"


def test_ensure_api_key_missing_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing GEMINI_API_KEY"):
        ensure_api_key()


def test_changed_only_skips_unchanged_entities():
    inputs_payload = _sample_inputs_payload()
    existing = index_existing_profiles(
        {
            "profiles": [
                {
                    "entity_type": "role",
                    "entity_id": "陈平安",
                    "generated_from_input_hash": "hash-role-1",
                },
                {
                    "entity_type": "location",
                    "entity_id": "泥瓶巷",
                    "generated_from_input_hash": "old-hash",
                },
            ]
        }
    )

    candidates = choose_candidates(
        inputs_payload=inputs_payload,
        existing_profiles=existing,
        changed_only=True,
        entity_id=None,
        entity_type=None,
        limit=None,
        force=False,
    )

    ids = {(item["entity_type"], item["entity_id"]) for item in candidates}
    assert ids == {("location", "泥瓶巷")}


def test_validate_entity_profiles_flags_excerpt_copy_and_template_marker():
    inputs_payload = _sample_inputs_payload()
    profiles_payload = {
        "profiles": [
            {
                "entity_type": "role",
                "entity_id": "陈平安",
                "identity_summary": "陈平安是关键角色。",
                "display_summary": "陈平安站在泥瓶巷。后续有成长。",
                "long_description": "陈平安站在泥瓶巷。人物关系上，他逐步改变。",
                "generator": "gemini-api",
                "model": "gemini-3.1-pro-preview",
                "generated_from_input_hash": "hash-role-1",
            },
            {
                "entity_type": "location",
                "entity_id": "泥瓶巷",
                "identity_summary": "泥瓶巷是地点。",
                "display_summary": "泥瓶巷承接叙事。",
                "long_description": "这里是地点评述。",
                "generator": "gemini-api",
                "model": "gemini-3.1-pro-preview",
                "generated_from_input_hash": "hash-loc-1",
            },
        ]
    }

    problems = validate_entity_profiles(inputs_payload=inputs_payload, profiles_payload=profiles_payload)
    assert any("long_description starts with original_descriptions[0]" in item for item in problems)
    assert any("hit legacy template marker" in item for item in problems)


def test_apply_display_summaries_warn_mode_does_not_raise_on_stale():
    kb = types.SimpleNamespace(
        roles={
            "陈平安": types.SimpleNamespace(
                display_summary="",
                identity_summary="",
                long_description="",
                summary_source="",
                summary_version="",
                profile_version="",
                description="",
            )
        },
        locations={},
    )

    summary_inputs = {
        "roles": [{"entity_id": "陈平安", "input_hash": "h1"}],
        "locations": [],
    }
    summary_outputs = {
        "profiles": [
            {
                "entity_type": "role",
                "entity_id": "陈平安",
                "display_summary": "简介",
                "identity_summary": "身份",
                "long_description": "长文",
                "generated_from_input_hash": "old",
                "generator": "gemini-api",
                "profile_version": "role-location-profile-v1",
            }
        ],
        "version": "entity-profiles-v1",
        "profile_version": "role-location-profile-v1",
    }

    coverage = build_swordcoming_offline_data._apply_display_summaries_to_kb(
        kb=kb,
        summary_inputs=summary_inputs,
        summary_outputs=summary_outputs,
        skip_summary_check=False,
        require_fresh_entity_profiles=False,
    )
    assert coverage["stale"] == 1


def test_apply_display_summaries_strict_mode_raises_on_stale():
    kb = types.SimpleNamespace(
        roles={
            "陈平安": types.SimpleNamespace(
                display_summary="",
                identity_summary="",
                long_description="",
                summary_source="",
                summary_version="",
                profile_version="",
                description="",
            )
        },
        locations={},
    )

    summary_inputs = {
        "roles": [{"entity_id": "陈平安", "input_hash": "h1"}],
        "locations": [],
    }
    summary_outputs = {
        "profiles": [
            {
                "entity_type": "role",
                "entity_id": "陈平安",
                "display_summary": "简介",
                "identity_summary": "身份",
                "long_description": "长文",
                "generated_from_input_hash": "old",
                "generator": "gemini-api",
                "profile_version": "role-location-profile-v1",
            }
        ],
        "version": "entity-profiles-v1",
        "profile_version": "role-location-profile-v1",
    }

    with pytest.raises(ValueError, match="missing or stale"):
        build_swordcoming_offline_data._apply_display_summaries_to_kb(
            kb=kb,
            summary_inputs=summary_inputs,
            summary_outputs=summary_outputs,
            skip_summary_check=False,
            require_fresh_entity_profiles=True,
        )
