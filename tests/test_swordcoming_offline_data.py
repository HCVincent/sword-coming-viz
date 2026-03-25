import json

from entity_resolution import EntityResolver
from model.action import Action
from model.event import Event
from model.role import Role
from scripts import build_swordcoming_offline_data
from scripts.build_swordcoming_writer_insights import build_writer_insights_payload
from scripts.validate_unified_knowledge import validate_unified_knowledge


def test_build_segment_chunk_extracts_core_entities_locations_and_relations():
    unit = {
        "juan_index": 1,
        "unit_title": "第一卷笼中雀 第一章 惊蛰",
    }
    segment = {
        "segment_index": 1,
        "segment_start_time": "第一卷笼中雀 第一章 惊蛰",
        "sentences": [
            "陈平安在泥瓶巷守夜。",
            "宋集薪在墙头讥讽陈平安。",
        ],
    }

    core_cast = {
        "characters": [
            {"name": "陈平安", "aliases": [], "power": "泥瓶巷", "description": "主角"},
            {"name": "宋集薪", "aliases": [], "power": "大骊", "description": "对照人物"},
        ],
        "locations": [
            {"name": "泥瓶巷", "aliases": [], "type": "街巷", "description": "开篇场景"}
        ],
        "relation_keywords": [
            {"action": "讥讽", "keywords": ["讥讽"]},
            {"action": "对话", "keywords": ["说道"]},
        ],
        "event_rules": [
            {
                "name": "惊蛰守夜",
                "event_type": "等待",
                "keywords": ["惊蛰", "守夜", "泥瓶巷", "陈平安"],
                "min_keywords": 3,
                "location": "泥瓶巷",
                "participants": ["陈平安"],
                "significance": "开篇事件",
            }
        ],
        "event_type_rules": [{"type": "等待", "keywords": ["守夜"]}],
    }

    chunk = build_swordcoming_offline_data.build_segment_chunk(
        unit=unit,
        segment=segment,
        character_config={item["name"]: item for item in core_cast["characters"]},
        location_config={item["name"]: item for item in core_cast["locations"]},
        character_matchers=build_swordcoming_offline_data.build_matchers(core_cast["characters"]),
        location_matchers=build_swordcoming_offline_data.build_matchers(core_cast["locations"]),
        relation_keywords=core_cast["relation_keywords"],
        event_rules=core_cast["event_rules"],
        event_type_rules=core_cast["event_type_rules"],
    )

    assert chunk is not None
    assert sorted(role.name for role in chunk.entities) == ["宋集薪", "陈平安"]
    assert [location.name for location in chunk.locations] == ["泥瓶巷"]
    assert [event.name for event in chunk.events] == ["惊蛰守夜"]
    assert len(chunk.relations) == 1
    assert chunk.relations[0].action == "讥讽"
    assert chunk.relations[0].from_roles == ["宋集薪"]
    assert chunk.relations[0].to_roles == ["陈平安"]


def test_build_segment_chunk_creates_pairwise_relations_for_multi_character_sentence():
    unit = {
        "juan_index": 1,
        "unit_title": "第一卷笼中雀 第十章 食牛之气",
    }
    segment = {
        "segment_index": 2,
        "segment_start_time": "第一卷笼中雀 第十章 食牛之气",
        "sentences": [
            "宁姚与陈平安、刘羡阳在泥瓶巷同行。",
        ],
    }
    core_cast = {
        "characters": [
            {"name": "陈平安", "aliases": [], "power": "泥瓶巷", "description": "主角"},
            {"name": "宁姚", "aliases": [], "power": "剑气长城", "description": "少女剑修"},
            {"name": "刘羡阳", "aliases": [], "power": "小镇", "description": "好友"},
        ],
        "locations": [
            {"name": "泥瓶巷", "aliases": [], "type": "街巷", "description": "场景"}
        ],
        "relation_keywords": [{"action": "同行", "keywords": ["同行"]}],
        "event_rules": [],
        "event_type_rules": [{"type": "同行", "keywords": ["同行"]}],
    }

    chunk = build_swordcoming_offline_data.build_segment_chunk(
        unit=unit,
        segment=segment,
        character_config={item["name"]: item for item in core_cast["characters"]},
        location_config={item["name"]: item for item in core_cast["locations"]},
        character_matchers=build_swordcoming_offline_data.build_matchers(core_cast["characters"]),
        location_matchers=build_swordcoming_offline_data.build_matchers(core_cast["locations"]),
        relation_keywords=core_cast["relation_keywords"],
        event_rules=core_cast["event_rules"],
        event_type_rules=core_cast["event_type_rules"],
    )

    assert chunk is not None
    relation_pairs = {(relation.from_roles[0], relation.to_roles[0]) for relation in chunk.relations}
    assert relation_pairs == {("宁姚", "陈平安"), ("宁姚", "刘羡阳"), ("陈平安", "刘羡阳")}


def test_validate_unified_knowledge_flags_placeholder_question_marks(tmp_path):
    path = tmp_path / "unified_knowledge.json"
    path.write_text(
        json.dumps(
            {
                "book_id": "swordcoming",
                "unit_label": "??",
                "roles": {"???": {"canonical_name": "???", "description": "????????"}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    suspicious = validate_unified_knowledge(path)
    assert "$.unit_label" in suspicious
    assert "$.roles.???.canonical_name" in suspicious


def test_entity_resolver_prefers_manual_canonical_role_name():
    resolver = EntityResolver()
    resolver.set_manual_overrides(
        {
            "canonical_role_names": {"宋睦": "宋集薪"},
            "role_primary_powers": {"宋集薪": "大骊"},
        }
    )

    resolver.add_role(
        Role(
            entity_type="person",
            name="宋集薪",
            alias=["宋睦"],
            description="核心角色",
            power="大骊",
            sentence_indexes_in_segment=[0],
            juan_index=1,
            segment_index=1,
        ),
        juan_index=1,
        segment_index=1,
        chunk_index=0,
        source_sentence="宋集薪与陈平安说话。",
    )

    kb = resolver.build_knowledge_base()
    assert "宋集薪" in kb.roles
    assert "宋睦" not in kb.roles


def test_normalize_mined_candidate_filters_non_person_prefix_phrases():
    normalized = build_swordcoming_offline_data.normalize_mined_candidate(
        "小心翼翼",
        blocked_names=set(),
        known_names=set(),
        location_names=set(),
    )
    assert normalized is None

    titled = build_swordcoming_offline_data.normalize_mined_candidate(
        "老秀才",
        blocked_names=set(),
        known_names=set(),
        location_names=set(),
    )
    assert titled == "老秀才"


def test_build_offline_data_generates_utf8_knowledge_base(tmp_path):
    book_path = tmp_path / "swordcoming_book.json"
    core_cast_path = tmp_path / "core_cast.json"
    book_config_path = tmp_path / "book_config.json"
    unit_progress_path = tmp_path / "unit_progress_index.json"
    manual_overrides_path = tmp_path / "manual_overrides.json"
    store_dir = tmp_path / "store"
    kb_output = tmp_path / "unified_knowledge.json"
    writer_output = tmp_path / "writer_insights.json"

    book_path.write_text(
        json.dumps(
            [
                {
                    "juan_index": 1,
                    "unit_title": "第一卷笼中雀 第一章 惊蛰",
                    "segments": [
                        {
                            "segment_index": 1,
                            "segment_start_time": "第一卷笼中雀 第一章 惊蛰",
                            "sentences": [
                                "陈平安在泥瓶巷守夜。",
                                "宋集薪在墙头讥讽陈平安。",
                            ],
                        }
                    ],
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    core_cast_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "characters": [
                    {"name": "陈平安", "aliases": [], "power": "泥瓶巷", "description": "主角"},
                    {"name": "宋集薪", "aliases": [], "power": "大骊", "description": "对照人物"},
                ],
                "locations": [
                    {"name": "泥瓶巷", "aliases": [], "type": "街巷", "description": "开篇场景"}
                ],
                "relation_keywords": [{"action": "讥讽", "keywords": ["讥讽"]}],
                "event_rules": [
                    {
                        "name": "惊蛰守夜",
                        "event_type": "等待",
                        "keywords": ["惊蛰", "守夜", "泥瓶巷", "陈平安"],
                        "min_keywords": 3,
                        "location": "泥瓶巷",
                        "participants": ["陈平安"],
                        "significance": "开篇事件",
                    }
                ],
                "event_type_rules": [{"type": "等待", "keywords": ["守夜"]}],
                "phase_rules": [{"label": "冲突", "keywords": ["讥讽"], "actions": ["讥讽"]}],
                "writer_focus": {
                    "spotlight_role": "陈平安",
                    "priority_characters": ["陈平安", "宋集薪"],
                    "conflict_actions": ["讥讽", "冲突"],
                    "curated_relationships": [
                        {
                            "roles": ["陈平安", "宋集薪"],
                            "kind": "mirror",
                            "title": "陈平安与宋集薪：镜像关系",
                            "focus": "用来校订主角关系线。",
                            "adaptation_value": "适合改编强化。",
                            "manual_beats": [
                                {
                                    "season_name": "第一季",
                                    "phase_label": "镜像",
                                    "summary": "测试人工节拍。",
                                    "event_keywords": ["守夜"],
                                    "location": "泥瓶巷",
                                }
                            ],
                        }
                    ],
                },
                "foreshadowing_patterns": [
                    {
                        "id": "night-watch",
                        "label": "守夜伏线",
                        "focus_roles": ["陈平安"],
                        "motif_keywords": ["守夜"],
                        "clue_keywords": ["守夜"],
                        "payoff_keywords": ["守夜"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    book_config_path.write_text(
        json.dumps(
            {
                "book_id": "swordcoming",
                "title": "剑来",
                "unit_label": "章节",
                "progress_label": "叙事进度",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    unit_progress_path.write_text(
        json.dumps(
            {
                "book_id": "swordcoming",
                "unit_label": "章节",
                "progress_label": "叙事进度",
                "segments": {
                    "1-1": {
                        "unit_index": 1,
                        "segment_index": 1,
                        "progress_index": 1,
                        "progress_label": "第一卷笼中雀 第一章 惊蛰 · 段1",
                    }
                },
                "units": {
                    "1": {
                        "unit_index": 1,
                        "unit_title": "第一卷笼中雀 第一章 惊蛰",
                        "season_name": "第一季",
                        "progress_start": 1,
                        "progress_end": 1,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manual_overrides_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "blocked_aliases": ["先生"],
                "role_aliases": {},
                "role_primary_powers": {"陈平安": "泥瓶巷", "宋集薪": "大骊"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    stats = build_swordcoming_offline_data.build_offline_data(
        book_path=book_path,
        core_cast_path=core_cast_path,
        store_dir=store_dir,
        kb_output=kb_output,
        writer_output=writer_output,
        unit_progress_index_path=unit_progress_path,
        book_config_path=book_config_path,
        manual_overrides_path=manual_overrides_path,
    )

    payload = json.loads(kb_output.read_text(encoding="utf-8"))
    assert stats["roles"] == 2
    assert payload["unit_label"] == "章节"
    assert "陈平安" in payload["roles"]
    assert payload["events"]["惊蛰守夜"]["progress_label"] == "第一卷笼中雀 第一章 惊蛰 · 段1"
    assert validate_unified_knowledge(kb_output) == []

    writer_payload = json.loads(writer_output.read_text(encoding="utf-8"))
    assert writer_payload["spotlight_role_name"] == "陈平安"
    assert writer_payload["summary"]["character_arc_count"] == 2
    assert writer_payload["summary"]["foreshadowing_thread_count"] == 1
    assert writer_payload["summary"]["season_overview_count"] == 1
    assert writer_payload["summary"]["curated_relationship_count"] == 1
    assert writer_payload["season_overviews"][0]["season_name"] == "第一季"
    assert writer_payload["curated_relationships"][0]["title"] == "陈平安与宋集薪：镜像关系"
    assert writer_payload["curated_relationships"][0]["manual_beats"][0]["phase_label"] == "镜像"


def test_build_offline_data_includes_curated_extra_seed_characters(tmp_path):
    book_path = tmp_path / "book.json"
    core_cast_path = tmp_path / "core_cast.json"
    book_config_path = tmp_path / "book_config.json"
    unit_progress_path = tmp_path / "unit_progress_index.json"
    manual_overrides_path = tmp_path / "manual_overrides.json"
    store_dir = tmp_path / "store"
    kb_output = tmp_path / "unified_knowledge.json"
    writer_output = tmp_path / "writer_insights.json"

    book_path.write_text(
        json.dumps(
            [
                {
                    "juan_index": 1,
                    "unit_title": "第一卷 笼中雀 第一章 惊蛰",
                    "segments": [
                        {
                            "segment_index": 1,
                            "segment_start_time": "第一卷 笼中雀 第一章 惊蛰",
                            "sentences": [
                                "陈平安在泥瓶巷守夜。",
                                "陆台问了陈平安一句。",
                            ],
                        }
                    ],
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    core_cast_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "characters": [
                    {"name": "陈平安", "aliases": [], "power": "泥瓶巷", "description": "主角"},
                ],
                "locations": [
                    {"name": "泥瓶巷", "aliases": [], "type": "街巷", "description": "场景"}
                ],
                "relation_keywords": [{"action": "提问", "keywords": ["问了"]}],
                "event_rules": [],
                "event_type_rules": [{"type": "剧情推进", "keywords": ["守夜", "问了"]}],
                "phase_rules": [],
                "writer_focus": {
                    "spotlight_role": "陈平安",
                    "priority_characters": ["陈平安"],
                    "conflict_actions": ["提问"],
                    "curated_relationships": [],
                },
                "foreshadowing_patterns": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    book_config_path.write_text(
        json.dumps(
            {
                "book_id": "swordcoming",
                "title": "剑来",
                "unit_label": "章节",
                "progress_label": "叙事进度",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    unit_progress_path.write_text(
        json.dumps(
            {
                "book_id": "swordcoming",
                "unit_label": "章节",
                "progress_label": "叙事进度",
                "segments": {
                    "1-1": {
                        "unit_index": 1,
                        "segment_index": 1,
                        "progress_index": 1,
                        "progress_label": "第一卷 笼中雀 第一章 惊蛰 · 段1",
                    }
                },
                "units": {
                    "1": {
                        "unit_index": 1,
                        "unit_title": "第一卷 笼中雀 第一章 惊蛰",
                        "season_name": "第一季",
                        "progress_start": 1,
                        "progress_end": 1,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manual_overrides_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "blocked_aliases": ["先生"],
                "role_aliases": {},
                "role_primary_powers": {"陈平安": "泥瓶巷"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    stats = build_swordcoming_offline_data.build_offline_data(
        book_path=book_path,
        core_cast_path=core_cast_path,
        store_dir=store_dir,
        kb_output=kb_output,
        writer_output=writer_output,
        unit_progress_index_path=unit_progress_path,
        book_config_path=book_config_path,
        manual_overrides_path=manual_overrides_path,
        sync_output=False,
    )

    payload = json.loads(kb_output.read_text(encoding="utf-8"))
    assert stats["curated_extra_seed_roles"] >= 1
    assert "陆台" in payload["roles"]


def test_build_writer_insights_payload_creates_arc_conflict_and_foreshadowing():
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1, "2-1": 3},
        {"1-1": "第一季 · 段1", "2-1": "第二季 · 段1"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷", "宋集薪": "大骊"}})

    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷", sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1,
        segment_index=1,
        chunk_index=0,
        source_sentence="陈平安守夜。",
    )
    resolver.add_role(
        Role(name="宋集薪", alias=[], description="对照角色", power="大骊", sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1,
        segment_index=1,
        chunk_index=0,
        source_sentence="宋集薪讥讽陈平安。",
    )

    resolver.add_event(
        Event(
            name="墙头对话",
            time=None,
            location="泥瓶巷",
            participants=["陈平安", "宋集薪"],
            description="宋集薪在泥瓶巷讥讽陈平安。",
            significance="建立二人的冲突关系。",
            juan_index=1,
            segment_index=1,
        ),
        juan_index=1,
        segment_index=1,
    )
    resolver.add_event(
        Event(
            name="落魄山再会",
            time=None,
            location="落魄山",
            participants=["陈平安", "宋集薪"],
            description="陈平安与宋集薪在落魄山再次会面。",
            significance="延续前段埋下的关系暗线。",
            juan_index=2,
            segment_index=1,
        ),
        juan_index=2,
        segment_index=1,
    )
    resolver.add_relation(
        Action(
            time=None,
            from_roles=["宋集薪"],
            to_roles=["陈平安"],
            action="讥讽",
            context="宋集薪在墙头讥讽陈平安。",
            event_name="墙头对话",
            location="泥瓶巷",
            juan_index=1,
            segment_index=1,
        )
    )

    kb = resolver.build_knowledge_base()
    payload = build_writer_insights_payload(
        kb=kb,
        unit_progress_index={
            "units": {
                "1": {
                    "unit_index": 1,
                    "unit_title": "第一章 惊蛰",
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 1,
                },
                "2": {
                    "unit_index": 2,
                    "unit_title": "第二章 回转",
                    "season_name": "第二季",
                    "progress_start": 3,
                    "progress_end": 3,
                },
            }
        },
        core_cast={
            "event_type_rules": [{"type": "冲突", "keywords": ["讥讽"]}],
            "phase_rules": [{"label": "冲突", "keywords": ["讥讽"], "actions": ["讥讽"]}],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "priority_characters": ["陈平安"],
                "conflict_actions": ["讥讽", "冲突"],
                "priority_pairs": [{"roles": ["陈平安", "宋集薪"], "weight": 10}],
                "curated_relationships": [
                    {
                        "roles": ["陈平安", "宋集薪"],
                        "kind": "mirror",
                        "title": "陈平安与宋集薪：镜像关系",
                        "focus": "测试人工校订关系线。",
                        "adaptation_value": "测试改编价值。",
                        "manual_beats": [
                            {
                                "season_name": "第一季",
                                "phase_label": "镜像",
                                "summary": "测试人工节拍。",
                                "event_keywords": ["墙头对话"],
                                "location": "泥瓶巷",
                            }
                        ],
                    }
                ],
            },
            "foreshadowing_patterns": [
                {
                    "id": "pair-thread",
                    "label": "陈平安与宋集薪暗线",
                    "focus_roles": ["陈平安", "宋集薪"],
                    "motif_keywords": ["陈平安", "宋集薪"],
                    "clue_keywords": ["墙头对话"],
                    "payoff_keywords": ["落魄山再会"],
                }
            ],
        },
    )

    assert payload["spotlight_role_name"] == "陈平安"
    assert payload["summary"]["character_arc_count"] == 1
    assert payload["summary"]["conflict_chain_count"] == 1
    assert payload["summary"]["foreshadowing_thread_count"] == 1
    assert payload["summary"]["season_overview_count"] == 2
    assert payload["summary"]["curated_relationship_count"] == 1
    assert len(payload["season_overviews"][0]["story_beats"]) == 3
    assert len(payload["season_overviews"][0]["must_keep_scenes"]) == 3
    assert payload["season_overviews"][0]["must_keep_scenes"][0]["label"]
    assert payload["character_arcs"][0]["role_name"] == "陈平安"
    assert payload["character_arcs"][0]["spotlight"] is True
    assert payload["season_overviews"][0]["season_name"] == "第一季"
    assert payload["curated_relationships"][0]["title"] == "陈平安与宋集薪：镜像关系"
    assert payload["curated_relationships"][0]["manual_beats"][0]["summary"] == "测试人工节拍。"
