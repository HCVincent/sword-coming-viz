#!/usr/bin/env python3
"""Generate relation_profiles.json via Gemini API.

Reuses the same two-phase (draft + self-critique rewrite) pipeline and
checkpoint/resume/retry infrastructure established for entity profiles.

Environment variables:
  GEMINI_API_KEY            – required
  GEMINI_MODEL              – optional, falls back to DEFAULT_MODEL
  GEMINI_MAX_CONCURRENCY    – optional, default 1
  GEMINI_TIMEOUT_SECONDS    – optional, default 60
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from swordcoming_pipeline.llm_json import LLMJSONParseError, extract_json_from_response

# ── Re-use shared infra from entity profiles script ──────────────────────
from scripts.generate_entity_profiles_via_gemini import (
    CHECKPOINT_FLUSH_INTERVAL,
    CHECKPOINT_TIME_INTERVAL,
    HEARTBEAT_INTERVAL,
    GeminiClient,
    _extract_text_from_response,
    _now_iso,
    _write_json,
    _load_json,
    ensure_api_key,
    load_prompts,
    resolve_max_concurrency,
    resolve_model_name,
    resolve_timeout_seconds,
)

DEFAULT_MODEL = "gemini-3.1-pro-preview"
OUTPUT_VERSION = "relation-profiles-v1"
PROFILE_VERSION = "relation-profile-v1"
GENERATOR_NAME = "gemini-api"
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Relation-specific helpers
# ---------------------------------------------------------------------------

def _relation_key(item: dict) -> str:
    return str(item.get("relation_id", "")).strip()


def iter_input_relations(payload: dict) -> list[dict]:
    return list(payload.get("relations", []))


def index_existing_profiles(payload: dict) -> Dict[str, dict]:
    profiles = payload.get("profiles", [])
    return {str(p.get("relation_id", "")).strip(): p for p in profiles if p.get("relation_id")}


def is_profile_fresh(*, input_item: dict, existing_profile: Optional[dict]) -> bool:
    if not existing_profile:
        return False
    expected = str(input_item.get("input_hash", "")).strip()
    actual = str(existing_profile.get("generated_from_input_hash", "")).strip()
    return bool(expected and expected == actual)


def build_relation_packet(item: dict) -> dict:
    """Build a Gemini-consumable packet from one relation input entry."""
    return {
        "relation_id": item.get("relation_id"),
        "source_name": item.get("source_name"),
        "target_name": item.get("target_name"),
        "primary_action": item.get("primary_action"),
        "action_types": item.get("action_types", []),
        "interaction_count": item.get("interaction_count", 0),
        "progress_start": item.get("progress_start"),
        "progress_end": item.get("progress_end"),
        "source_units": item.get("source_units", []),
        "contexts": item.get("contexts", []),
        "shared_event_refs": item.get("shared_event_refs", []),
        "action_type_counts": item.get("action_type_counts", {}),
        "contexts_by_phase": item.get("contexts_by_phase", {}),
        "input_hash": item.get("input_hash"),
    }


def write_packets(payload: dict, packets_dir: Path) -> Dict[str, dict]:
    packets_dir.mkdir(parents=True, exist_ok=True)
    index: Dict[str, dict] = {}
    for item in iter_input_relations(payload):
        rid = _relation_key(item)
        if not rid:
            continue
        packet = build_relation_packet(item)
        index[rid] = packet
        safe_name = rid.replace("->", "__").replace("/", "_").replace("\\", "_")
        _write_json(packets_dir / f"{safe_name}.json", packet)
    return index


def _coerce_relation_profile(raw: dict, *, packet: dict, model_name: str) -> dict:
    relation_id = str(raw.get("relation_id") or packet.get("relation_id") or "").strip()
    if not relation_id:
        raise ValueError("Model response missing relation_id")

    return {
        "relation_id": relation_id,
        "identity_summary": str(raw.get("identity_summary", "")).strip(),
        "display_summary": str(raw.get("display_summary", "")).strip(),
        "long_description": str(raw.get("long_description", "")).strip(),
        "story_function": str(raw.get("story_function", "")).strip(),
        "phase_arc": str(raw.get("phase_arc", "")).strip(),
        "interaction_patterns": list(raw.get("interaction_patterns", [])),
        "shared_event_ids": list(raw.get("shared_event_ids", []))[:6],
        "evidence_context_indexes": list(raw.get("evidence_context_indexes", []))[:5],
        "generated_from_input_hash": str(packet.get("input_hash", "")).strip(),
        "generator": GENERATOR_NAME,
        "model": model_name,
        "profile_version": PROFILE_VERSION,
        "generated_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Two-phase generation
# ---------------------------------------------------------------------------

def _build_draft_user_prompt(packet: dict) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2)
    return (
        "请基于以下 relation packet 生成一份关系 dossier 初稿。严格输出 JSON，不要输出 markdown 代码围栏。\n\n"
        "输出字段必须包含：relation_id, identity_summary, display_summary, long_description, "
        "story_function, phase_arc, interaction_patterns, shared_event_ids, evidence_context_indexes。\n\n"
        "relation packet:\n"
        f"{packet_json}"
    )


def generate_single_profile(
    *,
    client: GeminiClient,
    packet: dict,
    system_prompt: str,
    rewrite_template: str,
) -> dict:
    draft_prompt = _build_draft_user_prompt(packet)
    draft_raw = client.generate_json(system_prompt=system_prompt, user_prompt=draft_prompt)
    draft_json = json.dumps(draft_raw, ensure_ascii=False, indent=2)
    rewrite_prompt = rewrite_template.replace("{draft_json}", draft_json).replace(
        "{packet_json}", json.dumps(packet, ensure_ascii=False, indent=2)
    )
    final_raw = client.generate_json(system_prompt=system_prompt, user_prompt=rewrite_prompt)
    return _coerce_relation_profile(final_raw, packet=packet, model_name=client.model_name)


def _retry_generate(
    *,
    client: GeminiClient,
    packet: dict,
    system_prompt: str,
    rewrite_template: str,
) -> dict:
    attempt = 0
    while True:
        try:
            return generate_single_profile(
                client=client,
                packet=packet,
                system_prompt=system_prompt,
                rewrite_template=rewrite_template,
            )
        except Exception:
            if attempt >= MAX_RETRIES:
                raise
            attempt += 1
            time.sleep(1.0 * attempt)


# ---------------------------------------------------------------------------
# Merge / checkpoint infrastructure
# ---------------------------------------------------------------------------

def _merge_profiles(
    *,
    inputs_payload: dict,
    existing_profiles: Dict[str, dict],
    newly_generated: Dict[str, dict],
) -> List[dict]:
    ordered: List[dict] = []
    for item in iter_input_relations(inputs_payload):
        rid = _relation_key(item)
        if not rid:
            continue
        profile = newly_generated.get(rid) or existing_profiles.get(rid)
        if profile:
            ordered.append(profile)
    return ordered


def _sync_public_mirror(*, output_path: Path, public_data_dir: Path) -> None:
    public_data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_path, public_data_dir / output_path.name)


def _write_failures(path: Path, failures: List[dict]) -> None:
    _write_json(path, {
        "generated_at": _now_iso(),
        "failure_count": len(failures),
        "failures": failures,
    })


def _load_failures(path: Path) -> List[dict]:
    if not path.exists():
        return []
    payload = _load_json(path)
    return list(payload.get("failures", []))


class CheckpointManager:
    """Thread-safe checkpoint persistence for relation profiles."""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        existing_profiles: Dict[str, dict],
        inputs_payload: dict,
        model_name: str,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._model_name = model_name
        self._inputs_payload = inputs_payload
        self._lock = threading.Lock()
        self._profiles: Dict[str, dict] = dict(existing_profiles)
        self._generated_count = 0
        self._failed_count = 0
        self._unflushed_count = 0
        self._last_flush_time = time.monotonic()

    @property
    def generated_count(self) -> int:
        with self._lock:
            return self._generated_count

    @property
    def failed_count(self) -> int:
        with self._lock:
            return self._failed_count

    def record_success(self, key: str, profile: dict) -> None:
        with self._lock:
            self._profiles[key] = profile
            self._generated_count += 1
            self._unflushed_count += 1
            should_flush = (
                self._unflushed_count >= CHECKPOINT_FLUSH_INTERVAL
                or (time.monotonic() - self._last_flush_time) >= CHECKPOINT_TIME_INTERVAL
            )
        if should_flush:
            self.flush()

    def record_failure(self) -> None:
        with self._lock:
            self._failed_count += 1

    def flush(self) -> None:
        with self._lock:
            if self._unflushed_count == 0:
                return
            snapshot = dict(self._profiles)
            gen = self._generated_count
            fail = self._failed_count
            self._unflushed_count = 0
            self._last_flush_time = time.monotonic()

        ordered = _merge_profiles(
            inputs_payload=self._inputs_payload,
            existing_profiles=snapshot,
            newly_generated={},
        )
        _write_json(self._checkpoint_path, {
            "version": OUTPUT_VERSION,
            "generated_at": _now_iso(),
            "generator": GENERATOR_NAME,
            "model": self._model_name,
            "profile_version": PROFILE_VERSION,
            "generation_status": "partial",
            "generated_count": gen,
            "failed_count": fail,
            "last_checkpoint_at": _now_iso(),
            "profiles": ordered,
        })

    def get_all_profiles(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._profiles)


def _load_checkpoint_profiles(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except Exception:
        return {}
    return index_existing_profiles(payload)


def _best_profile(*, formal: Optional[dict], checkpoint: Optional[dict], input_hash: str) -> Optional[dict]:
    candidates = [s for s in (formal, checkpoint) if s and str(s.get("generated_from_input_hash", "")).strip() == input_hash]
    if not candidates:
        return formal or checkpoint
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda p: str(p.get("generated_at", "")))


def merge_formal_and_checkpoint(
    *,
    inputs_payload: dict,
    formal_profiles: Dict[str, dict],
    checkpoint_profiles: Dict[str, dict],
) -> Dict[str, dict]:
    merged: Dict[str, dict] = {}
    for item in iter_input_relations(inputs_payload):
        rid = _relation_key(item)
        if not rid:
            continue
        ih = str(item.get("input_hash", "")).strip()
        best = _best_profile(
            formal=formal_profiles.get(rid),
            checkpoint=checkpoint_profiles.get(rid),
            input_hash=ih,
        )
        if best:
            merged[rid] = best
    return merged


def _heartbeat_loop(
    *,
    stop_event: threading.Event,
    checkpoint_mgr: CheckpointManager,
    total: int,
    start_time: float,
    running_count: List[int],
) -> None:
    while not stop_event.wait(timeout=HEARTBEAT_INTERVAL):
        elapsed = time.monotonic() - start_time
        gen = checkpoint_mgr.generated_count
        fail = checkpoint_mgr.failed_count
        running = running_count[0]
        print(
            f"  Progress: {gen + fail}/{total} | success={gen} | failed={fail}"
            f" | running={running} | elapsed={elapsed:.0f}s"
        )


# ---------------------------------------------------------------------------
# CLI & main
# ---------------------------------------------------------------------------

def choose_candidates(
    *,
    inputs_payload: dict,
    existing_profiles: Dict[str, dict],
    changed_only: bool,
    relation_id: Optional[str],
    limit: Optional[int],
    force: bool,
) -> List[dict]:
    chosen: List[dict] = []
    for item in iter_input_relations(inputs_payload):
        rid = _relation_key(item)
        if not rid:
            continue
        if relation_id and rid != relation_id:
            continue
        existing = existing_profiles.get(rid)
        if not force and changed_only and is_profile_fresh(input_item=item, existing_profile=existing):
            continue
        chosen.append(item)
    if limit is not None:
        chosen = chosen[:max(0, limit)]
    return chosen


def choose_failure_candidates(*, failures: List[dict], inputs_payload: dict) -> List[dict]:
    fail_ids = {str(f.get("relation_id", "")).strip() for f in failures}
    return [item for item in iter_input_relations(inputs_payload) if _relation_key(item) in fail_ids]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate relation_profiles.json via Gemini API.")
    p.add_argument("--input", default="data/relation_profile_inputs.json")
    p.add_argument("--output", default="data/relation_profiles.json")
    p.add_argument("--checkpoint", default="data/relation_profiles.checkpoint.json")
    p.add_argument("--packets-dir", default="data/_runtime/relation_profile_packets")
    p.add_argument("--failures-output", default="data/relation_profile_generation_failures.json")
    p.add_argument("--sys-prompt", default="prompts/sys_relation_profile_gemini.md")
    p.add_argument("--rewrite-prompt", default="prompts/user_relation_profile_gemini.md")
    p.add_argument("--changed-only", action="store_true", default=True)
    p.add_argument("--all", action="store_true")
    p.add_argument("--relation-id", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--retry-failures", action="store_true")
    p.add_argument("--failures-input", default=None)
    p.add_argument("--public-data-dir", default="visualization/public/data")
    p.add_argument("--no-sync", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint)
    packets_dir = Path(args.packets_dir)
    failures_path = Path(args.failures_output)
    failures_input_path = Path(args.failures_input) if args.failures_input else failures_path
    changed_only = not args.all

    inputs_payload = _load_json(input_path)
    packets = write_packets(inputs_payload, packets_dir)

    formal_payload = _load_json(output_path) if output_path.exists() else {"profiles": []}
    formal_profiles = index_existing_profiles(formal_payload)
    checkpoint_profiles = _load_checkpoint_profiles(checkpoint_path)
    effective = merge_formal_and_checkpoint(
        inputs_payload=inputs_payload,
        formal_profiles=formal_profiles,
        checkpoint_profiles=checkpoint_profiles,
    )

    if args.retry_failures:
        prior = _load_failures(failures_input_path)
        if not prior:
            print(f"No failures found in {failures_input_path}.")
            return 0
        candidates = choose_failure_candidates(failures=prior, inputs_payload=inputs_payload)
        src = "retry-failures"
    else:
        candidates = choose_candidates(
            inputs_payload=inputs_payload,
            existing_profiles=effective,
            changed_only=changed_only,
            relation_id=args.relation_id,
            limit=args.limit,
            force=args.force,
        )
        src = "relation-id" if args.relation_id else ("all" if args.all else "changed-only")

    print(f"Packets written: {len(packets)}")
    print(f"Candidate source: {src}")
    print(f"Candidates selected: {len(candidates)}")

    if args.dry_run:
        for item in candidates:
            print(f"  - {_relation_key(item)}")
        return 0

    if not candidates:
        merged = _merge_profiles(inputs_payload=inputs_payload, existing_profiles=effective, newly_generated={})
        _write_json(output_path, {
            "version": OUTPUT_VERSION, "generated_at": _now_iso(),
            "generator": GENERATOR_NAME, "model": resolve_model_name(),
            "profile_version": PROFILE_VERSION, "profiles": merged,
        })
        if not args.no_sync:
            _sync_public_mirror(output_path=output_path, public_data_dir=Path(args.public_data_dir))
        if checkpoint_path.exists():
            checkpoint_path.unlink(missing_ok=True)
        print("No stale relations. relation_profiles.json refreshed.")
        return 0

    api_key = ensure_api_key()
    model_name = resolve_model_name()
    client = GeminiClient(api_key=api_key, model_name=model_name, timeout_seconds=resolve_timeout_seconds())
    client.preflight()
    system_prompt, rewrite_template = load_prompts(
        sys_prompt_path=Path(args.sys_prompt),
        rewrite_prompt_path=Path(args.rewrite_prompt),
    )

    checkpoint_mgr = CheckpointManager(
        checkpoint_path=checkpoint_path, existing_profiles=effective,
        inputs_payload=inputs_payload, model_name=model_name,
    )
    _emergency_flushed = threading.Event()

    def _emergency_flush(*_a: Any) -> None:
        if _emergency_flushed.is_set():
            return
        _emergency_flushed.set()
        checkpoint_mgr.flush()
        print("\n  Checkpoint flushed on exit.")

    atexit.register(_emergency_flush)
    signal.signal(signal.SIGINT, lambda *a: (_emergency_flush(), sys.exit(130)))

    stop_heartbeat = threading.Event()
    running_counter: List[int] = [0]
    _running_lock = threading.Lock()
    threading.Thread(
        target=_heartbeat_loop, daemon=True,
        kwargs={"stop_event": stop_heartbeat, "checkpoint_mgr": checkpoint_mgr,
                "total": len(candidates), "start_time": time.monotonic(),
                "running_count": running_counter},
    ).start()
    start_time = time.monotonic()

    failures: List[dict] = []

    def _task(item: dict) -> Tuple[str, dict, float]:
        t0 = time.monotonic()
        rid = _relation_key(item)
        packet = packets.get(rid)
        if not packet:
            raise RuntimeError(f"Packet missing for {rid}")
        profile = _retry_generate(
            client=client, packet=packet,
            system_prompt=system_prompt, rewrite_template=rewrite_template,
        )
        return rid, profile, time.monotonic() - t0

    try:
        with ThreadPoolExecutor(max_workers=resolve_max_concurrency()) as pool:
            future_map = {pool.submit(_task, item): item for item in candidates}
            with _running_lock:
                running_counter[0] = len(future_map)
            for future in as_completed(future_map):
                item = future_map[future]
                rid = _relation_key(item)
                try:
                    resolved_rid, profile, duration = future.result()
                    checkpoint_mgr.record_success(resolved_rid, profile)
                    print(f"  ✓ {resolved_rid} ({duration:.1f}s)")
                except Exception as exc:
                    checkpoint_mgr.record_failure()
                    failures.append({"relation_id": rid, "input_hash": str(item.get("input_hash", "")), "error": str(exc)})
                    print(f"  ✗ {rid} -> {exc}")
                finally:
                    with _running_lock:
                        running_counter[0] = max(0, running_counter[0] - 1)
    except KeyboardInterrupt:
        checkpoint_mgr.flush()
        print("\nInterrupted. Checkpoint saved.")
        return 130
    finally:
        stop_heartbeat.set()

    checkpoint_mgr.flush()
    elapsed = time.monotonic() - start_time
    gen = checkpoint_mgr.generated_count
    fail = checkpoint_mgr.failed_count
    print(f"\n{'='*60}\n  Total: {len(candidates)}  Success: {gen}  Failed: {fail}  Elapsed: {elapsed:.0f}s")

    if failures:
        _write_failures(failures_path, failures)
        print(f"  Failure report: {failures_path}\n  Formal output NOT updated.\n{'='*60}")
        return 2

    all_profiles = checkpoint_mgr.get_all_profiles()
    merged = _merge_profiles(inputs_payload=inputs_payload, existing_profiles=all_profiles, newly_generated={})
    _write_json(output_path, {
        "version": OUTPUT_VERSION, "generated_at": _now_iso(),
        "generator": GENERATOR_NAME, "model": model_name,
        "profile_version": PROFILE_VERSION, "profiles": merged,
    })
    if not args.no_sync:
        _sync_public_mirror(output_path=output_path, public_data_dir=Path(args.public_data_dir))
    if checkpoint_path.exists():
        checkpoint_path.unlink(missing_ok=True)
    if failures_path.exists():
        failures_path.unlink(missing_ok=True)
    print(f"  Output: {output_path}\n  Generated: {gen}\n{'='*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
