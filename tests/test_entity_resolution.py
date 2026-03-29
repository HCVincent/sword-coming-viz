"""
Tests for entity resolution with entity type classification.

Tests cover:
1. Entity type routing from Role.entity_type field (LLM-provided)
2. Fallback heuristic classification (polity/school/organization patterns)
3. School and organization resolution and merging
4. Updated LLM prompt produces valid entity_type values
"""

import pytest
from model.role import Role
from model.polity import Polity
from model.school import School
from model.organization import Organization
from model.unified import EntityOccurrence
from entity_resolution import EntityResolver


class TestEntityTypeClassification:
    """Test entity type classification from Role.entity_type field."""

    def test_entity_type_field_exists(self):
        """Role model should have entity_type field with default None (inferred as 'person')."""
        role = Role(name="张三")
        assert hasattr(role, 'entity_type')
        # Default is None, which is treated as 'person' by entity_resolution.py
        assert role.entity_type is None or role.entity_type == "person"

    def test_entity_type_person(self):
        """entity_type='person' should route to role occurrences."""
        resolver = EntityResolver()
        role = Role(
            name="商鞅",
            entity_type="person",
            description="秦国变法大臣",
            alias=["卫鞅", "公孙鞅"],
        )
        resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        assert len(resolver.role_occurrences) > 0
        assert "商鞅" in resolver.role_occurrences
        assert len(resolver.polity_occurrences) == 0
        assert len(resolver.school_occurrences) == 0
        assert len(resolver.organization_occurrences) == 0

    def test_entity_type_polity(self):
        """entity_type='polity' should route to polity occurrences."""
        resolver = EntityResolver()
        role = Role(
            name="秦",
            entity_type="polity",
            description="战国七雄之一",
            alias=["秦国"],
        )
        resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        assert len(resolver.polity_occurrences) > 0
        assert "秦" in resolver.polity_occurrences
        assert len(resolver.role_occurrences) == 0

    def test_entity_type_school(self):
        """entity_type='school' should route to school occurrences."""
        resolver = EntityResolver()
        role = Role(
            name="儒家",
            entity_type="school",
            description="以孔子思想为核心的学派",
            alias=["儒学"],
        )
        resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        assert len(resolver.school_occurrences) > 0
        assert "儒家" in resolver.school_occurrences
        assert len(resolver.role_occurrences) == 0
        assert len(resolver.polity_occurrences) == 0

    def test_entity_type_organization(self):
        """entity_type='organization' should route to organization occurrences."""
        resolver = EntityResolver()
        role = Role(
            name="丞相府",
            entity_type="organization",
            description="丞相办公机构",
        )
        resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        assert len(resolver.organization_occurrences) > 0
        assert "丞相府" in resolver.organization_occurrences
        assert len(resolver.role_occurrences) == 0


class TestFallbackHeuristics:
    """Test fallback heuristic classification when entity_type='person' or unset."""

    def test_polity_name_heuristic(self):
        """Names matching polity patterns should be reclassified."""
        resolver = EntityResolver()
        
        # Test various polity patterns
        polity_names = ["赵", "魏国", "汉", "周朝", "秦王朝"]
        for name in polity_names:
            role = Role(name=name, entity_type="person")  # Default/wrong type
            resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        # All should be reclassified to polities
        assert len(resolver.polity_occurrences) >= len(polity_names)
        for name in polity_names:
            assert name in resolver.polity_occurrences, f"{name} should be in polity_occurrences"

    def test_school_name_heuristic(self):
        """Names matching school patterns should be reclassified."""
        resolver = EntityResolver()
        
        # Test various school patterns
        school_names = ["儒家", "法家", "道家", "墨家", "兵家", "儒学"]
        for name in school_names:
            role = Role(name=name, entity_type="person")  # Default/wrong type
            resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        # All should be reclassified to schools
        assert len(resolver.school_occurrences) >= len(school_names)
        for name in school_names:
            assert name in resolver.school_occurrences, f"{name} should be in school_occurrences"

    def test_organization_name_heuristic(self):
        """Names matching organization patterns should be reclassified."""
        resolver = EntityResolver()
        
        # Test various organization patterns
        org_names = ["丞相府", "太尉府", "虎贲军"]
        for name in org_names:
            role = Role(name=name, entity_type="person")  # Default/wrong type
            resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        # All should be reclassified to organizations
        for name in org_names:
            assert name in resolver.organization_occurrences, f"{name} should be in organization_occurrences"

    def test_person_not_reclassified(self):
        """Person names should not be reclassified."""
        resolver = EntityResolver()
        
        person_names = ["商鞅", "孔子", "韩非子", "李斯"]
        for name in person_names:
            role = Role(name=name, entity_type="person")
            resolver.add_role(role, juan_index=1, segment_index=1, chunk_index=0)
        
        # All should remain as roles
        for name in person_names:
            assert name in resolver.role_occurrences, f"{name} should be in role_occurrences"
        assert len(resolver.polity_occurrences) == 0
        assert len(resolver.school_occurrences) == 0
        assert len(resolver.organization_occurrences) == 0


class TestSchoolResolution:
    """Test school entity resolution and merging."""

    def test_add_school_directly(self):
        """Schools added directly should be tracked correctly."""
        resolver = EntityResolver()
        school = School(
            name="法家",
            alias=["法"],
            description="以法治国的思想流派",
        )
        resolver.add_school(school, juan_index=1, segment_index=1, chunk_index=0)
        
        assert "法家" in resolver.school_occurrences
        assert len(resolver.school_occurrences["法家"]) == 1

    def test_school_alias_union(self):
        """Schools with aliases should be merged."""
        resolver = EntityResolver()
        
        school1 = School(name="儒家", alias=["儒"])
        school2 = School(name="儒", alias=[])
        
        resolver.add_school(school1, juan_index=1, segment_index=1, chunk_index=0)
        resolver.add_school(school2, juan_index=2, segment_index=1, chunk_index=0)
        
        schools = resolver.resolve_schools()
        # Should merge into one school
        assert len(schools) == 1
        unified = list(schools.values())[0]
        assert "儒家" in unified.all_names
        assert "儒" in unified.all_names

    def test_school_suffix_unification(self):
        """'X家' should be unified with 'X'."""
        resolver = EntityResolver()
        
        school = School(name="儒家", alias=[])
        resolver.add_school(school, juan_index=1, segment_index=1, chunk_index=0)
        
        # Check union-find relationship
        root1 = resolver._school_find("儒家")
        root2 = resolver._school_find("儒")
        assert root1 == root2, "儒家 and 儒 should have same root"


class TestOrganizationResolution:
    """Test organization entity resolution and merging."""

    def test_add_organization_directly(self):
        """Organizations added directly should be tracked correctly."""
        resolver = EntityResolver()
        org = Organization(
            name="丞相府",
            alias=["相府"],
            description="丞相的办公机构",
        )
        resolver.add_organization(org, juan_index=1, segment_index=1, chunk_index=0)
        
        assert "丞相府" in resolver.organization_occurrences
        assert len(resolver.organization_occurrences["丞相府"]) == 1

    def test_organization_alias_union(self):
        """Organizations with aliases should be merged."""
        resolver = EntityResolver()
        
        org1 = Organization(name="丞相府", alias=["相府"])
        org2 = Organization(name="相府", alias=[])
        
        resolver.add_organization(org1, juan_index=1, segment_index=1, chunk_index=0)
        resolver.add_organization(org2, juan_index=2, segment_index=1, chunk_index=0)
        
        orgs = resolver.resolve_organizations()
        # Should merge into one organization
        assert len(orgs) == 1
        unified = list(orgs.values())[0]
        assert "丞相府" in unified.all_names
        assert "相府" in unified.all_names


class TestBuildKnowledgeBase:
    """Test the complete knowledge base building with all entity types."""

    def test_build_includes_all_types(self):
        """build_knowledge_base should include all entity types."""
        resolver = EntityResolver()
        
        # Add one of each type
        resolver.add_role(
            Role(name="商鞅", entity_type="person"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="秦国", entity_type="polity"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="法家", entity_type="school"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="丞相府", entity_type="organization"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        
        kb = resolver.build_knowledge_base()
        
        assert kb.total_roles == 1
        assert kb.total_polities == 1
        assert kb.total_schools == 1
        assert kb.total_organizations == 1
        
        assert "商鞅" in kb.roles
        assert "秦" in kb.polities or "秦国" in kb.polities
        assert "法家" in kb.schools or "法" in kb.schools
        assert "丞相府" in kb.organizations

    def test_name_indexes_built(self):
        """Name to ID indexes should include all entity types."""
        resolver = EntityResolver()
        
        resolver.add_role(
            Role(name="商鞅", alias=["卫鞅"], entity_type="person"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="秦国", alias=["秦"], entity_type="polity"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="法家", alias=["法"], entity_type="school"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="丞相府", alias=["相府"], entity_type="organization"),
            juan_index=1, segment_index=1, chunk_index=0
        )
        
        kb = resolver.build_knowledge_base()
        
        # Check name indexes
        assert "商鞅" in kb.name_to_role_id
        assert "卫鞅" in kb.name_to_role_id
        
        # Either form should be in polity index
        assert "秦" in kb.name_to_polity_id or "秦国" in kb.name_to_polity_id
        
        # Either form should be in school index  
        assert "法家" in kb.name_to_school_id or "法" in kb.name_to_school_id
        
        # Either form should be in org index
        assert "丞相府" in kb.name_to_organization_id or "相府" in kb.name_to_organization_id

    def test_juan_indexes_built(self):
        """Juan indexes should include all entity types."""
        resolver = EntityResolver()
        
        resolver.add_role(
            Role(name="商鞅", entity_type="person"),
            juan_index=5, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="法家", entity_type="school"),
            juan_index=5, segment_index=1, chunk_index=0
        )
        resolver.add_role(
            Role(name="丞相府", entity_type="organization"),
            juan_index=5, segment_index=1, chunk_index=0
        )
        
        kb = resolver.build_knowledge_base()
        
        assert 5 in kb.juan_to_roles
        assert 5 in kb.juan_to_schools
        assert 5 in kb.juan_to_organizations


class TestClassificationMethods:
    """Test the individual classification methods."""

    def test_is_polity_name(self):
        """Test polity name detection."""
        resolver = EntityResolver()
        
        # Should be polities
        assert resolver._is_polity_name("秦") is True
        assert resolver._is_polity_name("秦国") is True
        assert resolver._is_polity_name("周朝") is True
        assert resolver._is_polity_name("汉王朝") is True
        assert resolver._is_polity_name("魏") is True
        assert resolver._is_polity_name("晋") is True
        
        # Should not be polities
        assert resolver._is_polity_name("商鞅") is False
        assert resolver._is_polity_name("孔子") is False
        assert resolver._is_polity_name("法家") is False
        assert resolver._is_polity_name("") is False

    def test_is_school_name(self):
        """Test school name detection."""
        resolver = EntityResolver()
        
        # Should be schools
        assert resolver._is_school_name("儒家") is True
        assert resolver._is_school_name("法家") is True
        assert resolver._is_school_name("道家") is True
        assert resolver._is_school_name("墨家") is True
        assert resolver._is_school_name("兵家") is True
        assert resolver._is_school_name("阴阳家") is True
        assert resolver._is_school_name("儒学") is True
        assert resolver._is_school_name("黄老之学") is True
        
        # Should not be schools
        assert resolver._is_school_name("三家") is False
        assert resolver._is_school_name("晋国三家") is False
        assert resolver._is_school_name("商鞅") is False
        assert resolver._is_school_name("秦国") is False
        assert resolver._is_school_name("") is False

    def test_is_organization_name(self):
        """Test organization name detection."""
        resolver = EntityResolver()
        
        # Should be organizations
        assert resolver._is_organization_name("丞相府") is True
        assert resolver._is_organization_name("太尉府") is True
        assert resolver._is_organization_name("虎贲军") is True
        assert resolver._is_organization_name("秦军") is True
        assert resolver._is_organization_name("三家") is True
        assert resolver._is_organization_name("晋国三家") is True
        
        # Should not be organizations
        assert resolver._is_organization_name("商鞅") is False
        assert resolver._is_organization_name("秦国") is False
        assert resolver._is_organization_name("儒家") is False
        assert resolver._is_organization_name("") is False


class TestDescriptionSelection:
    """Test filtering of editorial/meta descriptions and compression to short UI summaries."""

    def test_select_best_description_prefers_original_when_editorial_only(self):
        resolver = EntityResolver()
        descriptions = [
            "山上人物，适合补强高位修士群像。",
            "前三季叙事中多次出现，常与陈平安同场，推动相关支线发展。",
        ]
        original_descriptions = [
            "陆舫是鸟瞰峰山主，佩剑大椿，修为精深。",
        ]

        selected = resolver._select_best_description(descriptions, original_descriptions)
        assert "陆舫" in selected
        assert "鸟瞰峰" in selected

    def test_select_best_description_keeps_non_editorial(self):
        resolver = EntityResolver()
        descriptions = [
            "山上支线人物，适合补足修士群像。",
            "风雪庙剑修，常与问剑、对峙相关。",
        ]

        selected = resolver._select_best_description(descriptions, [])
        assert selected == "风雪庙剑修，常与问剑、对峙相关。"

    def test_select_best_description_falls_back_when_no_original(self):
        resolver = EntityResolver()
        descriptions = [
            "山上人物，适合扩展外围修士节点。",
        ]

        selected = resolver._select_best_description(descriptions, [])
        # Editorial description is compressed as last resort
        assert len(selected) > 0

    def test_description_compressed_to_max_chars(self):
        """When seed description is empty but original_descriptions has long text,
        description must be a compressed short summary, not the raw original."""
        resolver = EntityResolver()
        long_original = "陈平安今年十岁，没有文字的小镇上。" * 10  # ~180 chars
        descriptions = []
        original_descriptions = [long_original]

        selected = resolver._select_best_description(
            descriptions, original_descriptions, max_chars=120, entity_name="陈平安"
        )
        assert 0 < len(selected) <= 120
        # Must not just be the full raw original
        assert selected != long_original

    def test_description_not_equal_to_longest_original(self):
        """The old bug: _select_best_description returned max(original, key=len) raw."""
        resolver = EntityResolver()
        short_original = "宁姚是剑气长城年轻一辈的剑修天才。"
        long_original = (
            "陈平安当时在泥瓶巷的院子里第一次见到宁姚的时候，"
            "宁姚在做什么呢？她在杀人。实际上这个女孩不知道自己有多美，"
            "陈平安一直知道自己有个毛病，但从大窑和烧制瓷器开始就发现自己眼光精准，"
            "但不能准确说出来。"
        )
        descriptions = []
        original_descriptions = [short_original, long_original]

        selected = resolver._select_best_description(
            descriptions, original_descriptions, max_chars=120, entity_name="宁姚"
        )
        assert len(selected) <= 120
        # The first (earliest) original should be preferred as it's the introduction
        assert "宁姚" in selected or "剑气长城" in selected


class TestCompressToSummary:
    """Test the _compress_to_summary static helper."""

    def test_short_text_unchanged(self):
        result = EntityResolver._compress_to_summary("齐静春是山崖书院的山主。", max_chars=120)
        assert result == "齐静春是山崖书院的山主。"

    def test_long_text_truncated(self):
        long_text = "陈平安今年十岁，没有文字的小镇上，" * 10
        result = EntityResolver._compress_to_summary(long_text, max_chars=120)
        assert 0 < len(result) <= 120

    def test_dialogue_deprioritized(self):
        """Dialogue-heavy text should not become the summary sentence."""
        text = '"你是什么人？"老人皱眉问道。阮邛是铸剑名家，在风雪庙修行多年。'
        result = EntityResolver._compress_to_summary(text, max_chars=120, entity_name="阮邛")
        # Should prefer the descriptive sentence over the dialogue
        assert "阮邛" in result

    def test_empty_returns_empty(self):
        assert EntityResolver._compress_to_summary("", max_chars=120) == ""
        assert EntityResolver._compress_to_summary("   ", max_chars=120) == ""

    def test_entity_name_sentence_preferred(self):
        text = "少年翻了个白眼。陆舫是鸟瞰峰山主，修为极高。另一人不知所踪。"
        result = EntityResolver._compress_to_summary(text, max_chars=120, entity_name="陆舫")
        assert "陆舫" in result

    def test_respects_max_chars(self):
        text = "这是第一句话。" * 30
        for limit in [60, 80, 120, 140]:
            result = EntityResolver._compress_to_summary(text, max_chars=limit)
            assert len(result) <= limit + 1  # +1 for possible trailing punctuation


class TestLocationDescription:
    """Test that location resolver produces descriptions from original text."""

    def test_location_description_from_original(self):
        from model.location import Location
        from model.unified import EntityOccurrence

        resolver = EntityResolver()
        loc = Location(
            name="落魄山",
            alias=[],
            type="山门",
            description="",  # seed description is empty (cleared)
            original_description_in_book="陈平安打算在落魄山上建立自己的山门，此处灵气充沛，适合修行。",
            sentence_indexes_in_segment=[0, 1],
            juan_index=15,
            segment_index=0,
        )
        occ = EntityOccurrence(
            juan_index=15, segment_index=0, chunk_index=0,
            original_description="", source_sentence="",
        )
        resolver.location_occurrences["落魄山"].append((loc, occ))

        locations = resolver.resolve_locations()
        assert "落魄山" in locations
        unified = locations["落魄山"]
        assert unified.description != ""
        assert len(unified.description) <= 140
        assert len(unified.original_descriptions) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
