#!/usr/bin/env python3
"""Generate narrative_units.json via Gemini API.

Two-phase (draft + self-critique rewrite) pipeline for narrative unit dossiers.
Reuses GeminiClient / infrastructure from entity profiles / event dossier scripts.

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
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from swordcoming_pipeline.llm_json import LLMJSONParseError, extract_json_from_response

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
OUTPUT_VERSION = "narrative-units-v1"
DOSSIER_VERSION = "narrative-unit-dossier-v1"
GENERATOR_NAME = "gemini-api"
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Unit-specific helpers
# ---------------------------------------------------------------------------

def _unit_key(item: dict) -> str:
    return str(item.get("unit_id", "")).strip()


def iter_input_units(payload: dict) -> list:
    return list(payload.get("units", []))


def index_existing_dossiers(payload: dict) -> Dict[str, dict]:
    units = payload.get("units", [])
    return {str(d.get("unit_id", "")).strip(): d for d in units if d.get("unit_id")}


def is_dossier_fresh(*, input_item: dict, existing_dossier: Optional[dict]) -> bool:
    if not existing_dossier:
        return False
    expected = str(input_item.get("input_hash", "")).strip()
    actual = str(existing_dossier.get("generated_from_input_hash", "")).strip()
    return bool(expected and expected == actual)


def build_unit_packet(item: dict) -> dict:
    """Build a Gemini-consumable packet from one narrative unit input entry."""
    return {
        "unit_id": item.get("unit_id"),
        "unit_index": item.get("unit_index"),
        "season_name": item.get("season_name", ""),
        "start_unit_index": item.get("start_unit_index"),
        "end_unit_index": item.get("end_unit_index"),
        "source_unit_indexes": item.get("source_unit_indexes", []),
        "chapter_titles": item.get("chapter_titles", []),
        "main_roles": item.get("main_roles", []),
        "main_locations": item.get("main_locations", []),
        "progress_start": item.get("progress_start"),
        "progress_end": item.get("progress_end"),
        "source_event_ids": item.get("source_event_ids", []),
        "chapter_synopses": item.get("chapter_synopses", []),
        "key_events": item.get("key_events", []),
        "event_dossier_summaries": item.get("event_dossier_summaries", []),
        "writer_refs": item.get("writer_refs", []),
        "input_hash": item.get("input_hash"),
    }


def _coerce_unit_dossier(raw: dict, *, packet: dict, model_name: str) -> dict:
    unit_id = str(raw.get("unit_id") or packet.get("unit_id") or "").strip()
    if not unit_id:
        raise ValueError("Model response missing unit_id")

    return {
        "unit_id": unit_id,
        "title": str(raw.get("title", "")).strip(),
        "display_summary": str(raw.get("display_summary", "")).strip(),
        "long_summary": str(raw.get("long_summary", "")).strip(),
        "dramatic_function": str(raw.get("dramatic_function", "")).strip(),
        "what_changes": str(raw.get("what_changes", "")).strip(),
        "stakes": str(raw.get("stakes", "")).strip(),
        # Passthrough structural fields from input
        "unit_index": packet.get("unit_index"),
        "season_name": packet.get("season_name", ""),
        "start_unit_index": packet.get("start_unit_index"),
        "end_unit_index": packet.get("end_unit_index"),
        "source_unit_indexes": packet.get("source_unit_indexes", []),
        "progress_start": packet.get("progress_start"),
        "progress_end": packet.get("progress_end"),
        "source_event_ids": packet.get("source_event_ids", []),
        "main_roles": packet.get("main_roles", []),
        "main_locations": packet.get("main_locations", []),
        "generated_from_input_hash": str(packet.get("input_hash", "")).strip(),
        "generator": GENERATOR_NAME,
        "model": model_name,
        "dossier_version": DOSSIER_VERSION,
        "generated_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Two-phase generation
# ---------------------------------------------------------------------------

def _build_draft_user_prompt(packet: dict) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2)
    return (
        "Generate a first-draft dossier for the following narrative unit packet. "
        "Return valid JSON only, with no markdown fence. "
        "The JSON must contain unit_id, title, display_summary, long_summary, "
        "dramatic_function, what_changes, and stakes. "
        "Write all prose fields in Simplified Chinese.\n\n"
        "Narrative unit packet:\n"
        f"{packet_json}"
    )


def generate_single_dossier(
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
    return _coerce_unit_dossier(final_raw, packet=packet, model_name=client.model_name)


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
            return generate_single_dossier(
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

def _merge_units(
    *,
    inputs_payload: dict,
    existing_dossiers: Dict[str, dict],
    newly_generated: Dict[str, dict],
) -> List[dict]:
    ordered: List[dict] = []
    for item in iter_input_units(inputs_payload):
        uid = _unit_key(item)
        if not uid:
            continue
        dossier = newly_generated.get(uid) or existing_dossiers.get(uid)
        if dossier:
            # Backfill structural passthrough fields from authoritative inputs so
            # existing fresh dossiers can be rewritten without another API call.
            enriched = dict(dossier)
            enriched.setdefault("unit_index", item.get("unit_index"))
            enriched.setdefault("season_name", item.get("season_name", ""))
            enriched.setdefault("start_unit_index", item.get("start_unit_index"))
            enriched.setdefault("end_unit_index", item.get("end_unit_index"))
            enriched.setdefault("source_unit_indexes", item.get("source_unit_indexes", []))
            enriched.setdefault("progress_start", item.get("progress_start"))
            enriched.setdefault("progress_end", item.get("progress_end"))
            enriched.setdefault("source_event_ids", item.get("source_event_ids", []))
            enriched.setdefault("main_roles", item.get("main_roles", []))
            enriched.setdefault("main_locations", item.get("main_locations", []))
            ordered.append(enriched)
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
    """Thread-safe checkpoint persistence for narrative unit dossiers."""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        existing_dossiers: Dict[str, dict],
        inputs_payload: dict,
        model_name: str,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._model_name = model_name
        self._inputs_payload = inputs_payload
        self._lock = threading.Lock()
        self._dossiers: Dict[str, dict] = dict(existing_dossiers)
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

    def record_success(self, key: str, dossier: dict) -> None:
        with self._lock:
            self._dossiers[key] = dossier
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
            snapshot = dict(self._dossiers)
            gen = self._generated_count
            fail = self._failed_count
            self._unflushed_count = 0
            self._last_flush_time = time.monotonic()

        ordered = _merge_units(
            inputs_payload=self._inputs_payload,
            existing_dossiers=snapshot,
            newly_generated={},
        )
        _write_json(self._checkpoint_path, {
            "version": OUTPUT_VERSION,
            "generated_at": _now_iso(),
            "generator": GENERATOR_NAME,
            "model": self._model_name,
            "dossier_version": DOSSIER_VERSION,
            "generation_status": "partial",
            "generated_count": gen,
            "failed_count": fail,
            "units": ordered,
        })

    def get_all_dossiers(self) -> Dict[str, dict]:
        with self._lock:
            return dict(self._dossiers)


def _load_checkpoint_dossiers(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except Exception:
        return {}
    return index_existing_dossiers(payload)


def _best_dossier(*, formal: Optional[dict], checkpoint: Optional[dict], input_hash: str) -> Optional[dict]:
    candidates = [s for s in (formal, checkpoint) if s and str(s.get("generated_from_input_hash", "")).strip() == input_hash]
    if not candidates:
        return formal or checkpoint
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda p: str(p.get("generated_at", "")))


def merge_formal_and_checkpoint(
    *,
    inputs_payload: dict,
    formal_dossiers: Dict[str, dict],
    checkpoint_dossiers: Dict[str, dict],
) -> Dict[str, dict]:
    merged: Dict[str, dict] = {}
    for item in iter_input_units(inputs_payload):
        uid = _unit_key(item)
        if not uid:
            continue
        ih = str(item.get("input_hash", "")).strip()
        best = _best_dossier(
            formal=formal_dossiers.get(uid),
            checkpoint=checkpoint_dossiers.get(uid),
            input_hash=ih,
        )
        if best:
            merged[uid] = best
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
    existing_dossiers: Dict[str, dict],
    changed_only: bool,
    unit_id: Optional[str],
    limit: Optional[int],
    force: bool,
) -> List[dict]:
    chosen: List[dict] = []
    for item in iter_input_units(inputs_payload):
        uid = _unit_key(item)
        if not uid:
            continue
        if unit_id and uid != unit_id:
            continue
        existing = existing_dossiers.get(uid)
        if not force and changed_only and is_dossier_fresh(input_item=item, existing_dossier=existing):
            continue
        chosen.append(item)
    if limit is not None:
        chosen = chosen[:max(0, limit)]
    return chosen


def choose_failure_candidates(*, failures: List[dict], inputs_payload: dict) -> List[dict]:
    fail_ids = {str(f.get("unit_id", "")).strip() for f in failures}
    return [item for item in iter_input_units(inputs_payload) if _unit_key(item) in fail_ids]


def _load_audit_unit_ids(
    *,
    audit_path: Path,
    severities: Set[str],
    max_count: Optional[int] = None,
) -> List[str]:
    payload = _load_json(audit_path)
    findings = payload.get("findings", []) or []
    unit_ids: List[str] = []
    seen: Set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity", "")).strip().lower()
        if severities and severity not in severities:
            continue
        unit_id = str(finding.get("unit_id", "")).strip()
        if not unit_id or unit_id in seen:
            continue
        seen.add(unit_id)
        unit_ids.append(unit_id)
        if max_count is not None and len(unit_ids) >= max_count:
            break
    return unit_ids


def choose_audit_candidates(
    *,
    inputs_payload: dict,
    audit_path: Path,
    severities: Set[str],
    max_count: Optional[int] = None,
) -> List[dict]:
    audit_ids = set(
        _load_audit_unit_ids(
            audit_path=audit_path,
            severities=severities,
            max_count=max_count,
        )
    )
    return [item for item in iter_input_units(inputs_payload) if _unit_key(item) in audit_ids]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate narrative_units.json via Gemini API.")
    p.add_argument("--input", default="data/narrative_unit_dossier_inputs.json")
    p.add_argument("--output", default="data/narrative_units.json")
    p.add_argument("--checkpoint", default="data/narrative_units.checkpoint.json")
    p.add_argument("--failures-output", default="data/narrative_unit_generation_failures.json")
    p.add_argument("--sys-prompt", default="prompts/sys_narrative_unit_dossier_gemini.md")
    p.add_argument("--rewrite-prompt", default="prompts/user_narrative_unit_dossier_gemini.md")
    p.add_argument("--changed-only", action="store_true", default=True)
    p.add_argument("--all", action="store_true")
    p.add_argument("--unit-id", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--retry-failures", action="store_true")
    p.add_argument("--failures-input", default=None)
    p.add_argument("--audit-file", default=None, help="Narrative unit quality audit JSON for targeted reruns")
    p.add_argument(
        "--audit-severities",
        default="high,medium",
        help="Comma-separated severities to rerun from --audit-file (default: high,medium)",
    )
    p.add_argument("--audit-limit", type=int, default=None, help="Optional cap when selecting from --audit-file")
    p.add_argument("--public-data-dir", default="visualization/public/data")
    p.add_argument("--no-sync", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint)
    failures_path = Path(args.failures_output)
    failures_input_path = Path(args.failures_input) if args.failures_input else failures_path
    changed_only = not args.all
    audit_path = Path(args.audit_file) if args.audit_file else None
    audit_severities = {
        token.strip().lower()
        for token in str(args.audit_severities or "").split(",")
        if token.strip()
    }

    inputs_payload = _load_json(input_path)

    formal_payload = _load_json(output_path) if output_path.exists() else {"units": []}
    formal_dossiers = index_existing_dossiers(formal_payload)
    checkpoint_dossiers = _load_checkpoint_dossiers(checkpoint_path)
    effective = merge_formal_and_checkpoint(
        inputs_payload=inputs_payload,
        formal_dossiers=formal_dossiers,
        checkpoint_dossiers=checkpoint_dossiers,
    )

    if args.retry_failures:
        prior = _load_failures(failures_input_path)
        if not prior:
            print(f"No failures found in {failures_input_path}.")
            return 0
        candidates = choose_failure_candidates(failures=prior, inputs_payload=inputs_payload)
        src = "retry-failures"
    elif audit_path:
        candidates = choose_audit_candidates(
            inputs_payload=inputs_payload,
            audit_path=audit_path,
            severities=audit_severities,
            max_count=args.audit_limit,
        )
        src = "audit-file"
    else:
        candidates = choose_candidates(
            inputs_payload=inputs_payload,
            existing_dossiers=effective,
            changed_only=changed_only,
            unit_id=args.unit_id,
            limit=args.limit,
            force=args.force,
        )
        src = "unit-id" if args.unit_id else ("all" if args.all else "changed-only")

    total_input = len(iter_input_units(inputs_payload))
    print(f"Total units in input: {total_input}")
    print(f"Candidate source: {src}")
    print(f"Candidates selected: {len(candidates)}")

    if args.dry_run:
        for item in candidates:
            print(f"  - {_unit_key(item)}")
        return 0

    if not candidates:
        merged = _merge_units(inputs_payload=inputs_payload, existing_dossiers=effective, newly_generated={})
        _write_json(output_path, {
            "version": OUTPUT_VERSION, "generated_at": _now_iso(),
            "generator": GENERATOR_NAME, "model": resolve_model_name(),
            "dossier_version": DOSSIER_VERSION, "units": merged,
        })
        if not args.no_sync:
            _sync_public_mirror(output_path=output_path, public_data_dir=Path(args.public_data_dir))
        if checkpoint_path.exists():
            checkpoint_path.unlink(missing_ok=True)
        print("No stale units. narrative_units.json refreshed.")
        return 0

    api_key = ensure_api_key()
    model_name = resolve_model_name()
    client = GeminiClient(api_key=api_key, model_name=model_name, timeout_seconds=resolve_timeout_seconds())
    client.preflight()
    system_prompt, rewrite_template = load_prompts(
        sys_prompt_path=Path(args.sys_prompt),
        rewrite_prompt_path=Path(args.rewrite_prompt),
    )

    # Build packets
    packets: Dict[str, dict] = {}
    for item in iter_input_units(inputs_payload):
        uid = _unit_key(item)
        if uid:
            packets[uid] = build_unit_packet(item)

    checkpoint_mgr = CheckpointManager(
        checkpoint_path=checkpoint_path, existing_dossiers=effective,
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
        uid = _unit_key(item)
        packet = packets.get(uid)
        if not packet:
            raise RuntimeError(f"Packet missing for {uid}")
        dossier = _retry_generate(
            client=client, packet=packet,
            system_prompt=system_prompt, rewrite_template=rewrite_template,
        )
        return uid, dossier, time.monotonic() - t0

    try:
        with ThreadPoolExecutor(max_workers=resolve_max_concurrency()) as pool:
            future_map = {pool.submit(_task, item): item for item in candidates}
            with _running_lock:
                running_counter[0] = len(future_map)
            for future in as_completed(future_map):
                item = future_map[future]
                uid = _unit_key(item)
                try:
                    resolved_uid, dossier, duration = future.result()
                    checkpoint_mgr.record_success(resolved_uid, dossier)
                    print(f"  ✓ {resolved_uid} ({duration:.1f}s)")
                except Exception as exc:
                    checkpoint_mgr.record_failure()
                    failures.append({"unit_id": uid, "input_hash": str(item.get("input_hash", "")), "error": str(exc)})
                    print(f"  ✗ {uid} -> {exc}")
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

    all_dossiers = checkpoint_mgr.get_all_dossiers()
    merged = _merge_units(inputs_payload=inputs_payload, existing_dossiers=all_dossiers, newly_generated={})
    _write_json(output_path, {
        "version": OUTPUT_VERSION, "generated_at": _now_iso(),
        "generator": GENERATOR_NAME, "model": model_name,
        "dossier_version": DOSSIER_VERSION, "units": merged,
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
