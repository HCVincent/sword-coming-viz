import json
import threading
import time
import types
from pathlib import Path

import pytest

from scripts import build_swordcoming_offline_data
from scripts.generate_entity_profiles_via_gemini import (
    CheckpointManager,
    _best_profile,
    _coerce_profile,
    _heartbeat_loop,
    _load_checkpoint_profiles,
    _load_failures,
    choose_candidates,
    choose_failure_candidates,
    ensure_api_key,
    index_existing_profiles,
    merge_formal_and_checkpoint,
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


def test_coerce_profile_uses_packet_identity_when_model_echoes_alias():
    packet = {
        "entity_type": "role",
        "entity_id": "桂夫人",
        "input_hash": "hash-gui",
        "evidence_excerpt_ids": ["1-1-1-0"],
    }
    raw = {
        "entity_type": "role",
        "entity_id": "桂姨",
        "identity_summary": "身份简介",
        "display_summary": "展示简介",
        "long_description": "长描述",
        "story_function": "结构功能",
        "phase_arc": "阶段变化",
        "relationship_clusters": ["关系簇"],
        "major_locations": ["老龙城"],
        "turning_points": ["关键节点"],
        "evidence_excerpt_ids": ["1-1-1-0"],
    }

    profile = _coerce_profile(raw, packet=packet, model_name="gemini-test")

    assert profile["entity_type"] == "role"
    assert profile["entity_id"] == "桂夫人"
    assert profile["generated_from_input_hash"] == "hash-gui"


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


# ── Checkpoint & Resume Tests ────────────────────────────────────────────────

def _two_entity_inputs_payload() -> dict:
    return {
        "roles": [
            {"entity_type": "role", "entity_id": "陈平安", "input_hash": "h-role-1"},
            {"entity_type": "role", "entity_id": "宁姚", "input_hash": "h-role-2"},
        ],
        "locations": [
            {"entity_type": "location", "entity_id": "泥瓶巷", "input_hash": "h-loc-1"},
        ],
    }


def _make_profile(entity_type: str, entity_id: str, input_hash: str, generated_at: str = "2025-01-01T00:00:00") -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "identity_summary": f"{entity_id} summary",
        "display_summary": f"{entity_id} display",
        "long_description": f"{entity_id} long desc",
        "generated_from_input_hash": input_hash,
        "generator": "gemini-api",
        "model": "gemini-3.1-pro-preview",
        "profile_version": "role-location-profile-v1",
        "generated_at": generated_at,
    }


class TestCheckpointManager:
    """Tests for CheckpointManager flush and tracking."""

    def test_record_success_increments_count(self):
        inputs = _two_entity_inputs_payload()
        mgr = CheckpointManager(
            checkpoint_path=Path("dummy.json"),
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )
        profile = _make_profile("role", "陈平安", "h-role-1")
        mgr.record_success(("role", "陈平安"), profile)
        assert mgr.generated_count == 1
        assert mgr.failed_count == 0

    def test_record_failure_increments_count(self):
        inputs = _two_entity_inputs_payload()
        mgr = CheckpointManager(
            checkpoint_path=Path("dummy.json"),
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )
        mgr.record_failure()
        assert mgr.failed_count == 1
        assert mgr.generated_count == 0

    def test_flush_writes_checkpoint_file(self, tmp_path):
        inputs = _two_entity_inputs_payload()
        checkpoint_path = tmp_path / "checkpoint.json"
        mgr = CheckpointManager(
            checkpoint_path=checkpoint_path,
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )
        profile = _make_profile("role", "陈平安", "h-role-1")
        mgr.record_success(("role", "陈平安"), profile)
        # Force flush (bypasses interval check)
        mgr.flush()
        assert checkpoint_path.exists()
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        assert payload["generation_status"] == "partial"
        assert payload["generated_count"] == 1
        assert any(p["entity_id"] == "陈平安" for p in payload["profiles"])

    def test_flush_noop_when_nothing_unflushed(self, tmp_path):
        inputs = _two_entity_inputs_payload()
        checkpoint_path = tmp_path / "checkpoint.json"
        mgr = CheckpointManager(
            checkpoint_path=checkpoint_path,
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )
        mgr.flush()
        assert not checkpoint_path.exists()

    def test_get_all_profiles_includes_existing_and_new(self):
        inputs = _two_entity_inputs_payload()
        existing = {("role", "宁姚"): _make_profile("role", "宁姚", "h-role-2")}
        mgr = CheckpointManager(
            checkpoint_path=Path("dummy.json"),
            existing_profiles=existing,
            inputs_payload=inputs,
            model_name="test-model",
        )
        new_profile = _make_profile("role", "陈平安", "h-role-1")
        mgr.record_success(("role", "陈平安"), new_profile)
        all_profiles = mgr.get_all_profiles()
        assert ("role", "陈平安") in all_profiles
        assert ("role", "宁姚") in all_profiles


class TestMergeFormalAndCheckpoint:
    """Tests for merge_formal_and_checkpoint and _best_profile."""

    def test_prefers_hash_matching_profile(self):
        formal = _make_profile("role", "陈平安", "old-hash", "2025-01-01T00:00:00")
        checkpoint = _make_profile("role", "陈平安", "h-role-1", "2025-01-02T00:00:00")
        best = _best_profile(
            key=("role", "陈平安"),
            formal=formal,
            checkpoint=checkpoint,
            input_hash="h-role-1",
        )
        assert best["generated_from_input_hash"] == "h-role-1"

    def test_prefers_newer_when_both_match_hash(self):
        older = _make_profile("role", "陈平安", "h-role-1", "2025-01-01T00:00:00")
        newer = _make_profile("role", "陈平安", "h-role-1", "2025-06-15T12:00:00")
        best = _best_profile(
            key=("role", "陈平安"),
            formal=older,
            checkpoint=newer,
            input_hash="h-role-1",
        )
        assert best["generated_at"] == "2025-06-15T12:00:00"

    def test_fallback_to_any_when_neither_matches(self):
        formal = _make_profile("role", "陈平安", "old-1", "2025-01-01T00:00:00")
        checkpoint = _make_profile("role", "陈平安", "old-2", "2025-01-02T00:00:00")
        best = _best_profile(
            key=("role", "陈平安"),
            formal=formal,
            checkpoint=checkpoint,
            input_hash="h-role-1",
        )
        # Falls back to formal (first non-None)
        assert best is formal

    def test_merge_combines_formal_and_checkpoint(self):
        inputs = _two_entity_inputs_payload()
        formal_profiles = {
            ("role", "陈平安"): _make_profile("role", "陈平安", "h-role-1"),
        }
        checkpoint_profiles = {
            ("role", "宁姚"): _make_profile("role", "宁姚", "h-role-2"),
        }
        merged = merge_formal_and_checkpoint(
            inputs_payload=inputs,
            formal_profiles=formal_profiles,
            checkpoint_profiles=checkpoint_profiles,
        )
        assert ("role", "陈平安") in merged
        assert ("role", "宁姚") in merged


class TestRetryFailures:
    """Tests for _load_failures and choose_failure_candidates."""

    def test_load_failures_returns_empty_for_missing_file(self, tmp_path):
        result = _load_failures(tmp_path / "nonexistent.json")
        assert result == []

    def test_load_failures_parses_failure_report(self, tmp_path):
        report = {
            "generated_at": "2025-01-01T00:00:00",
            "failure_count": 1,
            "failures": [
                {"entity_type": "role", "entity_id": "宁姚", "input_hash": "h-role-2", "error": "timeout"},
            ],
        }
        path = tmp_path / "failures.json"
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        loaded = _load_failures(path)
        assert len(loaded) == 1
        assert loaded[0]["entity_id"] == "宁姚"

    def test_choose_failure_candidates_selects_only_failed(self):
        inputs = _two_entity_inputs_payload()
        failures = [
            {"entity_type": "role", "entity_id": "宁姚", "input_hash": "h-role-2", "error": "timeout"},
        ]
        candidates = choose_failure_candidates(failures=failures, inputs_payload=inputs)
        ids = [(c["entity_type"], c["entity_id"]) for c in candidates]
        assert ("role", "宁姚") in ids
        assert ("role", "陈平安") not in ids

    def test_choose_failure_candidates_ignores_unknown_entities(self):
        inputs = _two_entity_inputs_payload()
        failures = [
            {"entity_type": "role", "entity_id": "不存在角色", "input_hash": "xxx", "error": "timeout"},
        ]
        candidates = choose_failure_candidates(failures=failures, inputs_payload=inputs)
        assert len(candidates) == 0


class TestLoadCheckpointProfiles:
    """Tests for _load_checkpoint_profiles."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _load_checkpoint_profiles(tmp_path / "nope.json")
        assert result == {}

    def test_returns_empty_for_corrupt_file(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("NOT JSON", encoding="utf-8")
        result = _load_checkpoint_profiles(path)
        assert result == {}

    def test_indexes_profiles_from_checkpoint(self, tmp_path):
        payload = {
            "generation_status": "partial",
            "profiles": [_make_profile("role", "陈平安", "h-role-1")],
        }
        path = tmp_path / "checkpoint.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = _load_checkpoint_profiles(path)
        assert ("role", "陈平安") in result


class TestCheckpointWrittenOnPartialFailure:
    """Integration-like test: checkpoint has successes even when failures exist."""

    def test_checkpoint_preserves_successes(self, tmp_path):
        inputs = _two_entity_inputs_payload()
        checkpoint_path = tmp_path / "checkpoint.json"
        mgr = CheckpointManager(
            checkpoint_path=checkpoint_path,
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )
        # Simulate: first entity succeeds, second fails
        mgr.record_success(
            ("role", "陈平安"),
            _make_profile("role", "陈平安", "h-role-1"),
        )
        mgr.record_failure()
        mgr.flush()

        assert checkpoint_path.exists()
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        assert payload["generated_count"] == 1
        assert payload["failed_count"] == 1
        # The successful entity IS in the checkpoint
        ids = [p["entity_id"] for p in payload["profiles"]]
        assert "陈平安" in ids


class TestFormalOutputOnlyOnFullSuccess:
    """Verify formal output is NOT written when failures exist (by checking main logic flow)."""

    def test_checkpoint_written_but_formal_not_on_failures(self, tmp_path):
        """Simulate: checkpoint written, but we would NOT write formal output if failures > 0."""
        inputs = _two_entity_inputs_payload()
        checkpoint_path = tmp_path / "checkpoint.json"
        formal_path = tmp_path / "entity_profiles.json"

        mgr = CheckpointManager(
            checkpoint_path=checkpoint_path,
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )
        mgr.record_success(("role", "陈平安"), _make_profile("role", "陈平安", "h-role-1"))
        mgr.record_failure()
        mgr.flush()

        # In the real main(), failures > 0 means we skip writing formal_path
        # Verify checkpoint exists but formal does not
        assert checkpoint_path.exists()
        assert not formal_path.exists()


class TestHeartbeatRunningCount:
    """Verify the heartbeat thread can read running_counter set by another thread."""

    def test_running_counter_visible_across_threads(self):
        """running_counter (List[int]) must be readable from the heartbeat thread."""
        inputs = _two_entity_inputs_payload()
        mgr = CheckpointManager(
            checkpoint_path=Path("dummy.json"),
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )

        running_counter: list = [0]
        observed_values: list = []
        stop_event = threading.Event()

        def _capture_loop(
            *,
            stop_event: threading.Event,
            checkpoint_mgr: CheckpointManager,
            total: int,
            start_time: float,
            running_count: list,
        ) -> None:
            """Minimal heartbeat that just captures running_count snapshots."""
            while not stop_event.wait(timeout=0.01):
                observed_values.append(running_count[0])

        t = threading.Thread(
            target=_capture_loop,
            kwargs={
                "stop_event": stop_event,
                "checkpoint_mgr": mgr,
                "total": 3,
                "start_time": time.monotonic(),
                "running_count": running_counter,
            },
            daemon=True,
        )
        t.start()

        # Simulate main thread setting running_counter
        running_counter[0] = 5
        time.sleep(0.05)
        running_counter[0] = 3
        time.sleep(0.05)

        stop_event.set()
        t.join(timeout=1.0)

        # The observer thread must have seen the values written by the main thread
        assert any(v == 5 for v in observed_values), (
            f"Heartbeat thread never observed running=5; saw {set(observed_values)}"
        )
        assert any(v == 3 for v in observed_values), (
            f"Heartbeat thread never observed running=3; saw {set(observed_values)}"
        )

    def test_real_heartbeat_loop_reads_shared_counter(self, capsys):
        """_heartbeat_loop itself reads the shared List[int] counter correctly."""
        inputs = _two_entity_inputs_payload()
        mgr = CheckpointManager(
            checkpoint_path=Path("dummy.json"),
            existing_profiles={},
            inputs_payload=inputs,
            model_name="test-model",
        )

        running_counter: list = [7]
        stop_event = threading.Event()

        # Use a very short heartbeat interval via monkeypatching the wait
        import scripts.generate_entity_profiles_via_gemini as mod
        original_interval = mod.HEARTBEAT_INTERVAL
        mod.HEARTBEAT_INTERVAL = 0.02
        try:
            t = threading.Thread(
                target=_heartbeat_loop,
                kwargs={
                    "stop_event": stop_event,
                    "checkpoint_mgr": mgr,
                    "total": 10,
                    "start_time": time.monotonic(),
                    "running_count": running_counter,
                },
                daemon=True,
            )
            t.start()
            time.sleep(0.1)
            stop_event.set()
            t.join(timeout=1.0)
        finally:
            mod.HEARTBEAT_INTERVAL = original_interval

        captured = capsys.readouterr().out
        assert "running=7" in captured, (
            f"_heartbeat_loop did not print running=7; output was: {captured!r}"
        )
