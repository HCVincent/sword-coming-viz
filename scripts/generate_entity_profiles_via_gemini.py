#!/usr/bin/env python3
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from swordcoming_pipeline.llm_json import LLMJSONParseError, extract_json_from_response


DEFAULT_MODEL = "gemini-3.1-pro-preview"
OUTPUT_VERSION = "entity-profiles-v1"
PROFILE_VERSION = "role-location-profile-v1"
GENERATOR_NAME = "gemini-api"
MAX_RETRIES = 2

CHECKPOINT_FLUSH_INTERVAL = 5       # flush every N successful entities
CHECKPOINT_TIME_INTERVAL = 30.0     # or every N seconds, whichever comes first
HEARTBEAT_INTERVAL = 15.0           # progress heartbeat every N seconds


def _now_iso() -> str:
    return datetime.now().isoformat()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_model_name() -> str:
    configured = str(os.getenv("GEMINI_MODEL", "")).strip()
    return configured or DEFAULT_MODEL


def resolve_max_concurrency() -> int:
    raw = str(os.getenv("GEMINI_MAX_CONCURRENCY", "1")).strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return max(1, value)


def resolve_timeout_seconds() -> int:
    raw = str(os.getenv("GEMINI_TIMEOUT_SECONDS", "60")).strip()
    try:
        value = int(raw)
    except ValueError:
        return 60
    return max(10, value)


def ensure_api_key() -> str:
    key = str(os.getenv("GEMINI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY. Please export GEMINI_API_KEY before running this script.")
    return key


def _normalize_entity_type(value: str) -> str:
    v = str(value or "").strip().lower()
    if v in {"role", "roles"}:
        return "role"
    if v in {"location", "locations"}:
        return "location"
    return ""


def load_prompts(*, sys_prompt_path: Path, rewrite_prompt_path: Path) -> Tuple[str, str]:
    sys_prompt = sys_prompt_path.read_text(encoding="utf-8").strip()
    rewrite_template = rewrite_prompt_path.read_text(encoding="utf-8")
    if "{draft_json}" not in rewrite_template or "{packet_json}" not in rewrite_template:
        raise ValueError("Rewrite prompt template must include {draft_json} and {packet_json} placeholders.")
    return sys_prompt, rewrite_template


def build_packet(item: dict) -> dict:
    packet = {
        "entity_type": item.get("entity_type"),
        "entity_id": item.get("entity_id"),
        "canonical_name": item.get("canonical_name"),
        "input_hash": item.get("input_hash"),
        "identity_facts": item.get("identity_facts", []),
        "relationship_facts": item.get("top_related_entities_weighted", item.get("top_related_entities", [])),
        "location_facts": item.get("top_locations_weighted", item.get("top_locations", [])),
        "phase_arc": item.get("phase_arc_candidates", []),
        "turning_points": item.get("turning_point_candidates", []),
        "representative_excerpts": item.get("representative_original_excerpts", []),
        "original_descriptions": item.get("original_descriptions", []),
        "evidence_excerpt_ids": item.get("evidence_excerpt_ids", []),
    }
    if packet["entity_type"] == "location":
        packet["relationship_facts"] = item.get("top_roles", [])
        packet["location_facts"] = [item.get("canonical_name")] if item.get("canonical_name") else []
        packet["major_events"] = item.get("top_events", [])
        packet["location_type"] = item.get("location_type")
    return packet


def write_packets(payload: dict, packets_dir: Path) -> Dict[Tuple[str, str], dict]:
    role_dir = packets_dir / "roles"
    location_dir = packets_dir / "locations"
    role_dir.mkdir(parents=True, exist_ok=True)
    location_dir.mkdir(parents=True, exist_ok=True)

    packet_index: Dict[Tuple[str, str], dict] = {}
    for plural, subdir in (("roles", role_dir), ("locations", location_dir)):
        for item in payload.get(plural, []):
            entity_type = _normalize_entity_type(item.get("entity_type", plural[:-1]))
            entity_id = str(item.get("entity_id", "")).strip()
            if not entity_type or not entity_id:
                continue
            packet = build_packet(item)
            packet_index[(entity_type, entity_id)] = packet
            output_path = subdir / f"{entity_id}.json"
            _write_json(output_path, packet)
    return packet_index


def iter_input_entities(payload: dict) -> Iterable[dict]:
    for item in payload.get("roles", []):
        yield item
    for item in payload.get("locations", []):
        yield item


def index_existing_profiles(payload: dict) -> Dict[Tuple[str, str], dict]:
    profiles = payload.get("profiles", payload if isinstance(payload, list) else [])
    index: Dict[Tuple[str, str], dict] = {}
    for item in profiles:
        entity_type = _normalize_entity_type(item.get("entity_type", ""))
        entity_id = str(item.get("entity_id", "")).strip()
        if entity_type and entity_id:
            index[(entity_type, entity_id)] = item
    return index


def is_profile_fresh(*, input_item: dict, existing_profile: Optional[dict]) -> bool:
    if not existing_profile:
        return False
    expected = str(input_item.get("input_hash", "")).strip()
    actual = str(existing_profile.get("generated_from_input_hash", "")).strip()
    return bool(expected and expected == actual)


def choose_candidates(
    *,
    inputs_payload: dict,
    existing_profiles: Dict[Tuple[str, str], dict],
    changed_only: bool,
    entity_id: Optional[str],
    entity_type: Optional[str],
    limit: Optional[int],
    force: bool,
) -> List[dict]:
    chosen: List[dict] = []
    norm_type = _normalize_entity_type(entity_type or "") if entity_type else ""
    for item in iter_input_entities(inputs_payload):
        curr_type = _normalize_entity_type(item.get("entity_type", ""))
        curr_id = str(item.get("entity_id", "")).strip()
        if not curr_type or not curr_id:
            continue
        if norm_type and curr_type != norm_type:
            continue
        if entity_id and curr_id != entity_id:
            continue

        existing = existing_profiles.get((curr_type, curr_id))
        if not force and changed_only and is_profile_fresh(input_item=item, existing_profile=existing):
            continue
        chosen.append(item)

    if limit is not None:
        chosen = chosen[: max(0, limit)]
    return chosen


def _build_draft_user_prompt(packet: dict) -> str:
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2)
    return (
        "请基于以下 entity packet 生成一份 dossier 初稿。严格输出 JSON，不要输出 markdown 代码围栏。\n\n"
        "输出字段必须包含：entity_type, entity_id, identity_summary, display_summary, long_description, "
        "story_function, phase_arc, relationship_clusters, major_locations, turning_points, evidence_excerpt_ids。\n\n"
        "entity packet:\n"
        f"{packet_json}"
    )


def _extract_text_from_response(response: Any) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text
    # Fallback for SDK variants
    candidates = getattr(response, "candidates", None)
    if candidates:
        chunks: List[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue
            for part in parts:
                maybe_text = getattr(part, "text", None)
                if maybe_text:
                    chunks.append(str(maybe_text))
        if chunks:
            return "\n".join(chunks).strip()
    return ""


def _coerce_profile(raw: dict, *, packet: dict, model_name: str) -> dict:
    entity_type = _normalize_entity_type(raw.get("entity_type") or packet.get("entity_type") or "")
    entity_id = str(raw.get("entity_id") or packet.get("entity_id") or "").strip()
    if not entity_type or not entity_id:
        raise ValueError("Model response missing entity_type/entity_id")

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "identity_summary": str(raw.get("identity_summary", "")).strip(),
        "display_summary": str(raw.get("display_summary", "")).strip(),
        "long_description": str(raw.get("long_description", "")).strip(),
        "story_function": str(raw.get("story_function", "")).strip(),
        "phase_arc": str(raw.get("phase_arc", "")).strip(),
        "relationship_clusters": list(raw.get("relationship_clusters", [])),
        "major_locations": list(raw.get("major_locations", [])),
        "turning_points": list(raw.get("turning_points", [])),
        "evidence_excerpt_ids": list(raw.get("evidence_excerpt_ids", packet.get("evidence_excerpt_ids", [])))[:10],
        "generated_from_input_hash": str(packet.get("input_hash", "")).strip(),
        "generator": GENERATOR_NAME,
        "model": model_name,
        "profile_version": PROFILE_VERSION,
        "generated_at": _now_iso(),
    }


class GeminiClient:
    def __init__(self, *, api_key: str, model_name: str, timeout_seconds: int) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_client(self):
        with self._lock:
            if self._client is not None:
                return self._client
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
            return self._client

    def preflight(self) -> None:
        client = self._ensure_client()
        try:
            response = client.models.generate_content(
                model=self._model_name,
                contents="Return exactly this JSON: {\"ok\": true}",
            )
        except Exception as exc:  # pragma: no cover - SDK/runtime dependent
            raise RuntimeError(
                "Gemini preflight failed. GEMINI_API_KEY is set but the requested model is unavailable "
                f"or inaccessible: {self._model_name}. Original error: {exc}"
            ) from exc

        text = _extract_text_from_response(response)
        if not text:
            raise RuntimeError("Gemini preflight returned empty response text.")
        try:
            parsed = extract_json_from_response(text)
        except LLMJSONParseError as exc:
            raise RuntimeError(f"Gemini preflight returned non-JSON response: {text[:200]}") from exc
        if parsed.get("ok") is not True:
            raise RuntimeError(f"Gemini preflight validation failed for model {self._model_name}: {parsed}")

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        client = self._ensure_client()
        response = client.models.generate_content(
            model=self._model_name,
            contents=user_prompt,
            config={"system_instruction": system_prompt},
        )
        text = _extract_text_from_response(response)
        if not text:
            raise RuntimeError("Gemini returned empty response text.")
        return extract_json_from_response(text)


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
    return _coerce_profile(final_raw, packet=packet, model_name=client.model_name)


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


def _merge_profiles(
    *,
    inputs_payload: dict,
    existing_profiles: Dict[Tuple[str, str], dict],
    newly_generated: Dict[Tuple[str, str], dict],
) -> List[dict]:
    ordered: List[dict] = []
    for item in iter_input_entities(inputs_payload):
        entity_type = _normalize_entity_type(item.get("entity_type", ""))
        entity_id = str(item.get("entity_id", "")).strip()
        if not entity_type or not entity_id:
            continue
        key = (entity_type, entity_id)
        profile = newly_generated.get(key) or existing_profiles.get(key)
        if profile:
            ordered.append(profile)
    return ordered


def _sync_public_mirror(*, output_path: Path, public_data_dir: Path) -> None:
    public_data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output_path, public_data_dir / output_path.name)


def _write_failures(path: Path, failures: List[dict]) -> None:
    payload = {
        "generated_at": _now_iso(),
        "failure_count": len(failures),
        "failures": failures,
    }
    _write_json(path, payload)


def _fail_key(item: dict) -> Tuple[str, str]:
    return (_normalize_entity_type(item.get("entity_type", "")), str(item.get("entity_id", "")).strip())


def _load_failures(path: Path) -> List[dict]:
    """Load failure report and return list of failure entries."""
    if not path.exists():
        return []
    payload = _load_json(path)
    return list(payload.get("failures", []))


def choose_failure_candidates(
    *,
    failures: List[dict],
    inputs_payload: dict,
) -> List[dict]:
    """Build candidate list from failure report, matched against inputs."""
    fail_keys = set()
    for f in failures:
        et = _normalize_entity_type(f.get("entity_type", ""))
        eid = str(f.get("entity_id", "")).strip()
        if et and eid:
            fail_keys.add((et, eid))

    chosen: List[dict] = []
    for item in iter_input_entities(inputs_payload):
        curr_type = _normalize_entity_type(item.get("entity_type", ""))
        curr_id = str(item.get("entity_id", "")).strip()
        if (curr_type, curr_id) in fail_keys:
            chosen.append(item)
    return chosen


class CheckpointManager:
    """Thread-safe manager for incremental checkpoint persistence."""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        existing_profiles: Dict[Tuple[str, str], dict],
        inputs_payload: dict,
        model_name: str,
    ) -> None:
        self._checkpoint_path = checkpoint_path
        self._model_name = model_name
        self._inputs_payload = inputs_payload
        self._lock = threading.Lock()
        # Start with existing profiles so checkpoint always has full context
        self._profiles: Dict[Tuple[str, str], dict] = dict(existing_profiles)
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

    def record_success(self, key: Tuple[str, str], profile: dict) -> None:
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
            profiles_snapshot = dict(self._profiles)
            gen_count = self._generated_count
            fail_count = self._failed_count
            self._unflushed_count = 0
            self._last_flush_time = time.monotonic()

        ordered = _merge_profiles(
            inputs_payload=self._inputs_payload,
            existing_profiles=profiles_snapshot,
            newly_generated={},
        )

        payload = {
            "version": OUTPUT_VERSION,
            "generated_at": _now_iso(),
            "generator": GENERATOR_NAME,
            "model": self._model_name,
            "profile_version": PROFILE_VERSION,
            "generation_status": "partial",
            "generated_count": gen_count,
            "failed_count": fail_count,
            "last_checkpoint_at": _now_iso(),
            "profiles": ordered,
        }
        _write_json(self._checkpoint_path, payload)

    def get_all_profiles(self) -> Dict[Tuple[str, str], dict]:
        with self._lock:
            return dict(self._profiles)


def _load_checkpoint_profiles(checkpoint_path: Path) -> Dict[Tuple[str, str], dict]:
    """Load profiles from checkpoint file if it exists."""
    if not checkpoint_path.exists():
        return {}
    try:
        payload = _load_json(checkpoint_path)
    except Exception:
        return {}
    return index_existing_profiles(payload)


def _best_profile(
    *,
    key: Tuple[str, str],
    formal: Optional[dict],
    checkpoint: Optional[dict],
    input_hash: str,
) -> Optional[dict]:
    """Pick the best profile between formal and checkpoint for a given entity."""
    candidates = []
    for source in (formal, checkpoint):
        if source and str(source.get("generated_from_input_hash", "")).strip() == input_hash:
            candidates.append(source)
    if not candidates:
        # Fall back to any available (stale) profile
        return formal or checkpoint
    if len(candidates) == 1:
        return candidates[0]
    # Both match hash — pick by generated_at
    def _ts(p: dict) -> str:
        return str(p.get("generated_at", ""))
    return max(candidates, key=_ts)


def merge_formal_and_checkpoint(
    *,
    inputs_payload: dict,
    formal_profiles: Dict[Tuple[str, str], dict],
    checkpoint_profiles: Dict[Tuple[str, str], dict],
) -> Dict[Tuple[str, str], dict]:
    """Merge formal and checkpoint profiles, preferring hash-matching + newer."""
    merged: Dict[Tuple[str, str], dict] = {}
    for item in iter_input_entities(inputs_payload):
        et = _normalize_entity_type(item.get("entity_type", ""))
        eid = str(item.get("entity_id", "")).strip()
        if not et or not eid:
            continue
        key = (et, eid)
        ih = str(item.get("input_hash", "")).strip()
        best = _best_profile(
            key=key,
            formal=formal_profiles.get(key),
            checkpoint=checkpoint_profiles.get(key),
            input_hash=ih,
        )
        if best:
            merged[key] = best
    return merged


def _heartbeat_loop(
    *,
    stop_event: threading.Event,
    checkpoint_mgr: CheckpointManager,
    total: int,
    start_time: float,
    running_count: threading.local,
) -> None:
    """Background thread printing periodic progress."""
    while not stop_event.wait(timeout=HEARTBEAT_INTERVAL):
        elapsed = time.monotonic() - start_time
        gen = checkpoint_mgr.generated_count
        fail = checkpoint_mgr.failed_count
        running = getattr(running_count, "value", 0)
        print(
            f"  Progress: {gen + fail}/{total} | success={gen} | failed={fail}"
            f" | running={running} | elapsed={elapsed:.0f}s"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate entity_profiles.json via Gemini API.")
    parser.add_argument("--input", default="data/entity_profile_inputs.json", help="entity_profile_inputs.json path")
    parser.add_argument("--output", default="data/entity_profiles.json", help="entity_profiles.json output path")
    parser.add_argument(
        "--checkpoint",
        default="data/entity_profiles.checkpoint.json",
        help="Checkpoint file for partial progress persistence",
    )
    parser.add_argument(
        "--packets-dir",
        default="data/entity_profile_packets",
        help="Directory for single-entity packet files",
    )
    parser.add_argument(
        "--failures-output",
        default="data/entity_profile_generation_failures.json",
        help="Failed entity generation report path",
    )
    parser.add_argument("--sys-prompt", default="prompts/sys_entity_profile_gemini.md", help="System prompt path")
    parser.add_argument(
        "--rewrite-prompt",
        default="prompts/user_entity_profile_gemini.md",
        help="Self-critique rewrite prompt template path",
    )
    parser.add_argument("--changed-only", action="store_true", default=True, help="Generate only stale/missing entities")
    parser.add_argument("--all", action="store_true", help="Generate all entities (disables --changed-only)")
    parser.add_argument("--entity-id", default=None, help="Generate only one entity_id")
    parser.add_argument("--entity-type", default=None, help="Filter by entity type: role|location")
    parser.add_argument("--limit", type=int, default=None, help="Limit entities to process")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if hash is unchanged")
    parser.add_argument("--dry-run", action="store_true", help="Preview candidates without calling API")
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="Only regenerate entities from the failure report",
    )
    parser.add_argument(
        "--failures-input",
        default=None,
        help="Failure report to read for --retry-failures (defaults to --failures-output path)",
    )
    parser.add_argument(
        "--public-data-dir",
        default="visualization/public/data",
        help="public/data mirror directory",
    )
    parser.add_argument("--no-sync", action="store_true", help="Skip syncing output to public/data")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint)
    packets_dir = Path(args.packets_dir)
    failures_path = Path(args.failures_output)
    failures_input_path = Path(args.failures_input) if args.failures_input else failures_path
    sys_prompt_path = Path(args.sys_prompt)
    rewrite_prompt_path = Path(args.rewrite_prompt)

    changed_only = not args.all

    # ── Load inputs & build packets ──────────────────────────────────────
    inputs_payload = _load_json(input_path)
    packets = write_packets(inputs_payload, packets_dir)

    # ── Load existing profiles (formal + checkpoint) ─────────────────────
    formal_payload = _load_json(output_path) if output_path.exists() else {"profiles": []}
    formal_profiles = index_existing_profiles(formal_payload)
    checkpoint_profiles = _load_checkpoint_profiles(checkpoint_path)

    # Merge formal and checkpoint to get best-known state per entity
    effective_profiles = merge_formal_and_checkpoint(
        inputs_payload=inputs_payload,
        formal_profiles=formal_profiles,
        checkpoint_profiles=checkpoint_profiles,
    )

    # ── Select candidates ────────────────────────────────────────────────
    if args.retry_failures:
        prior_failures = _load_failures(failures_input_path)
        if not prior_failures:
            print(f"No failures found in {failures_input_path}. Nothing to retry.")
            return 0
        candidates = choose_failure_candidates(
            failures=prior_failures,
            inputs_payload=inputs_payload,
        )
        candidate_source = "retry-failures"
    else:
        candidates = choose_candidates(
            inputs_payload=inputs_payload,
            existing_profiles=effective_profiles,
            changed_only=changed_only,
            entity_id=args.entity_id,
            entity_type=args.entity_type,
            limit=args.limit,
            force=args.force,
        )
        candidate_source = "entity-id" if args.entity_id else (
            "entity-type" if args.entity_type else (
                "all" if args.all else "changed-only"
            )
        )

    print(f"Packets written: {len(packets)}")
    print(f"Candidate source: {candidate_source}")
    print(f"Candidates selected: {len(candidates)}")

    if args.dry_run:
        for item in candidates:
            print(f"  - {_normalize_entity_type(item.get('entity_type', ''))}:{item.get('entity_id')}")
        return 0

    # ── No candidates: refresh formal artifact and exit ──────────────────
    if not candidates:
        merged_profiles = _merge_profiles(
            inputs_payload=inputs_payload,
            existing_profiles=effective_profiles,
            newly_generated={},
        )
        output_payload = {
            "version": OUTPUT_VERSION,
            "generated_at": _now_iso(),
            "generator": GENERATOR_NAME,
            "model": resolve_model_name(),
            "profile_version": PROFILE_VERSION,
            "profiles": merged_profiles,
        }
        _write_json(output_path, output_payload)
        if not args.no_sync:
            _sync_public_mirror(output_path=output_path, public_data_dir=Path(args.public_data_dir))
        # Clean up checkpoint if everything is current
        if checkpoint_path.exists():
            checkpoint_path.unlink(missing_ok=True)
        print("No stale entities. entity_profiles.json refreshed with existing cached profiles.")
        return 0

    # ── Initialize Gemini client ─────────────────────────────────────────
    api_key = ensure_api_key()
    model_name = resolve_model_name()
    timeout_seconds = resolve_timeout_seconds()
    max_concurrency = resolve_max_concurrency()

    client = GeminiClient(api_key=api_key, model_name=model_name, timeout_seconds=timeout_seconds)
    client.preflight()

    system_prompt, rewrite_template = load_prompts(
        sys_prompt_path=sys_prompt_path,
        rewrite_prompt_path=rewrite_prompt_path,
    )

    # ── Checkpoint manager ───────────────────────────────────────────────
    checkpoint_mgr = CheckpointManager(
        checkpoint_path=checkpoint_path,
        existing_profiles=effective_profiles,
        inputs_payload=inputs_payload,
        model_name=model_name,
    )

    # Register emergency flush on exit / interrupt
    _emergency_flushed = threading.Event()

    def _emergency_flush(*_args: Any) -> None:
        if _emergency_flushed.is_set():
            return
        _emergency_flushed.set()
        checkpoint_mgr.flush()
        print("\n  Checkpoint flushed on exit.")

    atexit.register(_emergency_flush)
    signal.signal(signal.SIGINT, lambda *a: (_emergency_flush(), sys.exit(130)))

    # ── Heartbeat thread ─────────────────────────────────────────────────
    stop_heartbeat = threading.Event()
    running_counter = threading.local()
    running_counter.value = 0
    _running_lock = threading.Lock()

    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        kwargs={
            "stop_event": stop_heartbeat,
            "checkpoint_mgr": checkpoint_mgr,
            "total": len(candidates),
            "start_time": time.monotonic(),
            "running_count": running_counter,
        },
        daemon=True,
    )
    heartbeat_thread.start()
    start_time = time.monotonic()

    # ── Generation loop ──────────────────────────────────────────────────
    failures: List[dict] = []
    generated_this_run: Dict[Tuple[str, str], dict] = {}

    def _task(item: dict) -> Tuple[Tuple[str, str], dict, float]:
        t0 = time.monotonic()
        key = _fail_key(item)
        packet = packets.get(key)
        if not packet:
            raise RuntimeError(f"Packet missing for {key}")
        profile = _retry_generate(
            client=client,
            packet=packet,
            system_prompt=system_prompt,
            rewrite_template=rewrite_template,
        )
        return key, profile, time.monotonic() - t0

    try:
        with ThreadPoolExecutor(max_workers=max_concurrency) as pool:
            future_map = {pool.submit(_task, item): item for item in candidates}
            with _running_lock:
                running_counter.value = len(future_map)

            for future in as_completed(future_map):
                item = future_map[future]
                key = _fail_key(item)
                try:
                    resolved_key, profile, duration = future.result()
                    generated_this_run[resolved_key] = profile
                    checkpoint_mgr.record_success(resolved_key, profile)
                    print(f"  ✓ {resolved_key[0]}:{resolved_key[1]} ({duration:.1f}s)")
                except Exception as exc:
                    checkpoint_mgr.record_failure()
                    failures.append(
                        {
                            "entity_type": key[0],
                            "entity_id": key[1],
                            "input_hash": str(item.get("input_hash", "")),
                            "error": str(exc),
                        }
                    )
                    print(f"  ✗ {key[0]}:{key[1]} -> {exc}")
                finally:
                    with _running_lock:
                        running_counter.value = max(0, running_counter.value - 1)
    except KeyboardInterrupt:
        checkpoint_mgr.flush()
        print("\nInterrupted. Checkpoint saved.")
        return 130
    finally:
        stop_heartbeat.set()

    # Always flush checkpoint after loop
    checkpoint_mgr.flush()

    # ── Summary ──────────────────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    gen_count = checkpoint_mgr.generated_count
    fail_count = checkpoint_mgr.failed_count
    print(f"\n{'='*60}")
    print(f"  Total candidates:  {len(candidates)}")
    print(f"  Succeeded:         {gen_count}")
    print(f"  Failed:            {fail_count}")
    print(f"  Elapsed:           {elapsed:.0f}s")

    # ── Write outputs based on success/failure ───────────────────────────
    if failures:
        _write_failures(failures_path, failures)
        print(f"  Failure report:    {failures_path}")
        print(f"  Checkpoint:        {checkpoint_path}")
        print(f"  Formal output NOT updated (partial run).")
        print(f"{'='*60}")
        return 2

    # All succeeded — write formal artifact
    all_profiles = checkpoint_mgr.get_all_profiles()
    merged_profiles = _merge_profiles(
        inputs_payload=inputs_payload,
        existing_profiles=all_profiles,
        newly_generated={},
    )

    output_payload = {
        "version": OUTPUT_VERSION,
        "generated_at": _now_iso(),
        "generator": GENERATOR_NAME,
        "model": model_name,
        "profile_version": PROFILE_VERSION,
        "profiles": merged_profiles,
    }
    _write_json(output_path, output_payload)

    if not args.no_sync:
        _sync_public_mirror(output_path=output_path, public_data_dir=Path(args.public_data_dir))

    # Clean up checkpoint and failure report on full success
    if checkpoint_path.exists():
        checkpoint_path.unlink(missing_ok=True)
    if failures_path.exists():
        failures_path.unlink(missing_ok=True)

    print(f"  Output:            {output_path}")
    print(f"  Generated this run: {gen_count}")
    print(f"  Checkpoint cleaned up.")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
