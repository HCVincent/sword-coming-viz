"""Tests for narrative unit boundary determinism and correctness.

Ensures that:
1. Two consecutive builds from identical inputs produce identical output
   (excluding generated_at).
2. validate_boundaries() passes on every synthetic build.
3. Span constraints: every unit covers 1–4 chapters.
4. No overlap: each source unit_index appears in exactly one boundary unit.
5. No gap within a season: consecutive units within a season are adjacent.
6. No cross-season units: all source chapters share the same season_name.
7. input_hash is stable across repeated builds.
8. Season hard-cuts are honoured: chapters from different seasons are never
   merged into the same narrative unit.
"""
from __future__ import annotations

import copy
import json

import pytest

from scripts.build_chapter_structure_inputs import build_chapter_structure_inputs
from scripts.build_narrative_unit_boundaries import (
    build_narrative_unit_boundaries,
    validate_boundaries,
)


# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------

_CHAPTER_SYNOPSES_3 = {
    "version": "chapter-synopses-v1",
    "book_id": "sword-coming",
    "total_chapters": 3,
    "chapters": [
        {
            "unit_index": 1,
            "season_name": "第一卷",
            "unit_title": "章１",
            "synopsis": "陈平安与王朱相遇，开始修行。",
            "narrative_function": "introduce",
            "active_characters": ["陈平安", "王朱"],
            "locations": ["泥瓶巷"],
            "event_count": 3,
        },
        {
            "unit_index": 2,
            "season_name": "第一卷",
            "unit_title": "章２",
            "synopsis": "陈平安继续在泥瓶巷修行，遇到宁姚。",
            "narrative_function": "develop",
            "active_characters": ["陈平安", "宁姚"],
            "locations": ["泥瓶巷"],
            "event_count": 2,
        },
        {
            "unit_index": 3,
            "season_name": "第一卷",
            "unit_title": "章３",
            "synopsis": "宁姚启程离开，陈平安送别。",
            "narrative_function": "turn",
            "active_characters": ["陈平安", "宁姚"],
            "locations": ["泥瓶巷", "城门"],
            "event_count": 4,
        },
    ],
}

_UPI_3 = {
    "version": "unit-progress-index-v1",
    "book_id": "sword-coming",
    "units": {
        "1": {"unit_index": 1, "unit_title": "章１", "season_index": 1, "season_name": "第一卷", "progress_start": 0, "progress_end": 33},
        "2": {"unit_index": 2, "unit_title": "章２", "season_index": 1, "season_name": "第一卷", "progress_start": 34, "progress_end": 66},
        "3": {"unit_index": 3, "unit_title": "章３", "season_index": 1, "season_name": "第一卷", "progress_start": 67, "progress_end": 100},
    },
}

_KEY_EVENTS_3 = {
    "version": "key-events-index-v1",
    "book_id": "sword-coming",
    "chapters": [
        {"unit_index": 1, "key_events": [{"event_id": "evt_001"}, {"event_id": "evt_002"}]},
        {"unit_index": 2, "key_events": [{"event_id": "evt_003"}]},
        {"unit_index": 3, "key_events": [{"event_id": "evt_003"}, {"event_id": "evt_004"}]},
    ],
}

_WRITER_INSIGHTS_EMPTY = {
    "version": "writer-insights-v1",
    "book_id": "sword-coming",
    "season_overviews": [],
    "character_arcs": [],
    "curated_relationships": [],
    "conflict_chains": [],
    "foreshadowing_threads": [],
}


def _make_structure_inputs(synopses=None, upi=None, key_events=None, writer=None):
    return build_chapter_structure_inputs(
        chapter_synopses=synopses or _CHAPTER_SYNOPSES_3,
        unit_progress_index=upi or _UPI_3,
        key_events_index=key_events or _KEY_EVENTS_3,
        writer_insights=writer or _WRITER_INSIGHTS_EMPTY,
    )


def _make_boundaries(synopses=None, upi=None, key_events=None, writer=None):
    structure = _make_structure_inputs(synopses, upi, key_events, writer)
    return build_narrative_unit_boundaries(chapter_structure_inputs=structure)


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

def test_chapter_structure_inputs_deterministic():
    """Two builds from identical inputs produce identical chapter structure outputs."""
    out1 = _make_structure_inputs()
    out2 = _make_structure_inputs()

    # Strip generated_at before comparing
    for o in (out1, out2):
        o.pop("generated_at", None)

    assert out1 == out2


def test_boundaries_deterministic():
    """Two builds from identical inputs produce identical boundary outputs."""
    b1 = _make_boundaries()
    b2 = _make_boundaries()

    for b in (b1, b2):
        b.pop("generated_at", None)
        for u in b.get("units", []):
            u.pop("generated_at", None)

    assert b1 == b2


def test_input_hash_stable():
    """input_hash is identical across two builds of the same chapter."""
    s1 = _make_structure_inputs()
    s2 = _make_structure_inputs()

    hashes1 = {ch["unit_index"]: ch["input_hash"] for ch in s1["chapters"]}
    hashes2 = {ch["unit_index"]: ch["input_hash"] for ch in s2["chapters"]}
    assert hashes1 == hashes2


def test_input_hash_changes_on_different_roles():
    """input_hash changes when chapter metadata changes."""
    synopses_modified = copy.deepcopy(_CHAPTER_SYNOPSES_3)
    synopses_modified["chapters"][0]["active_characters"] = ["陈平安", "王朱", "石苓人"]

    s1 = _make_structure_inputs()
    s2 = _make_structure_inputs(synopses=synopses_modified)

    h1 = next(ch["input_hash"] for ch in s1["chapters"] if ch["unit_index"] == 1)
    h2 = next(ch["input_hash"] for ch in s2["chapters"] if ch["unit_index"] == 1)
    assert h1 != h2


# ---------------------------------------------------------------------------
# Structural correctness tests
# ---------------------------------------------------------------------------

def test_validate_boundaries_passes():
    """validate_boundaries() reports no errors on synthetic 3-chapter build."""
    payload = _make_boundaries()
    errors = validate_boundaries(payload)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_span_within_limits():
    """Every narrative unit covers between 1 and 4 chapters."""
    payload = _make_boundaries()
    for unit in payload["units"]:
        span = len(unit["source_unit_indexes"])
        assert 1 <= span <= 4, f"Unit {unit['unit_id']} has span {span}"


def test_no_overlap():
    """Each source chapter appears in exactly one narrative unit."""
    payload = _make_boundaries()
    seen: set[int] = set()
    for unit in payload["units"]:
        for idx in unit["source_unit_indexes"]:
            assert idx not in seen, f"Chapter {idx} appears in multiple units"
            seen.add(idx)


def test_all_chapters_covered():
    """Every input chapter is covered by exactly one narrative unit."""
    structure = _make_structure_inputs()
    payload = build_narrative_unit_boundaries(chapter_structure_inputs=structure)

    expected = {ch["unit_index"] for ch in structure["chapters"]}
    covered: set[int] = set()
    for unit in payload["units"]:
        covered.update(unit["source_unit_indexes"])

    assert covered == expected


def test_no_gap_within_season():
    """Within a season, consecutive narrative units are adjacent (no gaps)."""
    payload = _make_boundaries()
    units = payload["units"]

    prev_end: dict[str, int] = {}
    for unit in units:
        season = unit["season_name"]
        start = unit["start_unit_index"]
        if season in prev_end:
            assert start == prev_end[season] + 1, (
                f"Gap in {season}: {prev_end[season]} -> {start}"
            )
        prev_end[season] = unit["end_unit_index"]


def test_no_cross_season_units():
    """All source chapters in a narrative unit share the same season_name."""
    structure = _make_structure_inputs()
    season_map = {ch["unit_index"]: ch["season_name"] for ch in structure["chapters"]}
    payload = build_narrative_unit_boundaries(chapter_structure_inputs=structure)

    for unit in payload["units"]:
        unit_season = unit["season_name"]
        for idx in unit["source_unit_indexes"]:
            assert season_map[idx] == unit_season, (
                f"Unit {unit['unit_id']} crosses seasons: "
                f"chapter {idx} is {season_map[idx]}, unit is {unit_season}"
            )


# ---------------------------------------------------------------------------
# Season hard-cut test
# ---------------------------------------------------------------------------

def test_season_hard_cut():
    """Chapters from different seasons are never merged into the same unit."""
    # Two seasons, one chapter each — must produce two separate units.
    synopses_2s = {
        "version": "chapter-synopses-v1",
        "book_id": "sword-coming",
        "total_chapters": 2,
        "chapters": [
            {
                "unit_index": 1,
                "season_name": "第一卷",
                "unit_title": "章１",
                "synopsis": "陈平安初登场",
                "narrative_function": "introduce",
                "active_characters": ["陈平安", "王朱"],
                "locations": ["泥瓶巷"],
                "event_count": 2,
            },
            {
                "unit_index": 2,
                "season_name": "第二卷",
                "unit_title": "章２",
                "synopsis": "陈平安踏上旅途",
                "narrative_function": "develop",
                "active_characters": ["陈平安", "王朱"],
                "locations": ["泥瓶巷"],
                "event_count": 2,
            },
        ],
    }
    upi_2s = {
        "version": "unit-progress-index-v1",
        "book_id": "sword-coming",
        "units": {
            "1": {"unit_index": 1, "unit_title": "章１", "season_index": 1, "season_name": "第一卷", "progress_start": 0, "progress_end": 50},
            "2": {"unit_index": 2, "unit_title": "章２", "season_index": 2, "season_name": "第二卷", "progress_start": 51, "progress_end": 100},
        },
    }
    key_events_2s = {
        "version": "key-events-index-v1",
        "book_id": "sword-coming",
        "chapters": [
            {"unit_index": 1, "key_events": [{"event_id": "evt_001"}]},
            {"unit_index": 2, "key_events": [{"event_id": "evt_001"}]},  # same event — high overlap
        ],
    }

    payload = _make_boundaries(synopses=synopses_2s, upi=upi_2s, key_events=key_events_2s)
    errors = validate_boundaries(payload)
    assert errors == []

    unit_seasons = [(u["unit_id"], u["season_name"]) for u in payload["units"]]
    seasons_seen = [s for _, s in unit_seasons]
    assert "第一卷" in seasons_seen
    assert "第二卷" in seasons_seen

    # Each unit must be in exactly one season
    for unit in payload["units"]:
        assert len({unit["season_name"]}) == 1


# ---------------------------------------------------------------------------
# Empty input graceful handling
# ---------------------------------------------------------------------------

def test_empty_chapters():
    """Empty chapter list produces a valid empty payload."""
    empty = {
        "version": "chapter-structure-inputs-v1",
        "book_id": "sword-coming",
        "total_chapters": 0,
        "chapters": [],
    }
    payload = build_narrative_unit_boundaries(chapter_structure_inputs=empty)
    assert payload["total_units"] == 0
    assert payload["units"] == []
    assert validate_boundaries(payload) == []


# ---------------------------------------------------------------------------
# JSON round-trip test (no generated_at drift)
# ---------------------------------------------------------------------------

def test_json_roundtrip_deterministic():
    """Serialising and re-running with the same structure inputs gives the same
    JSON (modulo generated_at)."""
    structure = _make_structure_inputs()
    payload1 = build_narrative_unit_boundaries(chapter_structure_inputs=structure)
    payload2 = build_narrative_unit_boundaries(chapter_structure_inputs=structure)

    def _strip(d: dict) -> str:
        d = copy.deepcopy(d)
        d.pop("generated_at", None)
        return json.dumps(d, sort_keys=True, ensure_ascii=False)

    assert _strip(payload1) == _strip(payload2)
