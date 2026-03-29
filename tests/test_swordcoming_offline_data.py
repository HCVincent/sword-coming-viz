import json

from entity_resolution import EntityResolver
from model.action import Action
from model.event import Event
from model.role import Role
from scripts import build_swordcoming_offline_data
from scripts.build_chapter_synopses import build_chapter_synopses
from scripts.build_key_events_index import build_key_events_index
from scripts.build_season_overview_audit import build_audit
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
    assert titled is None


def test_normalize_mined_candidate_filters_pseudo_role_fragments():
    normalized = build_swordcoming_offline_data.normalize_mined_candidate(
        "管狮子",
        blocked_names=set(),
        known_names=set(),
        location_names=set(),
        sentence_text="陈平安，只管狮子大开口，条件怎么过分怎么开。",
        source="dialogue",
        match_start=4,
        match_end=7,
    )
    assert normalized is None

    normalized = build_swordcoming_offline_data.normalize_mined_candidate(
        "后笑眯眯",
        blocked_names=set(),
        known_names=set(),
        location_names=set(),
    )
    assert normalized is None


def test_build_offline_data_generates_utf8_knowledge_base(tmp_path):
    book_path = tmp_path / "swordcoming_book.json"
    core_cast_path = tmp_path / "core_cast.json"
    book_config_path = tmp_path / "book_config.json"
    unit_progress_path = tmp_path / "unit_progress_index.json"
    manual_overrides_path = tmp_path / "manual_overrides.json"
    store_dir = tmp_path / "store"
    kb_output = tmp_path / "unified_knowledge.json"
    writer_output = tmp_path / "writer_insights.json"
    synopses_output = tmp_path / "chapter_synopses.json"
    key_events_output = tmp_path / "key_events_index.json"

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
        synopses_output=synopses_output,
        key_events_output=key_events_output,
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

    # chapter_synopses.json must be generated with valid structure
    assert synopses_output.exists(), "chapter_synopses.json was not generated"
    synopses_data = json.loads(synopses_output.read_text(encoding="utf-8"))
    assert synopses_data["version"] == "chapter-synopses-v1"
    assert synopses_data["chapter_count"] >= 1
    assert len(synopses_data["chapters"]) == synopses_data["chapter_count"]

    # key_events_index.json must be generated with valid structure
    assert key_events_output.exists(), "key_events_index.json was not generated"
    key_events_data = json.loads(key_events_output.read_text(encoding="utf-8"))
    assert key_events_data["version"] == "key-events-index-v1"
    assert isinstance(key_events_data["chapters"], list)

    # Stats should include new outputs
    assert stats["chapter_synopses_count"] >= 1
    assert isinstance(stats["key_events_chapters"], int)


def test_validate_unified_knowledge_flags_pseudo_role_names(tmp_path):
    path = tmp_path / "unified_knowledge.json"
    path.write_text(
        json.dumps(
            {
                "book_id": "swordcoming",
                "roles": {
                    "管狮子": {
                        "canonical_name": "管狮子",
                        "description": "伪角色",
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    suspicious = validate_unified_knowledge(path)
    assert any("管狮子" in item for item in suspicious)


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


def test_build_writer_insights_payload_uses_season_focus_roles_and_relationships():
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1, "2-1": 2},
        {"1-1": "第一季 · 段1", "2-1": "第二季 · 段1"},
    )
    resolver.set_manual_overrides(
        {
            "role_primary_powers": {
                "陈平安": "泥瓶巷",
                "阿良": "剑修",
                "齐静春": "山崖书院",
            }
        }
    )

    for role_name, power, juan_index in [
        ("陈平安", "泥瓶巷", 1),
        ("陈平安", "泥瓶巷", 2),
        ("阿良", "剑修", 2),
        ("齐静春", "山崖书院", 1),
    ]:
        resolver.add_role(
            Role(
                name=role_name,
                alias=[],
                description=f"{role_name}描述",
                power=power,
                sentence_indexes_in_segment=[0],
                juan_index=juan_index,
                segment_index=1,
            ),
            juan_index=juan_index,
            segment_index=1,
            chunk_index=0,
            source_sentence=f"{role_name}出现。",
        )

    resolver.add_event(
        Event(
            name="阿良现身",
            time=None,
            location="小镇",
            participants=["陈平安", "阿良"],
            description="阿良在第二季进入陈平安主线。",
            significance="打开第二季外部世界入口。",
            juan_index=2,
            segment_index=1,
        ),
        juan_index=2,
        segment_index=1,
    )
    resolver.add_event(
        Event(
            name="齐静春点拨",
            time=None,
            location="山崖书院",
            participants=["陈平安", "齐静春"],
            description="齐静春在第一季点拨陈平安。",
            significance="提供主线价值奠基。",
            juan_index=1,
            segment_index=1,
        ),
        juan_index=1,
        segment_index=1,
    )
    resolver.add_relation(
        Action(
            time=None,
            from_roles=["阿良"],
            to_roles=["陈平安"],
            action="指引",
            context="阿良带陈平安看到更大的天地。",
            event_name="阿良现身",
            location="小镇",
            juan_index=2,
            segment_index=1,
        )
    )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
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
                    "unit_title": "第二章 山水",
                    "season_name": "第二季",
                    "progress_start": 2,
                    "progress_end": 2,
                },
            }
        },
        core_cast={
            "event_type_rules": [{"type": "指引", "keywords": ["阿良", "点拨", "指引"]}],
            "phase_rules": [{"label": "引路", "keywords": ["阿良", "指引"], "actions": ["指引"]}],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "season_focus": {
                    "第二季": {
                        "priority_roles": ["陈平安", "阿良", "齐静春"],
                    }
                },
                "priority_characters": ["陈平安", "阿良", "齐静春"],
                "conflict_actions": ["指引"],
                "priority_pairs": [{"roles": ["陈平安", "阿良"], "weight": 10}],
                "curated_relationships": [
                    {
                        "roles": ["陈平安", "阿良"],
                        "kind": "guide",
                        "title": "陈平安与阿良：小镇之外的世界入口",
                        "focus": "第二季主线外扩。",
                        "adaptation_value": "适合承担第二季外部世界开启功能。",
                        "manual_beats": [
                            {
                                "season_name": "第二季",
                                "phase_label": "引路",
                                "summary": "阿良把陈平安带到更大的世界门口。",
                                "event_keywords": ["阿良现身"],
                                "location": "小镇",
                            }
                        ],
                    },
                    {
                        "roles": ["陈平安", "齐静春"],
                        "kind": "mentor",
                        "title": "陈平安与齐静春：文脉引路与价值奠基",
                        "focus": "第一季价值奠基。",
                        "adaptation_value": "保留主角价值来源。",
                        "manual_beats": [
                            {
                                "season_name": "第一季",
                                "phase_label": "点拨",
                                "summary": "齐静春为陈平安托底。",
                                "event_keywords": ["齐静春点拨"],
                                "location": "山崖书院",
                            }
                        ],
                    },
                ],
            },
            "foreshadowing_patterns": [],
        },
    )

    second_overview = next(item for item in payload["season_overviews"] if item["season_name"] == "第二季")
    assert second_overview["priority_roles"]
    assert "阿良" in [role["role_name"] for role in second_overview["priority_roles"]]
    assert "陈平安与阿良：小镇之外的世界入口" in [
        relation["title"] for relation in second_overview["priority_relationships"]
    ]


def test_season_overview_evidence_gates_priority_roles():
    """Season_focus roles with zero chapter appearances are dropped."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1},
        {"1-1": "第一季 · 段1"},
    )
    resolver.set_manual_overrides(
        {"role_primary_powers": {"陈平安": "泥瓶巷", "宋集薪": "大骊"}}
    )

    # Only add 陈平安 as a role — 宋集薪 is NOT present in chapter data
    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0, source_sentence="陈平安。",
    )
    resolver.add_event(
        Event(name="守夜", time=None, location="泥瓶巷",
              participants=["陈平安"], description="陈平安守夜。",
              significance="开篇。", juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                "1": {
                    "unit_index": 1,
                    "unit_title": "第一章 惊蛰",
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 1,
                },
            }
        },
        core_cast={
            "event_type_rules": [],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                # season_focus lists 宋集薪, but he has no chapter appearances
                "season_focus": {
                    "第一季": {
                        "priority_roles": ["陈平安", "宋集薪"],
                    }
                },
                "priority_characters": ["陈平安"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [],
            },
            "foreshadowing_patterns": [],
        },
    )

    overview = payload["season_overviews"][0]
    role_names = [r["role_name"] for r in overview["priority_roles"]]
    assert "陈平安" in role_names, "陈平安 should be kept (has chapter data)"
    assert "宋集薪" not in role_names, "宋集薪 should be dropped (no chapter data)"
    # data_provenance should record the drop
    assert "宋集薪" in overview["data_provenance"]["priority_roles_dropped"]
    assert "evidence_gated" in overview["data_provenance"]["priority_roles_source"]


def test_season_overview_story_beats_have_unique_names():
    """Each season's story beats should have distinct event names."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1, "1-2": 2, "1-3": 3},
        {"1-1": "第一季 · 段1", "1-2": "第一季 · 段2", "1-3": "第一季 · 段3"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷"}})

    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0, source_sentence="陈平安。",
    )
    # Create multiple events spread across the season progress range
    for i, (name, loc, prog) in enumerate([
        ("惊蛰守夜", "泥瓶巷", 1),
        ("墙头对话", "泥瓶巷", 2),
        ("出城", "城门", 3),
    ], start=1):
        resolver.add_event(
            Event(name=name, time=None, location=loc,
                  participants=["陈平安"], description=f"{name}描述",
                  significance=f"{name}意义", juan_index=i, segment_index=1),
            juan_index=i, segment_index=1,
        )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                str(i): {
                    "unit_index": i,
                    "unit_title": f"第{i}章",
                    "season_name": "第一季",
                    "progress_start": i,
                    "progress_end": i,
                }
                for i in range(1, 4)
            }
        },
        core_cast={
            "event_type_rules": [],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "priority_characters": ["陈平安"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [],
            },
            "foreshadowing_patterns": [],
        },
    )

    for overview in payload["season_overviews"]:
        beats = overview.get("story_beats", [])
        beat_names = [
            b["event"]["name"]
            for b in beats
            if b.get("event") and b["event"].get("name")
        ]
        assert len(beat_names) == len(set(beat_names)), (
            f"Season {overview['season_name']} has duplicate beat names: {beat_names}"
        )


def test_event_refs_contain_source_unit_titles():
    """Every event ref in season overviews should carry source_unit_titles."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1},
        {"1-1": "第一季 · 段1"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷"}})

    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0, source_sentence="陈平安。",
    )
    resolver.add_event(
        Event(name="惊蛰守夜", time=None, location="泥瓶巷",
              participants=["陈平安"], description="陈平安守夜。",
              significance="开篇。", juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                "1": {
                    "unit_index": 1,
                    "unit_title": "第一章 惊蛰",
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 1,
                },
            }
        },
        core_cast={
            "event_type_rules": [],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "priority_characters": ["陈平安"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [],
            },
            "foreshadowing_patterns": [],
        },
    )

    # Check anchor events carry source_unit_titles
    for overview in payload["season_overviews"]:
        for ev in overview.get("anchor_events", []):
            assert "source_unit_titles" in ev, (
                f"Anchor event {ev.get('name')} missing source_unit_titles"
            )
        for beat in overview.get("story_beats", []):
            ev = beat.get("event")
            if ev:
                assert "source_unit_titles" in ev, (
                    f"Story beat event {ev.get('name')} missing source_unit_titles"
                )


def test_data_provenance_present_on_every_season_overview():
    """Every season overview must include a data_provenance dict."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1},
        {"1-1": "第一季 · 段1"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷"}})

    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0, source_sentence="陈平安。",
    )
    resolver.add_event(
        Event(name="守夜", time=None, location="泥瓶巷",
              participants=["陈平安"], description="陈平安守夜。",
              significance="开篇。", juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                "1": {
                    "unit_index": 1,
                    "unit_title": "第一章 惊蛰",
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 1,
                },
            }
        },
        core_cast={
            "event_type_rules": [],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "priority_characters": ["陈平安"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [],
            },
            "foreshadowing_patterns": [],
        },
    )

    for overview in payload["season_overviews"]:
        prov = overview.get("data_provenance")
        assert prov is not None, f"Missing data_provenance on {overview['season_name']}"
        assert "priority_roles_source" in prov
        assert "priority_roles_dropped" in prov
        assert isinstance(prov["priority_roles_dropped"], list)
        assert "priority_relationships_source" in prov
        assert "note" in prov


def test_priority_relationships_evidence_gate_both_participants():
    """Relationships where a participant has no chapter appearances are excluded."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1},
        {"1-1": "第一季 · 段1"},
    )
    resolver.set_manual_overrides(
        {"role_primary_powers": {"陈平安": "泥瓶巷", "阿良": "剑修"}}
    )

    # Only 陈平安 has chapter data — 阿良 does NOT
    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0, source_sentence="陈平安。",
    )
    resolver.add_event(
        Event(name="守夜", time=None, location="泥瓶巷",
              participants=["陈平安"], description="陈平安守夜。",
              significance="开篇。", juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                "1": {
                    "unit_index": 1,
                    "unit_title": "第一章 惊蛰",
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 1,
                },
            }
        },
        core_cast={
            "event_type_rules": [],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "season_focus": {
                    "第一季": {
                        "priority_roles": ["陈平安"],
                        "priority_relationship_pairs": [["陈平安", "阿良"]],
                    }
                },
                "priority_characters": ["陈平安"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [
                    {
                        "roles": ["陈平安", "阿良"],
                        "kind": "guide",
                        "title": "陈平安与阿良：引路",
                        "focus": "引路。",
                        "adaptation_value": "重要。",
                        "manual_beats": [
                            {
                                "season_name": "第一季",
                                "phase_label": "引路",
                                "summary": "阿良引路。",
                                "event_keywords": ["守夜"],
                                "location": "泥瓶巷",
                            }
                        ],
                    },
                ],
            },
            "foreshadowing_patterns": [],
        },
    )

    overview = payload["season_overviews"][0]
    rel_titles = [r["title"] for r in overview["priority_relationships"]]
    # 阿良 has no chapter appearances → the relationship should be excluded
    assert "陈平安与阿良：引路" not in rel_titles, (
        "Relationship with a participant lacking chapter evidence should be excluded"
    )
    assert "evidence_gated" in overview["data_provenance"]["priority_relationships_source"]


def test_build_audit_includes_template_params_audit():
    """build_audit output should contain template_params_audit per season."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1},
        {"1-1": "第一季 · 段1"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷"}})

    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0, source_sentence="陈平安。",
    )
    resolver.add_event(
        Event(name="守夜", time=None, location="泥瓶巷",
              participants=["陈平安"], description="陈平安守夜。",
              significance="开篇。", juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )

    payload = build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                "1": {
                    "unit_index": 1,
                    "unit_title": "第一章 惊蛰",
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 1,
                },
            }
        },
        core_cast={
            "event_type_rules": [],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "priority_characters": ["陈平安"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [],
            },
            "foreshadowing_patterns": [],
        },
    )

    upi = {
        "units": {
            "1": {
                "unit_index": 1,
                "unit_title": "第一章 惊蛰",
                "season_name": "第一季",
                "progress_start": 1,
                "progress_end": 1,
            },
        }
    }
    audit = build_audit(payload, upi)

    assert audit.get("all_seasons_template_names_backed") is True
    for sa in audit["season_audits"]:
        tpa = sa.get("template_params_audit")
        assert tpa is not None, f"Missing template_params_audit on {sa['season_name']}"
        assert tpa["all_template_names_backed"] is True
        assert isinstance(tpa["unbacked_summary_names"], list)
        assert isinstance(tpa["unbacked_spotlight_names"], list)


def test_build_audit_detects_unbacked_relationship_participant():
    """Audit should flag when a relationship participant is not in season top_roles."""
    # Simulate writer_insights data with a relationship where one participant
    # is not in top_roles or priority_roles.
    wi = {
        "season_overviews": [
            {
                "season_name": "第一季",
                "unit_range": [1, 5],
                "summary": "测试摘要",
                "spotlight_summary": None,
                "adaptation_hooks": [],
                "story_beats": [],
                "top_roles": [
                    {"role_name": "陈平安", "unit_appearance_count": 3, "event_count": 2},
                ],
                "priority_roles": [
                    {"role_name": "陈平安", "unit_appearance_count": 3, "event_count": 2},
                ],
                "priority_relationships": [
                    {
                        "title": "陈平安与鬼魅：对峙",
                        "source_role_name": "陈平安",
                        "target_role_name": "鬼魅",
                    },
                ],
                "anchor_events": [],
                "must_keep_scenes": [],
                "data_provenance": {
                    "priority_roles_source": "density_ranking",
                    "priority_roles_dropped": [],
                    "priority_relationships_source": "score_ranking",
                    "note": "test",
                },
            }
        ]
    }
    upi = {
        "units": {
            "1": {"unit_index": 1, "season_name": "第一季", "progress_start": 1, "progress_end": 1},
        }
    }
    audit = build_audit(wi, upi)
    sa = audit["season_audits"][0]
    rel_audit = sa["priority_relationships_audit"]
    assert len(rel_audit) == 1
    assert rel_audit[0]["source_in_season"] is True
    assert rel_audit[0]["target_in_season"] is False
    assert rel_audit[0]["both_in_season"] is False
    assert sa["priority_relationships_both_in_season"] is False


# ---------------------------------------------------------------------------
# Chapter Synopses tests
# ---------------------------------------------------------------------------

def _make_synopsis_kb_and_upi():
    """Helper: builds a small KB + UPI suitable for synopsis / key-events tests."""
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1, "2-1": 3},
        {"1-1": "第一季 · 段1", "2-1": "第一季 · 段2"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷"}})

    resolver.add_role(
        Role(name="陈平安", alias=[], description="主角", power="泥瓶巷",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0,
        source_sentence="陈平安守夜。",
    )
    resolver.add_role(
        Role(name="宋集薪", alias=[], description="对照", power="大骊",
             sentence_indexes_in_segment=[0], juan_index=1, segment_index=1),
        juan_index=1, segment_index=1, chunk_index=0,
        source_sentence="宋集薪讥讽。",
    )
    resolver.add_role(
        Role(name="宁姚", alias=[], description="剑修", power="剑气长城",
             sentence_indexes_in_segment=[0], juan_index=2, segment_index=1),
        juan_index=2, segment_index=1, chunk_index=0,
        source_sentence="宁姚赠剑。",
    )

    resolver.add_event(
        Event(name="墙头对话", time=None, location="泥瓶巷",
              participants=["陈平安", "宋集薪"],
              description="宋集薪在墙头讥讽陈平安。",
              significance="建立冲突关系。",
              juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )
    resolver.add_event(
        Event(name="泥瓶巷守夜", time=None, location="泥瓶巷",
              participants=["陈平安"],
              description="陈平安在泥瓶巷独自守夜。",
              significance="开篇独白。",
              juan_index=1, segment_index=1),
        juan_index=1, segment_index=1,
    )
    resolver.add_event(
        Event(name="少女赠剑", time=None, location="小镇",
              participants=["陈平安", "宁姚"],
              description="宁姚将飞剑赠予陈平安。",
              significance="关键转折。",
              juan_index=2, segment_index=1),
        juan_index=2, segment_index=1,
    )

    kb = resolver.build_knowledge_base()
    upi = {
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
                "unit_title": "第二章 飞剑",
                "season_name": "第一季",
                "progress_start": 3,
                "progress_end": 3,
            },
        }
    }
    return kb, upi


def test_build_chapter_synopses_produces_one_entry_per_unit():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    assert len(synopses) == 2
    assert synopses[0]["unit_index"] == 1
    assert synopses[1]["unit_index"] == 2


def test_chapter_synopsis_contains_expected_fields():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    for entry in synopses:
        assert "unit_index" in entry
        assert "unit_title" in entry
        assert "season_name" in entry
        assert "event_count" in entry
        assert "active_characters" in entry
        assert "locations" in entry
        assert "key_developments" in entry
        assert "synopsis" in entry
        assert "narrative_function" in entry


def test_chapter_synopsis_event_count_matches_kb_events():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    ch1 = synopses[0]
    # Chapter 1 has 2 events (墙头对话, 泥瓶巷守夜)
    assert ch1["event_count"] == 2
    ch2 = synopses[1]
    # Chapter 2 has 1 event (少女赠剑)
    assert ch2["event_count"] == 1


def test_chapter_synopsis_active_characters_includes_participants():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    ch1_chars = synopses[0]["active_characters"]
    assert "陈平安" in ch1_chars
    assert "宋集薪" in ch1_chars
    ch2_chars = synopses[1]["active_characters"]
    assert "陈平安" in ch2_chars
    assert "宁姚" in ch2_chars


def test_chapter_synopsis_key_developments_ordered_by_score():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(
        kb=kb,
        unit_progress_index=upi,
        event_type_rules=[{"type": "冲突", "keywords": ["讥讽"]}],
    )
    ch1_devs = synopses[0]["key_developments"]
    # 墙头对话 should score higher (冲突 type + 2 participants) than 泥瓶巷守夜
    assert len(ch1_devs) >= 1
    assert "墙头对话" in ch1_devs[0]


def test_chapter_synopsis_narrative_function_is_valid_label():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    valid_labels = {"开篇", "过渡", "高潮", "收束"}
    for entry in synopses:
        assert entry["narrative_function"] in valid_labels, (
            f"unit {entry['unit_index']} got unexpected label: {entry['narrative_function']}"
        )


def test_chapter_synopsis_locations_populated():
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    ch1_locs = synopses[0]["locations"]
    assert "泥瓶巷" in ch1_locs


# ---------------------------------------------------------------------------
# Key Events Index tests
# ---------------------------------------------------------------------------

def test_build_key_events_index_produces_chapter_records():
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=0)
    assert len(chapters) >= 1
    for ch in chapters:
        assert "unit_index" in ch
        assert "key_events" in ch
        assert len(ch["key_events"]) >= 1


def test_key_events_have_importance_tiers():
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=0)
    valid_tiers = {"critical", "major", "notable"}
    for ch in chapters:
        for ev in ch["key_events"]:
            assert ev["importance"] in valid_tiers


def test_key_events_deduplicates_by_name():
    """Events with the same name in a chapter should appear only once (highest score)."""
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=0)
    for ch in chapters:
        names = [ev["name"] for ev in ch["key_events"]]
        assert len(names) == len(set(names)), f"Duplicate event names in unit {ch['unit_index']}"


def test_key_events_respects_min_score():
    kb, upi = _make_synopsis_kb_and_upi()
    # With a very high min_score, nothing should qualify
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=100)
    assert len(chapters) == 0


def test_key_events_respects_max_events_per_chapter():
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(
        kb=kb, unit_progress_index=upi, min_score=0, max_events_per_chapter=1,
    )
    for ch in chapters:
        assert len(ch["key_events"]) <= 1


def test_key_events_sorted_by_score_descending():
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=0)
    for ch in chapters:
        scores = [ev["score"] for ev in ch["key_events"]]
        assert scores == sorted(scores, reverse=True)


def test_chapter_synopsis_text_contains_no_abnormal_characters():
    """Synopsis and key_developments must use only standard Chinese punctuation."""
    import re
    ABNORMAL_CHARS = re.compile(r"[\u3129\u02d9\ufe5d\ufe5e\uff62\uff63\u2502\u2500\u2014{2,}]")
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(
        kb=kb,
        unit_progress_index=upi,
        event_type_rules=[{"type": "冲突", "keywords": ["讥讽"]}],
    )
    for entry in synopses:
        assert not ABNORMAL_CHARS.search(entry["synopsis"]), (
            f"unit {entry['unit_index']} synopsis contains abnormal characters: {entry['synopsis']!r}"
        )
        for dev in entry["key_developments"]:
            assert not ABNORMAL_CHARS.search(dev), (
                f"unit {entry['unit_index']} key_development contains abnormal characters: {dev!r}"
            )


def test_key_events_use_involved_characters_field():
    """Key events should have involved_characters (not affects_arcs)."""
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=0)
    for ch in chapters:
        for ev in ch["key_events"]:
            assert "involved_characters" in ev, f"Missing involved_characters on {ev['name']}"
            assert "affects_arcs" not in ev, f"Stale affects_arcs field found on {ev['name']}"
            assert ev["involved_characters"] == ev["participants"]


# ---------------------------------------------------------------------------
# Cross-season dedup & frequency penalty tests
# ---------------------------------------------------------------------------

def _make_cross_season_payload(*, duplicate_names: bool = True):
    """Build a payload with 2 seasons where the same event name occurs in both.

    When *duplicate_names* is True, both seasons contain events named "墙头对话"
    (simulating the over-firing rule problem).  The pipeline should still produce
    distinct beat/anchor names across seasons thanks to the cross-season dedup.
    """
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id="swordcoming", unit_label="章节", progress_label="叙事进度")
    resolver.set_segment_progress_index(
        {"1-1": 1, "1-2": 2, "2-1": 3, "2-2": 4},
        {"1-1": "第一季 · 段1", "1-2": "第一季 · 段2", "2-1": "第二季 · 段1", "2-2": "第二季 · 段2"},
    )
    resolver.set_manual_overrides({"role_primary_powers": {"陈平安": "泥瓶巷", "宋集薪": "大骊", "宁姚": "剑气长城"}})

    for rn, pw, juans in [
        ("陈平安", "泥瓶巷", [1, 2, 3, 4]),
        ("宋集薪", "大骊", [1, 2]),
        ("宁姚", "剑气长城", [3, 4]),
    ]:
        for j in juans:
            resolver.add_role(
                Role(name=rn, alias=[], description="", power=pw,
                     sentence_indexes_in_segment=[0], juan_index=j, segment_index=1),
                juan_index=j, segment_index=1, chunk_index=0, source_sentence=f"{rn}。",
            )

    # Season 1 events (units 1-2)
    for name, loc, juan in [
        ("墙头对话", "泥瓶巷", 1),
        ("惊蛰守夜", "泥瓶巷", 2),
    ]:
        resolver.add_event(
            Event(name=name, time=None, location=loc,
                  participants=["陈平安", "宋集薪"], description=f"{name}。",
                  significance=f"{name}意义。", juan_index=juan, segment_index=1),
            juan_index=juan, segment_index=1,
        )

    # Season 2 events (units 3-4)
    s2_events = [
        ("宁姚再会", "落魄山", 3),
        ("练剑", "落魄山", 4),
        ("落魄山起势", "落魄山", 3),
        ("崔东山现身", "落魄山", 4),
    ]
    if duplicate_names:
        # Insert a "墙头对话" that fires in season 2 too (the root-cause bug)
        s2_events.insert(0, ("墙头对话", "泥瓶巷", 3))
    for name, loc, juan in s2_events:
        resolver.add_event(
            Event(name=name, time=None, location=loc,
                  participants=["陈平安", "宁姚"], description=f"{name}。",
                  significance=f"{name}意义。", juan_index=juan, segment_index=1),
            juan_index=juan, segment_index=1,
        )

    return build_writer_insights_payload(
        kb=resolver.build_knowledge_base(),
        unit_progress_index={
            "units": {
                str(i): {
                    "unit_index": i,
                    "unit_title": f"第{i}章",
                    "season_name": "第一季" if i <= 2 else "第二季",
                    "progress_start": i,
                    "progress_end": i,
                }
                for i in range(1, 5)
            }
        },
        core_cast={
            "event_type_rules": [{"type": "对话", "keywords": ["对话"]}],
            "phase_rules": [],
            "writer_focus": {
                "spotlight_role": "陈平安",
                "priority_characters": ["陈平安", "宋集薪", "宁姚"],
                "conflict_actions": [],
                "priority_pairs": [],
                "curated_relationships": [],
            },
            "foreshadowing_patterns": [],
        },
    )


def test_cross_season_story_beats_have_distinct_names():
    """When the same event name exists in both seasons, cross-season dedup
    should ensure story beats pick different names per season."""
    payload = _make_cross_season_payload(duplicate_names=True)
    all_beat_names: list[str] = []
    for overview in payload["season_overviews"]:
        for beat in overview.get("story_beats", []):
            ev = beat.get("event")
            if ev and ev.get("name"):
                all_beat_names.append(ev["name"])
    # There should be no name that appears in both seasons' beats
    season1_beats = set()
    season2_beats = set()
    for overview in payload["season_overviews"]:
        names = {
            beat["event"]["name"]
            for beat in overview.get("story_beats", [])
            if beat.get("event") and beat["event"].get("name")
        }
        if overview["season_name"] == "第一季":
            season1_beats = names
        else:
            season2_beats = names
    overlap = season1_beats & season2_beats
    assert not overlap, f"Story beats share names across seasons: {overlap}"


def test_cross_season_anchor_events_have_distinct_names():
    """Anchor events should also be deduplicated across seasons."""
    payload = _make_cross_season_payload(duplicate_names=True)
    season1_anchors = set()
    season2_anchors = set()
    for overview in payload["season_overviews"]:
        names = {a["name"] for a in overview.get("anchor_events", []) if a.get("name")}
        if overview["season_name"] == "第一季":
            season1_anchors = names
        else:
            season2_anchors = names
    overlap = season1_anchors & season2_anchors
    assert not overlap, f"Anchor events share names across seasons: {overlap}"


def test_frequency_penalty_demotes_high_frequency_event_names():
    """Events whose name appears in many chapters should score lower than
    events with unique names, all else being equal."""
    from scripts.build_swordcoming_writer_insights import focused_event_score

    base_ref = {
        "event_id": "unique-event@1",
        "name": "独特事件",
        "event_type": "冲突",
        "participants": ["陈平安", "宋集薪"],
        "location": "泥瓶巷",
        "significance": "重要。",
    }
    common_ref = {
        **base_ref,
        "event_id": "common-event@99",
        "name": "墙头对话",
    }
    writer_focus = {
        "spotlight_role": "陈平安",
        "priority_characters": ["陈平安"],
    }
    counts = {"墙头对话": 30, "独特事件": 1}

    score_unique = focused_event_score(
        base_ref,
        writer_focus=writer_focus,
        priority_pair_scores={},
        spotlight_role="陈平安",
        name_occurrence_counts=counts,
    )
    score_common = focused_event_score(
        common_ref,
        writer_focus=writer_focus,
        priority_pair_scores={},
        spotlight_role="陈平安",
        name_occurrence_counts=counts,
    )
    assert score_unique > score_common, (
        f"Unique event ({score_unique}) should score higher than common event ({score_common})"
    )


def test_audit_detects_cross_season_beat_overlap():
    """The audit should flag when story beat names overlap across seasons."""
    # Construct a minimal writer_insights with overlapping beat names
    wi = {
        "season_overviews": [
            {
                "season_name": "第一季",
                "unit_range": [1, 2],
                "progress_range": [1, 2],
                "story_beats": [
                    {"beat_type": "opening", "event": {"event_id": "A@1", "name": "墙头对话", "unit_index": 1, "season_name": "第一季"}},
                ],
                "anchor_events": [
                    {"event_id": "A@1", "name": "墙头对话", "unit_index": 1, "season_name": "第一季"},
                ],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
            {
                "season_name": "第二季",
                "unit_range": [3, 4],
                "progress_range": [3, 4],
                "story_beats": [
                    {"beat_type": "opening", "event": {"event_id": "A@3", "name": "墙头对话", "unit_index": 3, "season_name": "第二季"}},
                ],
                "anchor_events": [
                    {"event_id": "A@3", "name": "墙头对话", "unit_index": 3, "season_name": "第二季"},
                ],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
        ]
    }
    upi = {"units": {}}
    audit = build_audit(wi, upi)

    assert not audit["no_cross_season_overlap"], "Should detect cross-season overlap"
    assert len(audit["cross_season_beat_overlap"]) >= 1
    assert "墙头对话" in audit["cross_season_beat_overlap"][0]["shared_names"]
    assert len(audit["cross_season_anchor_overlap"]) >= 1


def test_audit_no_overlap_when_beats_are_distinct():
    """The audit should report no overlap when each season has unique beat names."""
    wi = {
        "season_overviews": [
            {
                "season_name": "第一季",
                "unit_range": [1, 2],
                "progress_range": [1, 2],
                "story_beats": [
                    {"beat_type": "opening", "event": {"event_id": "A@1", "name": "惊蛰守夜", "unit_index": 1, "season_name": "第一季"}},
                ],
                "anchor_events": [
                    {"event_id": "A@1", "name": "惊蛰守夜", "unit_index": 1, "season_name": "第一季"},
                ],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
            {
                "season_name": "第二季",
                "unit_range": [3, 4],
                "progress_range": [3, 4],
                "story_beats": [
                    {"beat_type": "opening", "event": {"event_id": "B@3", "name": "宁姚再会", "unit_index": 3, "season_name": "第二季"}},
                ],
                "anchor_events": [
                    {"event_id": "B@3", "name": "宁姚再会", "unit_index": 3, "season_name": "第二季"},
                ],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
        ]
    }
    upi = {"units": {}}
    audit = build_audit(wi, upi)

    assert audit["no_cross_season_overlap"], "Should report no cross-season overlap"
    assert len(audit["cross_season_beat_overlap"]) == 0
    assert len(audit["cross_season_anchor_overlap"]) == 0


def test_provenance_records_cross_season_dedup_source():
    """data_provenance should indicate cross-season dedup is active."""
    payload = _make_cross_season_payload(duplicate_names=True)
    for overview in payload["season_overviews"]:
        prov = overview.get("data_provenance", {})
        assert "cross_season_dedup" in prov.get("story_beats_source", ""), (
            f"{overview['season_name']} should record cross_season_dedup in story_beats_source"
        )


# ---------------------------------------------------------------------------
# Step 1-2 new tests: window matching, card granularity, provenance
# ---------------------------------------------------------------------------


def test_window_match_keywords_scattered_across_chapter_no_match():
    """Keywords spread across distant sentences (no window overlap) → no match."""
    rule = {
        "name": "远距离事件",
        "event_type": "冲突",
        "keywords": ["关键A", "关键B", "关键C"],
        "min_keywords": 3,
        "location": "某地",
        "participants": ["陈平安"],
        "significance": "测试",
    }
    unit = {"unit_title": "第一卷 第一章 测试"}
    # 10 sentences, keywords scattered: sentence 0, 5, 9
    sentences = [
        "关键A出现在开头。",
        "无关句子。",
        "无关句子。",
        "无关句子。",
        "无关句子。",
        "关键B出现在中间。",
        "无关句子。",
        "无关句子。",
        "无关句子。",
        "关键C出现在末尾。",
    ]
    segment = {
        "segment_index": 1,
        "segment_start_time": "测试",
        "sentences": sentences,
    }
    result = build_swordcoming_offline_data.match_event_rule(
        unit["unit_title"], sentences, [rule]
    )
    # With window-based matching, 3 keywords cannot all fit in any 1 or 2 adjacent
    # sentences, so the match should fail (None)
    assert result is None, "Scattered keywords should not trigger window-based match"


def test_window_match_keywords_in_adjacent_sentences():
    """Keywords in 2 adjacent sentences → should match."""
    rule = {
        "name": "相邻事件",
        "event_type": "冲突",
        "keywords": ["惊蛰", "守夜"],
        "min_keywords": 2,
        "location": "泥瓶巷",
        "participants": ["陈平安"],
        "significance": "测试",
    }
    unit = {"unit_title": "第一卷 第一章 测试"}
    sentences = [
        "无关句子。",
        "今天是惊蛰时节。",
        "陈平安在守夜。",
        "无关句子。",
    ]
    segment = {
        "segment_index": 1,
        "segment_start_time": "测试",
        "sentences": sentences,
    }
    result = build_swordcoming_offline_data.match_event_rule(
        unit["unit_title"], sentences, [rule]
    )
    assert result is not None, "Adjacent keywords should trigger match"
    assert result.matched_rule_name == "相邻事件"
    assert set(result.matched_keywords) == {"惊蛰", "守夜"}
    assert result.evidence_excerpt  # Should have excerpt text


def test_title_alone_does_not_trigger_match():
    """Title keywords alone (without sentence keywords) should not match."""
    rule = {
        "name": "仅标题事件",
        "event_type": "冲突",
        "keywords": ["惊蛰", "泥瓶巷"],
        "min_keywords": 2,
        "location": "泥瓶巷",
        "participants": ["陈平安"],
        "significance": "测试",
    }
    # Title contains both keywords but sentences don't
    unit = {"unit_title": "第一卷 惊蛰 泥瓶巷"}
    sentences = ["无关句子。", "完全不相干的内容。"]
    segment = {
        "segment_index": 1,
        "segment_start_time": "测试",
        "sentences": sentences,
    }
    result = build_swordcoming_offline_data.match_event_rule(
        unit["unit_title"], sentences, [rule]
    )
    assert result is None, "Title keywords alone should not trigger match"


def test_chapter_synopsis_card_granularity_fields():
    """Synopsis should have key_development_events and capped synopsis length."""
    kb, upi = _make_synopsis_kb_and_upi()
    synopses = build_chapter_synopses(kb=kb, unit_progress_index=upi)
    for entry in synopses:
        assert "key_development_events" in entry
        assert len(entry["synopsis"]) <= 220, (
            f"unit {entry['unit_index']} synopsis too long: {len(entry['synopsis'])} chars"
        )
        for kd in entry["key_development_events"]:
            assert "event_id" in kd
            assert "name" in kd
            assert "display_text" in kd
            assert len(kd["display_text"]) <= 100


def test_key_events_card_fields_present():
    """Key events should have the new card-granularity fields."""
    kb, upi = _make_synopsis_kb_and_upi()
    chapters = build_key_events_index(kb=kb, unit_progress_index=upi, min_score=0)
    for ch in chapters:
        for ev in ch["key_events"]:
            assert "display_summary" in ev
            assert "evidence_excerpt" in ev
            assert "name_occurrence_count" in ev
            assert "is_first_occurrence" in ev
            assert "selection_reason" in ev
            assert len(ev["display_summary"]) <= 100


def test_audit_card_granularity_checks():
    """Audit should include card_granularity section."""
    wi = {
        "season_overviews": [
            {
                "season_name": "第一季",
                "unit_range": [1, 2],
                "progress_range": [1, 2],
                "story_beats": [],
                "anchor_events": [],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
        ]
    }
    upi = {"units": {}}
    # Provide synopses with one too-long synopsis
    synopses = [
        {
            "unit_index": 1,
            "synopsis": "x" * 221,  # over 220
            "key_development_events": [
                {"display_text": "y" * 101, "evidence_excerpt": ""},  # over 100 + missing evidence
            ],
        }
    ]
    key_events = [
        {
            "unit_index": 1,
            "key_events": [
                {"display_summary": "z" * 101, "evidence_excerpt": "", "name": "频繁事件", "name_occurrence_count": 15},
            ],
        }
    ]
    audit = build_audit(wi, upi, chapter_synopses=synopses, key_events_index=key_events)
    cg = audit["card_granularity"]
    assert cg["chapter_synopsis_too_long_count"] == 1
    assert cg["key_event_summary_too_long_count"] >= 2  # 1 from synopses + 1 from key_events
    assert cg["missing_evidence_excerpt_count"] >= 2
    assert len(cg["high_frequency_event_name_hotspots"]) == 1
    assert cg["high_frequency_event_name_hotspots"][0]["name_occurrence_count"] == 15


def test_audit_adjacent_season_failure():
    """Audit should flag adjacent seasons with >1 shared beat/anchor name."""
    wi = {
        "season_overviews": [
            {
                "season_name": "第一季",
                "unit_range": [1, 2],
                "progress_range": [1, 2],
                "story_beats": [
                    {"beat_type": "opening", "event": {"event_id": "A1", "name": "墙头对话", "unit_index": 1}},
                    {"beat_type": "midpoint", "event": {"event_id": "A2", "name": "守夜独白", "unit_index": 1}},
                ],
                "anchor_events": [
                    {"event_id": "A1", "name": "墙头对话", "unit_index": 1},
                    {"event_id": "A2", "name": "守夜独白", "unit_index": 1},
                ],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
            {
                "season_name": "第二季",
                "unit_range": [3, 4],
                "progress_range": [3, 4],
                "story_beats": [
                    {"beat_type": "opening", "event": {"event_id": "B1", "name": "墙头对话", "unit_index": 3}},
                    {"beat_type": "midpoint", "event": {"event_id": "B2", "name": "守夜独白", "unit_index": 3}},
                ],
                "anchor_events": [
                    {"event_id": "B1", "name": "墙头对话", "unit_index": 3},
                    {"event_id": "B2", "name": "守夜独白", "unit_index": 3},
                ],
                "top_roles": [],
                "priority_roles": [],
                "priority_relationships": [],
                "must_keep_scenes": [],
                "data_provenance": {},
            },
        ]
    }
    upi = {"units": {}}
    audit = build_audit(wi, upi)
    assert not audit["no_adjacent_season_failures"]
    assert len(audit["adjacent_season_failures"]) == 1
    fail = audit["adjacent_season_failures"][0]
    assert set(fail["shared_beat_names"]) == {"墙头对话", "守夜独白"}


def test_provenance_expanded_fields():
    """data_provenance should include the new expanded fields."""
    payload = _make_cross_season_payload(duplicate_names=True)
    for overview in payload["season_overviews"]:
        prov = overview.get("data_provenance", {})
        assert "story_beat_name_overlap_with_previous" in prov
        assert "anchor_name_overlap_with_previous" in prov
        assert "frequency_penalty_applied" in prov
        assert "fallback_used" in prov
        assert "selected_from_season_focus" in prov
        assert "beat_first_occurrence_count" in prov
        assert "anchor_first_occurrence_count" in prov


# ---------------------------------------------------------------------------
# P1 regression: fallback provenance alignment
# ---------------------------------------------------------------------------


def test_choose_summary_sentences_indexed_returns_original_indexes():
    """_choose_summary_sentences_indexed must return correct (index, text) pairs."""
    sentences = [
        "无关句子A。",
        "陈平安在泥瓶巷守夜。",
        "无关句子B。",
        "宋集薪在墙头讥讽。",
        "无关句子C。",
    ]
    sentence_characters = [[], ["陈平安"], [], ["宋集薪"], []]
    sentence_locations = [[], ["泥瓶巷"], [], ["墙头"], []]

    indexed = build_swordcoming_offline_data._choose_summary_sentences_indexed(
        sentences, sentence_characters, sentence_locations, limit=2
    )
    assert len(indexed) == 2
    # The two prioritised sentences should be at original indexes 1 and 3
    assert indexed[0] == (1, "陈平安在泥瓶巷守夜。")
    assert indexed[1] == (3, "宋集薪在墙头讥讽。")


def test_choose_summary_sentences_indexed_fallback():
    """When no sentence mentions characters/locations, plain sentences are returned."""
    sentences = ["甲。", "乙。", "丙。"]
    sentence_characters = [[], [], []]
    sentence_locations = [[], [], []]

    indexed = build_swordcoming_offline_data._choose_summary_sentences_indexed(
        sentences, sentence_characters, sentence_locations, limit=2
    )
    assert len(indexed) == 2
    assert indexed[0] == (0, "甲。")
    assert indexed[1] == (1, "乙。")


def test_choose_summary_sentences_wrapper_unchanged():
    """choose_summary_sentences (public wrapper) should return the same texts as before."""
    sentences = ["无关。", "陈平安出发。", "到达泥瓶巷。"]
    sentence_characters = [[], ["陈平安"], []]
    sentence_locations = [[], [], ["泥瓶巷"]]

    result = build_swordcoming_offline_data.choose_summary_sentences(
        sentences, sentence_characters, sentence_locations, limit=2
    )
    assert result == ["陈平安出发。", "到达泥瓶巷。"]


def test_fallback_event_evidence_indexes_match_excerpt():
    """Non-rule event: evidence_sentence_indexes must cover only the chosen
    summary sentences, not the entire segment."""
    unit = {"unit_title": "第一卷笼中雀 第一章 惊蛰", "juan_index": 1}
    sentences = [
        "无关句子。",
        "陈平安独自守夜。",
        "无关句子。",
        "无关句子。",
        "宋集薪在墙头讥讽。",
    ]
    segment = {
        "segment_index": 1,
        "segment_start_time": "惊蛰",
        "sentences": sentences,
    }
    sentence_characters = [[], ["陈平安"], [], [], ["宋集薪"]]
    sentence_locations = [[], [], [], [], ["墙头"]]

    event = build_swordcoming_offline_data.build_event(
        unit=unit,
        segment=segment,
        sentences=sentences,
        sentence_characters=sentence_characters,
        sentence_locations=sentence_locations,
        relation_actions=[],
        event_rules=[],          # no rules → forces fallback path
        event_type_rules=[],
    )
    assert event is not None
    # Indexes must be a small subset, NOT range(5)
    assert len(event.sentence_indexes_in_segment) <= 2
    assert event.sentence_indexes_in_segment != list(range(len(sentences)))
    # Each index must correspond to a sentence whose text appears in the excerpt
    for idx in event.sentence_indexes_in_segment:
        assert sentences[idx] in event.evidence_excerpt or sentences[idx][:20] in event.evidence_excerpt