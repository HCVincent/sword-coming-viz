"""Tests for event dossier input determinism.

Ensures that:
1. participants are always sorted in event dossier packets
2. Two consecutive builds from the same KB/insights/key-events produce
   identical event_dossier_inputs.json output
3. input_hash is stable across repeated builds
"""
from __future__ import annotations

import json

import pytest

from model.unified import (
    UnifiedEvent,
    UnifiedKnowledgeBase,
    UnifiedRelation,
    UnifiedRole,
)
from scripts.build_event_dossier_inputs import (
    _build_event_packet,
    _collect_referenced_event_ids,
    _score_event,
    build_event_dossier_inputs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _role(name: str) -> UnifiedRole:
    return UnifiedRole(
        id=name,
        canonical_name=name,
        all_names={name},
        description="",
        total_mentions=1,
        juans_appeared={1},
        units_appeared={1},
    )


def _event(
    eid: str,
    participants: set[str],
    *,
    source_units: set[int] | None = None,
    significance: str = "",
    location: str = "",
    evidence_excerpt: str = "",
    title_source: str = "",
) -> UnifiedEvent:
    return UnifiedEvent(
        id=eid,
        name=eid,
        description="desc",
        participants=participants,
        source_juans={1},
        source_units=source_units or {1},
        significance=significance,
        location=location,
        evidence_excerpt=evidence_excerpt,
        title_source=title_source,
    )


def _make_kb(
    *,
    roles: dict[str, UnifiedRole] | None = None,
    events: dict[str, UnifiedEvent] | None = None,
) -> UnifiedKnowledgeBase:
    _roles = roles or {}
    _events = events or {}
    return UnifiedKnowledgeBase(
        book_id="test",
        roles=_roles,
        events=_events,
        total_roles=len(_roles),
        total_events=len(_events),
        name_to_role_id={r.canonical_name: rid for rid, r in _roles.items()},
    )


def _make_writer_insights_with_refs(event_ids: list[str]) -> dict:
    """Build a minimal writer_insights that references the given event_ids."""
    beats = [
        {"event": {"event_id": eid}, "beat_name": f"beat_{eid}"}
        for eid in event_ids
    ]
    return {
        "season_overviews": [{"story_beats": beats, "anchor_events": []}],
        "character_arcs": [],
        "conflict_chains": [],
        "foreshadowing_threads": [],
        "curated_relationships": [],
    }


def _make_key_events_index_with_refs(event_ids: list[str]) -> dict:
    events = [{"event_id": eid, "event_name": eid} for eid in event_ids]
    return {"chapters": [{"key_events": events}]}


# ---------------------------------------------------------------------------
# Test: participants are sorted in packets
# ---------------------------------------------------------------------------

class TestParticipantsSorted:
    """Participants in event dossier packets must be sorted."""

    def test_participants_sorted_in_packet(self):
        """A set with arbitrary insertion order must produce sorted list."""
        event = _event("e1", {"丁婴", "陈平安", "阿良", "宁姚"})
        source_membership: dict = {}
        score, _ = _score_event(event, source_membership)
        packet = _build_event_packet(
            event,
            source_membership=source_membership,
            event_score=score,
        )
        assert packet["participants"] == sorted(packet["participants"]), (
            "participants must be sorted for hash stability"
        )

    def test_participants_sorted_with_canonical_filter(self):
        """After canonical filtering, participants must still be sorted."""
        event = _event("e1", {"丁婴", "陈平安", "阿良", "宁姚", "噪音名"})
        canonical_ids = {"陈平安", "宁姚", "阿良", "丁婴"}
        source_membership: dict = {}
        score, _ = _score_event(event, source_membership)
        packet = _build_event_packet(
            event,
            source_membership=source_membership,
            event_score=score,
            canonical_role_ids=canonical_ids,
        )
        assert "噪音名" not in packet["participants"]
        assert packet["participants"] == sorted(packet["participants"])

    def test_participants_sorted_in_full_build(self):
        """build_event_dossier_inputs produces sorted participants."""
        roles = {n: _role(n) for n in ["陈平安", "宁姚", "阿良", "丁婴"]}
        events = {
            "e1": _event("e1", {"丁婴", "陈平安", "阿良", "宁姚"}),
        }
        kb = _make_kb(roles=roles, events=events)
        result = build_event_dossier_inputs(
            kb=kb,
            writer_insights=_make_writer_insights_with_refs(["e1"]),
            key_events_index=_make_key_events_index_with_refs(["e1"]),
            top_n=10,
        )
        for evt in result["events"]:
            assert evt["participants"] == sorted(evt["participants"]), (
                f"Event {evt['event_id']} has unsorted participants"
            )


# ---------------------------------------------------------------------------
# Test: full build determinism
# ---------------------------------------------------------------------------

class TestBuildDeterminism:
    """Two consecutive builds from the same inputs must produce identical output."""

    @staticmethod
    def _build_twice():
        """Build event_dossier_inputs twice and return both payloads."""
        role_names = ["陈平安", "宁姚", "阿良", "丁婴", "曹慈", "刘羡阳"]
        roles = {n: _role(n) for n in role_names}

        events = {}
        for i in range(20):
            # Use varying participant sets to exercise sort stability
            participants = set(role_names[: (i % len(role_names)) + 1])
            events[f"event_{i}"] = _event(
                f"event_{i}",
                participants,
                source_units={i + 1},
                significance=f"sig_{i}" if i % 2 == 0 else "",
                location=f"loc_{i}" if i % 3 == 0 else "",
                evidence_excerpt=f"excerpt_{i}" if i % 4 == 0 else "",
                title_source="catalog" if i % 5 == 0 else "",
            )

        kb = _make_kb(roles=roles, events=events)
        event_ids = list(events.keys())
        writer = _make_writer_insights_with_refs(event_ids[:10])
        key_events = _make_key_events_index_with_refs(event_ids[5:15])

        a = build_event_dossier_inputs(
            kb=kb, writer_insights=writer, key_events_index=key_events, top_n=20,
        )
        b = build_event_dossier_inputs(
            kb=kb, writer_insights=writer, key_events_index=key_events, top_n=20,
        )
        return a, b

    def test_same_event_count(self):
        a, b = self._build_twice()
        assert a["total_selected"] == b["total_selected"]

    def test_same_event_ids(self):
        a, b = self._build_twice()
        ids_a = [e["event_id"] for e in a["events"]]
        ids_b = [e["event_id"] for e in b["events"]]
        assert ids_a == ids_b

    def test_same_input_hashes(self):
        a, b = self._build_twice()
        hashes_a = [e["input_hash"] for e in a["events"]]
        hashes_b = [e["input_hash"] for e in b["events"]]
        assert hashes_a == hashes_b, "input_hash must be identical across builds"

    def test_full_json_identical(self):
        a, b = self._build_twice()
        # Exclude generated_at which is a timestamp
        for payload in (a, b):
            payload.pop("generated_at", None)
        json_a = json.dumps(a, ensure_ascii=False, sort_keys=True)
        json_b = json.dumps(b, ensure_ascii=False, sort_keys=True)
        assert json_a == json_b, "Full JSON output must be identical across builds"

    def test_participants_order_stable(self):
        a, b = self._build_twice()
        for ea, eb in zip(a["events"], b["events"]):
            assert ea["participants"] == eb["participants"], (
                f"Participant order differs for {ea['event_id']}"
            )


# ---------------------------------------------------------------------------
# Test: reference_sources and source_units are sorted
# ---------------------------------------------------------------------------

class TestFieldSorting:
    """All list fields that enter the hash must be deterministically ordered."""

    def test_source_units_sorted(self):
        event = _event("e1", {"陈平安"}, source_units={5, 1, 3, 10, 2})
        source_membership: dict = {}
        score, _ = _score_event(event, source_membership)
        packet = _build_event_packet(
            event,
            source_membership=source_membership,
            event_score=score,
        )
        assert packet["source_units"] == [1, 2, 3, 5, 10]

    def test_reference_sources_sorted(self):
        event = _event("e1", {"陈平安"})
        source_membership = {
            "foreshadowing": {"e1"},
            "anchor_events": {"e1"},
            "story_beats": {"e1"},
        }
        score, _ = _score_event(event, source_membership)
        packet = _build_event_packet(
            event,
            source_membership=source_membership,
            event_score=score,
        )
        assert packet["reference_sources"] == sorted(packet["reference_sources"])
