"""Tests for the upstream extraction & disambiguation governance plan.

Covers:
  1. Generic designator variant detection (穿草鞋的少年, 那个老头, etc.)
  2. Allowlist safety (杨老头, 火龙真人, 大骊皇帝 not killed)
  3. Existing noise still caught (沙哑, 俞真意冷)
  4. classify_role_name precedence: allow > merge > block
  5. Stage B post-LLM cascading cleanup
  6. Stage C entity_resolution integration
"""
from __future__ import annotations

import pytest

from scripts.character_quality import (
    audit_role_name,
    is_pseudo_role_name,
    classify_role_name,
    classify_role_name_detailed,
    NameClassification,
    build_allowed_special_designator_map,
    build_allowed_special_designator_names,
    _detect_generic_designator_variant,
    VOICE_DESCRIPTOR_NAMES,
)
from model.extraction import EntityRelationExtraction
from model.role import Role
from model.event import Event
from model.location import Location
from model.action import Action


# ── Manual overrides fixtures ──

BLOCKED_ALIASES = [
    "先生", "掌教", "道人", "少年", "少女", "老人", "白衣少年",
    "沙哑", "俞真意冷",
]

ALLOWED_SPECIAL_DESIGNATORS = [
    {"name": "杨老头", "resolution": "keep_as_canonical", "canonical_target": "杨老头", "kind": "honorific"},
    {"name": "大骊皇帝", "resolution": "keep_as_canonical", "canonical_target": "大骊皇帝", "kind": "official_title"},
    {"name": "火龙真人", "resolution": "keep_as_canonical", "canonical_target": "火龙真人", "kind": "daohao"},
    {"name": "于夫人", "resolution": "keep_as_canonical", "canonical_target": "于夫人", "kind": "honorific"},
    {"name": "桂夫人", "resolution": "keep_as_canonical", "canonical_target": "桂夫人", "kind": "honorific"},
    {"name": "桂姨", "resolution": "merge_to_canonical", "canonical_target": "桂夫人", "kind": "kinship_title"},
    {"name": "刘太守", "resolution": "keep_as_canonical", "canonical_target": "刘太守", "kind": "official_title"},
]

CANONICAL_ROLE_NAMES = {
    "宋睦": "宋集薪",
    "齐先生": "齐静春",
    "大骊国师": "崔瀺",
    "桂姨": "桂夫人",
}

ROLE_ALIASES = {
    "宋集薪": ["宋睦"],
    "齐静春": ["齐先生"],
    "崔瀺": ["大骊国师"],
    "桂夫人": ["桂姨"],
}

ALLOWED_NAMES = build_allowed_special_designator_names(ALLOWED_SPECIAL_DESIGNATORS)


# =====================================================================
# 1. Generic designator variant detection
# =====================================================================

class TestGenericDesignatorVariantDetection:
    """Test that structural patterns catch descriptive designators."""

    @pytest.mark.parametrize("name", [
        "穿草鞋的少年",
        "穿白袍的道人",
        "穿青衫的书生",
        "穿灰衣的老人",
    ])
    def test_clothing_descriptors_flagged(self, name: str):
        reason = _detect_generic_designator_variant(name)
        assert reason is not None, f"{name} should be flagged as clothing descriptor"
        assert "穿着描述泛称" in reason

    @pytest.mark.parametrize("name", [
        "白衣少年",
        "青衫书生",
        "黑袍老人",
        "灰衣女子",
    ])
    def test_appearance_role_flagged(self, name: str):
        reason = _detect_generic_designator_variant(name)
        assert reason is not None, f"{name} should be flagged as appearance descriptor"
        assert "外貌泛称" in reason

    @pytest.mark.parametrize("name", [
        "那个老头",
        "这个少年",
        "那位道人",
        "一位老人",
        "一个少女",
    ])
    def test_demonstrative_generic_flagged(self, name: str):
        reason = _detect_generic_designator_variant(name)
        assert reason is not None, f"{name} should be flagged as demonstrative+generic"
        assert "指示代词+泛称" in reason

    @pytest.mark.parametrize("name", [
        "身旁的道人",
        "身边的少年",
        "对面的老人",
        "一旁少女",
    ])
    def test_positional_role_flagged(self, name: str):
        reason = _detect_generic_designator_variant(name)
        assert reason is not None, f"{name} should be flagged as positional descriptor"

    @pytest.mark.parametrize("name", [
        "旁边的儒士",
        "面前的汉子",
    ])
    def test_modifier_de_role_flagged(self, name: str):
        reason = _detect_generic_designator_variant(name)
        assert reason is not None, f"{name} should be flagged"

    @pytest.mark.parametrize("name", [
        "少年", "少女", "道人", "老人", "老头", "老者",
        "女子", "男子", "儒士", "书生", "公子", "夫人",
    ])
    def test_bare_generic_role_words_flagged(self, name: str):
        reason = _detect_generic_designator_variant(name)
        assert reason is not None, f"{name} should be flagged as bare generic"
        assert "泛称裸词" in reason


# =====================================================================
# 2. Allowlist safety — must NOT be killed
# =====================================================================

class TestAllowlistSafety:
    """Stable designators must survive all filtering."""

    @pytest.mark.parametrize("name", [
        "杨老头",
        "火龙真人",
        "大骊皇帝",
        "于夫人",
        "桂夫人",
        "桂姨",
        "刘太守",
    ])
    def test_allowed_designators_not_flagged_by_audit(self, name: str):
        reasons = audit_role_name(
            name,
            blocked_names=BLOCKED_ALIASES,
            allowed_names=ALLOWED_NAMES,
        )
        assert reasons == [], f"{name} should NOT be flagged (got: {reasons})"

    @pytest.mark.parametrize("name", [
        "杨老头",
        "火龙真人",
        "大骊皇帝",
        "于夫人",
        "桂夫人",
        "桂姨",
        "刘太守",
    ])
    def test_allowed_designators_not_pseudo(self, name: str):
        assert not is_pseudo_role_name(
            name,
            blocked_names=BLOCKED_ALIASES,
            allowed_names=ALLOWED_NAMES,
        )

    def test_real_character_names_untouched(self):
        for name in ("陈平安", "宁姚", "齐静春", "崔瀺", "宋集薪"):
            reasons = audit_role_name(name, blocked_names=BLOCKED_ALIASES)
            assert reasons == [], f"{name} should not be flagged"


# =====================================================================
# 3. Existing noise still caught
# =====================================================================

class TestExistingNoiseContinues:
    """Previously caught noise must still be detected."""

    def test_sha_ya_still_flagged(self):
        reasons = audit_role_name("沙哑", blocked_names=BLOCKED_ALIASES)
        assert reasons, "沙哑 should still be flagged"

    def test_yu_zhen_yi_leng_still_flagged(self):
        reasons = audit_role_name(
            "俞真意冷",
            blocked_names=BLOCKED_ALIASES,
            canonical_roles={"俞真意"},
        )
        assert reasons, "俞真意冷 should still be flagged"

    def test_bai_yi_shao_nian_still_flagged(self):
        reasons = audit_role_name("白衣少年", blocked_names=BLOCKED_ALIASES)
        assert reasons, "白衣少年 should still be flagged"


# =====================================================================
# 4. classify_role_name precedence: allow > merge > block
# =====================================================================

class TestClassifyRoleNamePrecedence:
    """classify_role_name must enforce allow > merge > block."""

    ASD = build_allowed_special_designator_map(ALLOWED_SPECIAL_DESIGNATORS)

    def test_allowed_special_is_allow(self):
        for name in ("杨老头", "火龙真人", "大骊皇帝", "刘太守"):
            result = classify_role_name(
                name,
                allowed_special_designators=self.ASD,
                blocked_names=BLOCKED_ALIASES,
            )
            assert result == "allow", f"{name} should be 'allow', got '{result}'"

    def test_canonical_alias_is_merge(self):
        """Known alias → merge."""
        result = classify_role_name(
            "宋睦",
            allowed_special_designators=self.ASD,
            canonical_role_names=CANONICAL_ROLE_NAMES,
            role_aliases=ROLE_ALIASES,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result == "merge"

    def test_canonical_name_is_allow(self):
        """The canonical name itself → allow."""
        result = classify_role_name(
            "宋集薪",
            allowed_special_designators=self.ASD,
            canonical_role_names=CANONICAL_ROLE_NAMES,
            role_aliases=ROLE_ALIASES,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result == "allow"

    def test_blocked_noise_is_block(self):
        for name in ("沙哑", "白衣少年", "少年", "道人"):
            result = classify_role_name(
                name,
                allowed_special_designators=self.ASD,
                blocked_names=BLOCKED_ALIASES,
            )
            assert result == "block", f"{name} should be 'block', got '{result}'"

    def test_generic_variant_is_block(self):
        for name in ("穿草鞋的少年", "那个老头", "身旁的道人"):
            result = classify_role_name(
                name,
                allowed_special_designators=self.ASD,
                blocked_names=BLOCKED_ALIASES,
            )
            assert result == "block", f"{name} should be 'block', got '{result}'"

    def test_allow_beats_block(self):
        """杨老头 contains 老头 (a generic word) but is in the allowlist."""
        result = classify_role_name(
            "杨老头",
            allowed_special_designators=self.ASD,
            blocked_names=BLOCKED_ALIASES + ["杨老头"],
        )
        assert result == "allow"

    def test_unknown_name_is_allow(self):
        """Names not in any list get benefit of the doubt."""
        result = classify_role_name(
            "张三丰",
            allowed_special_designators=self.ASD,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result == "allow"

    def test_桂姨_is_merge_via_asd(self):
        """桂姨 is in ASD as merge_to_canonical — classify returns 'merge'."""
        result = classify_role_name(
            "桂姨",
            allowed_special_designators=self.ASD,
            canonical_role_names=CANONICAL_ROLE_NAMES,
            role_aliases=ROLE_ALIASES,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result == "merge"

    def test_桂姨_detailed_gives_canonical_target(self):
        """classify_role_name_detailed returns merge + canonical_target=桂夫人."""
        result = classify_role_name_detailed(
            "桂姨",
            allowed_special_designators=self.ASD,
            canonical_role_names=CANONICAL_ROLE_NAMES,
            role_aliases=ROLE_ALIASES,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result["decision"] == "merge"
        assert result["canonical_target"] == "桂夫人"

    def test_keep_as_canonical_gives_keep(self):
        """杨老头 (keep_as_canonical) → decision=keep, canonical_target=None."""
        result = classify_role_name_detailed(
            "杨老头",
            allowed_special_designators=self.ASD,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result["decision"] == "keep"
        assert result["canonical_target"] is None

    def test_宋睦_detailed_merge_target(self):
        """宋睦 via canonical_role_names → merge to 宋集薪."""
        result = classify_role_name_detailed(
            "宋睦",
            allowed_special_designators=self.ASD,
            canonical_role_names=CANONICAL_ROLE_NAMES,
            role_aliases=ROLE_ALIASES,
            blocked_names=BLOCKED_ALIASES,
        )
        assert result["decision"] == "merge"
        assert result["canonical_target"] == "宋集薪"


# =====================================================================
# 5. Stage B post-LLM cascading cleanup
# =====================================================================

class TestStageB_CascadingCleanup:
    """filter_extraction_noise must cascade filtered names correctly."""

    FILTER_KWARGS = dict(
        blocked_aliases=BLOCKED_ALIASES,
        allowed_special_names=ALLOWED_NAMES,
        canonical_role_set={"陈平安", "宁姚", "俞真意", "齐静春"},
    )

    @staticmethod
    def _make_extraction(
        entities: list[Role],
        events: list[Event] | None = None,
        locations: list[Location] | None = None,
        relations: list[Action] | None = None,
    ) -> EntityRelationExtraction:
        return EntityRelationExtraction(
            entities=entities,
            events=events or [],
            locations=locations or [],
            relations=relations or [],
        )

    def test_pseudo_person_removed(self):
        from extraction_filter import filter_extraction_noise

        ext = self._make_extraction(
            entities=[
                Role(name="穿草鞋的少年", description="test"),
                Role(name="陈平安", description="主角"),
            ]
        )
        result = filter_extraction_noise(ext, **self.FILTER_KWARGS)
        names = [e.name for e in result.entities]
        assert "穿草鞋的少年" not in names
        assert "陈平安" in names

    def test_filtered_person_removed_from_event_participants(self):
        from extraction_filter import filter_extraction_noise

        ext = self._make_extraction(
            entities=[
                Role(name="那个老头", description="test"),
                Role(name="陈平安", description="主角"),
            ],
            events=[
                Event(
                    name="相遇",
                    description="偶遇",
                    participants=["陈平安", "那个老头"],
                ),
            ],
        )
        result = filter_extraction_noise(ext, **self.FILTER_KWARGS)
        assert "那个老头" not in result.events[0].participants
        assert "陈平安" in result.events[0].participants

    def test_filtered_person_removed_from_location_related(self):
        from extraction_filter import filter_extraction_noise

        ext = self._make_extraction(
            entities=[
                Role(name="身旁的道人", description="test"),
                Role(name="宁姚", description="女主角"),
            ],
            locations=[
                Location(
                    name="小镇",
                    related_entities=["宁姚", "身旁的道人"],
                ),
            ],
        )
        result = filter_extraction_noise(ext, **self.FILTER_KWARGS)
        assert "身旁的道人" not in result.locations[0].related_entities
        assert "宁姚" in result.locations[0].related_entities

    def test_relation_with_filtered_endpoint_discarded(self):
        from extraction_filter import filter_extraction_noise

        ext = self._make_extraction(
            entities=[
                Role(name="白衣少年", description="test"),
                Role(name="陈平安", description="主角"),
                Role(name="宁姚", description="女主角"),
            ],
            relations=[
                Action(
                    from_roles=["白衣少年"],
                    to_roles=["陈平安"],
                    action="对话",
                    context="test",
                ),
                Action(
                    from_roles=["陈平安"],
                    to_roles=["宁姚"],
                    action="对话",
                    context="test good",
                ),
            ],
        )
        result = filter_extraction_noise(ext, **self.FILTER_KWARGS)
        assert len(result.relations) == 1
        assert result.relations[0].from_roles == ["陈平安"]
        assert result.relations[0].to_roles == ["宁姚"]

    def test_pseudo_alias_cleaned_but_entity_kept(self):
        from extraction_filter import filter_extraction_noise

        ext = self._make_extraction(
            entities=[
                Role(name="陈平安", alias=["穿草鞋的少年", "小平安"], description="主角"),
            ]
        )
        result = filter_extraction_noise(ext, **self.FILTER_KWARGS)
        assert len(result.entities) == 1
        assert "穿草鞋的少年" not in result.entities[0].alias
        assert "小平安" in result.entities[0].alias

    def test_non_person_entity_types_not_filtered(self):
        from extraction_filter import filter_extraction_noise

        ext = self._make_extraction(
            entities=[
                Role(name="少年", entity_type="polity", description="国名测试"),
            ]
        )
        result = filter_extraction_noise(ext, **self.FILTER_KWARGS)
        assert len(result.entities) == 1


# =====================================================================
# 6. Stage C entity_resolution integration
# =====================================================================

class TestEntityResolution_ClassifyIntegration:
    """entity_resolution uses character_quality via _classify_name."""

    @staticmethod
    def _make_resolver():
        from entity_resolution import EntityResolver
        resolver = EntityResolver()
        resolver.set_manual_overrides({
            "blocked_aliases": BLOCKED_ALIASES,
            "allowed_special_designators": ALLOWED_SPECIAL_DESIGNATORS,
            "canonical_role_names": CANONICAL_ROLE_NAMES,
            "role_aliases": ROLE_ALIASES,
        })
        return resolver

    def test_generic_variant_blocked_from_merging(self):
        resolver = self._make_resolver()
        role = Role(name="穿草鞋的少年", description="泛称")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "穿草鞋的少年" not in roles

    def test_allowed_designator_survives(self):
        resolver = self._make_resolver()
        role = Role(name="杨老头", description="杨氏老掌柜")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "杨老头" in roles

    def test_blocked_alias_not_merged(self):
        resolver = self._make_resolver()
        role = Role(name="陈平安", alias=["少年"], description="主角")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "陈平安" in roles
        # 少年 should not become a separate canonical role
        assert "少年" not in roles

    def test_real_name_with_clean_alias_merges(self):
        resolver = self._make_resolver()
        role1 = Role(name="宋集薪", description="地主少爷")
        role2 = Role(name="宋睦", alias=["宋集薪"], description="改名后")
        resolver.add_role(role1, juan_index=1, segment_index=0, chunk_index=0)
        resolver.add_role(role2, juan_index=1, segment_index=1, chunk_index=1)
        roles = resolver.resolve_roles()
        # Both should merge into a single role
        all_names = set()
        for r in roles.values():
            all_names.update(r.all_names)
        assert "宋集薪" in all_names
        assert "宋睦" in all_names
        # Should not have separate entries for both
        assert len(roles) == 1

    def test_bare_generic_word_blocked(self):
        """Stand-alone generic words like 道人/老人 shouldn't survive as canonical."""
        resolver = self._make_resolver()
        for name in ("道人", "老人", "少年", "少女"):
            role = Role(name=name, description="泛称")
            resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        for name in ("道人", "老人", "少年", "少女"):
            assert name not in roles, f"{name} should not become a canonical role"

    def test_火龙真人_not_blocked(self):
        """火龙真人 contains 真人 (blocked) but is in allowlist."""
        resolver = self._make_resolver()
        role = Role(name="火龙真人", description="龙虎山掌教")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "火龙真人" in roles


# =====================================================================
# 7. merge_to_canonical entity resolution
# =====================================================================

class TestMergeToCanonicalResolution:
    """桂姨 (merge_to_canonical → 桂夫人) must produce a single unified role."""

    @staticmethod
    def _make_resolver():
        from entity_resolution import EntityResolver
        resolver = EntityResolver()
        resolver.set_manual_overrides({
            "blocked_aliases": BLOCKED_ALIASES,
            "allowed_special_designators": ALLOWED_SPECIAL_DESIGNATORS,
            "canonical_role_names": CANONICAL_ROLE_NAMES,
            "role_aliases": ROLE_ALIASES,
        })
        return resolver

    def test_only_alias_produces_canonical_target(self):
        """Only 桂姨 appears → unified role id must be 桂夫人."""
        resolver = self._make_resolver()
        role = Role(name="桂姨", description="老龙城女主人")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "桂姨" not in roles, "桂姨 must not survive as an independent role id"
        assert "桂夫人" in roles, "桂夫人 must be the canonical role id"
        assert "桂姨" in roles["桂夫人"].all_names
        assert "桂夫人" in roles["桂夫人"].all_names

    def test_alias_and_canonical_coexist_single_role(self):
        """桂姨 + 桂夫人 both appear → exactly 1 unified role."""
        resolver = self._make_resolver()
        r1 = Role(name="桂姨", description="老龙城女主人")
        r2 = Role(name="桂夫人", description="桂花巷主人")
        resolver.add_role(r1, juan_index=1, segment_index=0, chunk_index=0)
        resolver.add_role(r2, juan_index=2, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert len(roles) == 1, f"Expected 1 unified role, got {len(roles)}: {list(roles.keys())}"
        assert "桂夫人" in roles
        assert "桂姨" in roles["桂夫人"].all_names

    def test_keep_as_canonical_not_merged_elsewhere(self):
        """杨老头 (keep_as_canonical) stays as its own entity."""
        resolver = self._make_resolver()
        role = Role(name="杨老头", description="杨氏老掌柜")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "杨老头" in roles
        assert roles["杨老头"].canonical_name == "杨老头"

    def test_宋睦_merges_to_宋集薪_via_canonical_role_names(self):
        """宋睦 in canonical_role_names → merges to 宋集薪."""
        resolver = self._make_resolver()
        r1 = Role(name="宋睦", description="原名")
        resolver.add_role(r1, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "宋睦" not in roles, "宋睦 must not be an independent role id"
        assert "宋集薪" in roles
        assert "宋睦" in roles["宋集薪"].all_names

    def test_齐先生_merges_to_齐静春(self):
        """齐先生 in role_aliases → merges to 齐静春."""
        resolver = self._make_resolver()
        r1 = Role(name="齐先生", description="书院山长")
        resolver.add_role(r1, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "齐先生" not in roles
        assert "齐静春" in roles
        assert "齐先生" in roles["齐静春"].all_names


# =====================================================================
# 8. Alias sticky / concat noise detection with expanded ref set
# =====================================================================

class TestAliasStickyNoiseDetection:
    """Concat detection must catch alias+action-suffix patterns."""

    # Build a canonical_roles set that includes aliases (matching the new behavior)
    FULL_CANONICAL_ROLES = {
        "陈平安", "宁姚", "俞真意", "齐静春", "宋集薪", "崔瀺",
        # aliases that are now in the expanded set:
        "宋睦", "齐先生", "大骊国师", "桂姨", "桂夫人",
        "杨老头", "杨掌柜", "火龙真人", "刘太守",
    }

    def test_宋睦笑_flagged(self):
        """宋睦 + 笑 → concat noise."""
        reasons = audit_role_name(
            "宋睦笑",
            blocked_names=BLOCKED_ALIASES,
            canonical_roles=self.FULL_CANONICAL_ROLES,
        )
        assert any("人名粘连" in r for r in reasons), f"宋睦笑 should be caught: {reasons}"

    def test_齐先生道_flagged(self):
        """齐先生 + 道 → concat noise."""
        reasons = audit_role_name(
            "齐先生道",
            blocked_names=BLOCKED_ALIASES,
            canonical_roles=self.FULL_CANONICAL_ROLES,
        )
        assert any("人名粘连" in r for r in reasons), f"齐先生道 should be caught: {reasons}"

    def test_桂姨笑_flagged(self):
        """桂姨 + 笑 → concat noise."""
        reasons = audit_role_name(
            "桂姨笑",
            blocked_names=BLOCKED_ALIASES,
            canonical_roles=self.FULL_CANONICAL_ROLES,
            allowed_names=ALLOWED_NAMES,
        )
        assert any("人名粘连" in r for r in reasons), f"桂姨笑 should be caught: {reasons}"

    def test_杨老头_not_flagged_as_sticky(self):
        """杨老头 is a real name, not a concat artefact."""
        reasons = audit_role_name(
            "杨老头",
            blocked_names=BLOCKED_ALIASES,
            canonical_roles=self.FULL_CANONICAL_ROLES,
            allowed_names=ALLOWED_NAMES,
        )
        assert reasons == [], f"杨老头 should not be flagged: {reasons}"

    def test_entity_resolution_catches_宋睦笑(self):
        """Stage C resolver must filter 宋睦笑 as concat noise."""
        from entity_resolution import EntityResolver
        resolver = EntityResolver()
        resolver.set_manual_overrides({
            "blocked_aliases": BLOCKED_ALIASES,
            "allowed_special_designators": ALLOWED_SPECIAL_DESIGNATORS,
            "canonical_role_names": CANONICAL_ROLE_NAMES,
            "role_aliases": ROLE_ALIASES,
        })
        role = Role(name="宋睦笑", description="test concat")
        resolver.add_role(role, juan_index=1, segment_index=0, chunk_index=0)
        roles = resolver.resolve_roles()
        assert "宋睦笑" not in roles, "宋睦笑 should be blocked as concat noise"

    def test_stage_b_filter_catches_齐先生道(self):
        """Stage B filter must remove 齐先生道."""
        from extraction_filter import filter_extraction_noise

        # Build a canonical_role_set that includes aliases (matching new behavior)
        ext = EntityRelationExtraction(
            entities=[
                Role(name="齐先生道", description="concat noise"),
                Role(name="陈平安", description="主角"),
            ],
            events=[],
            locations=[],
            relations=[],
        )
        result = filter_extraction_noise(
            ext,
            blocked_aliases=BLOCKED_ALIASES,
            allowed_special_names=ALLOWED_NAMES,
            canonical_role_set=self.FULL_CANONICAL_ROLES,
        )
        names = [e.name for e in result.entities]
        assert "齐先生道" not in names, "齐先生道 should be filtered"
        assert "陈平安" in names
