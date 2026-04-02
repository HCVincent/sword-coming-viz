from __future__ import annotations

import json

from scripts.build_narrative_unit_dossier_inputs import build_narrative_unit_dossier_inputs
from scripts.validate_narrative_units import validate_narrative_units


BOUNDARIES = {
    "version": "narrative-unit-boundaries-v1",
    "book_id": "sword-coming",
    "total_units": 1,
    "units": [
        {
            "unit_id": "nu-001",
            "unit_index": 1,
            "season_name": "第一季",
            "start_unit_index": 1,
            "end_unit_index": 2,
            "source_unit_indexes": [1, 2],
            "source_event_ids": ["e-1", "e-2"],
            "chapter_titles": ["惊蛰", "开门"],
            "main_roles": ["陈平安", "宁姚"],
            "main_locations": ["泥瓶巷"],
            "progress_start": 1,
            "progress_end": 30,
            "boundary_reason": "主角处境建立并引入外来变量",
            "input_hash": "boundary-hash",
        }
    ],
}

CHAPTER_SYNOPSES = {
    "version": "chapter-synopses-v1",
    "book_id": "sword-coming",
    "chapters": [
        {
            "unit_index": 1,
            "unit_title": "第一卷笼中雀 第一章 惊蛰",
            "season_name": "第一季",
            "event_count": 3,
            "active_characters": ["陈平安", "宋集薪"],
            "locations": ["泥瓶巷"],
            "key_developments": ["建立陈平安的生计处境"],
            "synopsis": "陈平安的困顿处境与小镇秩序一并被建立。",
            "narrative_function": "开篇建立人物处境与世界规则",
        },
        {
            "unit_index": 2,
            "unit_title": "第一卷笼中雀 第二章 开门",
            "season_name": "第一季",
            "event_count": 4,
            "active_characters": ["陈平安", "宁姚"],
            "locations": ["泥瓶巷"],
            "key_developments": ["宁姚正式进入小镇线"],
            "synopsis": "宁姚的进入改变了陈平安原本封闭的行动节奏。",
            "narrative_function": "引入改变主线张力的新变量",
        },
    ],
}

KEY_EVENTS_INDEX = {
    "version": "key-events-index-v1",
    "book_id": "sword-coming",
    "chapters": [
        {"unit_index": 1, "key_events": [{"event_id": "e-1", "event_name": "陈平安生计建立", "importance_tier": "critical"}]},
        {"unit_index": 2, "key_events": [{"event_id": "e-2", "event_name": "宁姚进入小镇", "importance_tier": "critical"}]},
    ],
}

WRITER_INSIGHTS = {
    "season_overviews": [
        {
            "story_beats": [
                {
                    "beat_name": "开篇处境建立",
                    "description": "确立陈平安的生计困局与世界压力。",
                    "event": {"event_id": "e-1"},
                }
            ],
            "anchor_events": [
                {
                    "event_id": "e-2",
                    "event_name": "宁姚进入小镇",
                    "selection_reason": "外来变量进入主线",
                }
            ],
        }
    ],
    "character_arcs": [
        {"role_name": "陈平安", "summary": "在被动生存里逐步产生主动性。"}
    ],
    "conflict_chains": [
        {
            "title": "陈平安的生存压力链",
            "summary": "从贫困处境到被迫面对外来变化。",
            "beats": [{"event_id": "e-1"}, {"event_id": "e-2"}],
            "unit_span": [1, 2],
            "source_role_name": "陈平安",
            "target_role_name": "宁姚",
        }
    ],
    "foreshadowing_threads": [
        {
            "label": "外来者改写小镇秩序",
            "summary": "宁姚进入后，小镇的既有平衡开始动摇。",
            "clue_events": [{"event_id": "e-2"}],
            "payoff_events": [],
        }
    ],
}

EVENT_DOSSIERS = {
    "version": "event-dossiers-v1",
    "dossiers": [
        {
            "event_id": "e-1",
            "identity_summary": "开篇先把陈平安的生计与处境压实。",
            "display_summary": "这一事件让主角的匮乏、忍耐与小镇秩序同时落地。",
            "story_function": "为主线建立压力底盘。",
        },
        {
            "event_id": "e-2",
            "identity_summary": "宁姚进入，打破陈平安的单线生活。",
            "display_summary": "外来者进入后，主角的行动节奏和关系重心都开始变化。",
            "story_function": "把主线从静态处境推向动态关系。",
        },
    ],
}


def test_narrative_unit_dossier_inputs_deterministic() -> None:
    first = build_narrative_unit_dossier_inputs(
        boundaries=BOUNDARIES,
        chapter_synopses=CHAPTER_SYNOPSES,
        key_events_index=KEY_EVENTS_INDEX,
        writer_insights=WRITER_INSIGHTS,
        event_dossiers=EVENT_DOSSIERS,
    )
    second = build_narrative_unit_dossier_inputs(
        boundaries=BOUNDARIES,
        chapter_synopses=CHAPTER_SYNOPSES,
        key_events_index=KEY_EVENTS_INDEX,
        writer_insights=WRITER_INSIGHTS,
        event_dossiers=EVENT_DOSSIERS,
    )

    first.pop("generated_at", None)
    second.pop("generated_at", None)
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )
    assert first["units"][0]["input_hash"] == second["units"][0]["input_hash"]


def test_narrative_unit_dossier_inputs_include_writer_refs() -> None:
    payload = build_narrative_unit_dossier_inputs(
        boundaries=BOUNDARIES,
        chapter_synopses=CHAPTER_SYNOPSES,
        key_events_index=KEY_EVENTS_INDEX,
        writer_insights=WRITER_INSIGHTS,
        event_dossiers=EVENT_DOSSIERS,
    )
    unit = payload["units"][0]
    assert unit["writer_refs"]
    assert {item["type"] for item in unit["writer_refs"]} >= {
        "story_beat",
        "anchor_event",
        "character_arc",
        "conflict_chain",
        "foreshadowing",
    }


def test_validate_narrative_units_accepts_structural_unit() -> None:
    inputs_payload = build_narrative_unit_dossier_inputs(
        boundaries=BOUNDARIES,
        chapter_synopses=CHAPTER_SYNOPSES,
        key_events_index=KEY_EVENTS_INDEX,
        writer_insights=WRITER_INSIGHTS,
        event_dossiers=EVENT_DOSSIERS,
    )
    unit_input = inputs_payload["units"][0]
    units_payload = {
        "version": "narrative-units-v1",
        "generated_at": "2026-04-02T00:00:00",
        "book_id": "sword-coming",
        "dossier_version": "narrative-unit-dossier-v1",
        "units": [
            {
                "unit_id": "nu-001",
                "title": "困局裂口",
                "display_summary": "这组章节先把陈平安在小镇里的困顿生活和被压抑的行动空间钉牢，再借宁姚的闯入撬开原本封闭的叙事局面，让故事从静态处境正式转向动态关系，也让后续人物线第一次出现真正可持续升级的张力。",
                "long_summary": "这一剧情单元真正完成的，不只是开篇交代背景，而是把陈平安为何值得被观众持续追随的基础先建立起来。前两章不断压实他的贫穷、克制与对小镇秩序的被动承受，让他先处在一个几乎没有腾挪余地的位置上。\n\n宁姚的进入则不是单纯增加一个重要人物，而是把原本只围绕生存展开的日常，推向会持续改写人物关系和行动方向的新阶段。她带来的不是热闹感，而是对主角处境的重新照亮：陈平安不再只是被世界压着走的人，他开始被迫面对新的责任、选择和外部目光。\n\n因此这段戏的价值，在于它把人物底盘、关系变量和后续主线的动力一起搭起来，为后面的命运展开留下了真正有效的结构接口。",
                "dramatic_function": "作为开篇核心单元，它负责先压实主角处境，再引入改变主线重心的关键外来变量。",
                "what_changes": "在这一单元结束时，陈平安的叙事位置从单纯承受小镇秩序的人，转成必须面对外来人物和新关系压力的人，故事的驱动力因此被真正点燃。",
                "stakes": "如果宁姚没有进入这条线，陈平安的故事会长期停留在被动生存层面，主线很难获得持续升级的关系张力。",
                "unit_index": 1,
                "season_name": "第一季",
                "start_unit_index": 1,
                "end_unit_index": 2,
                "source_event_ids": ["e-1", "e-2"],
                "main_roles": ["陈平安", "宁姚"],
                "main_locations": ["泥瓶巷"],
                "generated_from_input_hash": unit_input["input_hash"],
                "generator": "gemini-api",
                "model": "gemini-3.1-flash-lite-preview",
                "dossier_version": "narrative-unit-dossier-v1",
                "generated_at": "2026-04-02T00:00:00",
            }
        ],
    }
    assert validate_narrative_units(
        inputs_payload=inputs_payload,
        units_payload=units_payload,
    ) == []


def test_validate_narrative_units_rejects_chapter_title_reuse_and_empty_structure_fields() -> None:
    inputs_payload = build_narrative_unit_dossier_inputs(
        boundaries=BOUNDARIES,
        chapter_synopses=CHAPTER_SYNOPSES,
        key_events_index=KEY_EVENTS_INDEX,
        writer_insights=WRITER_INSIGHTS,
        event_dossiers=EVENT_DOSSIERS,
    )
    unit_input = inputs_payload["units"][0]
    units_payload = {
        "version": "narrative-units-v1",
        "generated_at": "2026-04-02T00:00:00",
        "book_id": "sword-coming",
        "dossier_version": "narrative-unit-dossier-v1",
        "units": [
            {
                "unit_id": "nu-001",
                "title": "惊蛰",
                "display_summary": "陈平安生计建立；宁姚进入小镇；开篇处境交代；关系线展开；后续剧情铺垫；小镇秩序建立。",
                "long_summary": "陈平安生计建立。宁姚进入小镇。关系线展开。后续剧情铺垫。",
                "dramatic_function": "",
                "what_changes": "",
                "stakes": "",
                "generated_from_input_hash": unit_input["input_hash"],
                "generator": "gemini-api",
                "model": "gemini-3.1-flash-lite-preview",
            }
        ],
    }
    problems = validate_narrative_units(
        inputs_payload=inputs_payload,
        units_payload=units_payload,
    )
    assert any("title reuses a chapter title verbatim" in item for item in problems)
    assert any("dramatic_function must not be empty" in item for item in problems)
    assert any("what_changes must not be empty" in item for item in problems)
    assert any("stakes must not be empty" in item for item in problems)
