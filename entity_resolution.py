"""
Entity Resolution: Merge duplicate entities across extractions.

This module provides the core logic for:
1. Detecting duplicate entities (by name, alias, context)
2. Merging entity information from multiple occurrences
3. Building a unified knowledge base from raw extractions
"""

import json
import re
from collections import defaultdict
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from datetime import datetime

from model.role import Role
from model.polity import Polity
from model.school import School
from model.organization import Organization
from model.location import Location
from model.event import Event
from model.action import Action
from model.unified import (
    UnifiedRole, UnifiedPolity, UnifiedSchool, UnifiedOrganization,
    UnifiedLocation, UnifiedEvent, UnifiedRelation,
    UnifiedKnowledgeBase, EntityOccurrence
)


class EntityResolver:
    """
    Resolves and merges duplicate entities across all extractions.
    
    Strategy:
    1. Build name->aliases mapping from all occurrences
    2. Use Union-Find to group entities that share names/aliases
    3. Merge grouped entities into canonical UnifiedRole/UnifiedLocation
    
    Safeguards against over-merging:
    - Block generic/ambiguous aliases (大王, 王, 臣, etc.)
    - Block ambiguous ruler titles (秦王, 楚王 - refer to multiple people over time)
    - Prevent person-country confusion (赵籍 ≠ 赵国)
    - Cap maximum group size to prevent runaway merging
    """
    
    # Generic terms that should NEVER be used as merge keys
    # These are contextual references, not true aliases
    BLOCKED_ALIASES: Set[str] = {
        # Generic titles/honorifics
        "大王", "王", "臣", "寡人", "君", "君主", "国君", "君王",
        "太子", "世子", "公子", "王子", "皇子",
        "皇帝", "天子", "陛下", "主公", "主上", "主君",
        "将军", "丞相", "相国", "太后", "皇后", "夫人",
        "先帝", "先王", "真人", "始皇", "始皇帝",
        # Family/relationship terms
        "弟弟", "兄弟", "父亲", "母亲", "儿子", "女儿",
        "叔父", "伯父", "舅舅", "侄子", "外甥",
        # Generic role descriptors
        "使者", "使臣", "谋士", "谋臣", "大臣", "臣子",
        "百姓", "老百姓", "人民", "民众", "众人",
        "敌人", "敌军", "我军", "军队", "士兵", "士卒",
        "宾客", "客", "士", "朕",
        # Pronouns and references
        "您", "他", "她", "我", "吾", "余", "予",
        "此人", "其人", "何人", "某人",
        # Other ambiguous terms
        "领导国家提倡礼义者", "治理国家的君主", "发表评论者", "评论者",
        "先生", "掌教", "掌教真人", "真人", "道人", "老道人", "年轻道人",
        "少年", "少女", "男人", "女人", "老人", "老前辈", "国师",
        # Ambiguous ruler titles (refer to different people at different times)
        "秦王", "楚王", "齐王", "赵王", "魏王", "韩王", "燕王",
        "周王", "晋王", "宋王", "鲁王",
        "秦君", "楚君", "齐君", "赵君", "魏君", "韩君", "燕君",
    }
    
    # Country/state names - these should not be aliases for persons
    # A person can BELONG to a country (power field), but is not THE country
    COUNTRY_NAMES: Set[str] = {
        # Major states
        "赵", "魏", "韩", "秦", "楚", "齐", "燕",
        "赵国", "魏国", "韩国", "秦国", "楚国", "齐国", "燕国",
        "周", "周朝", "周王朝", "东周", "西周",
        "晋", "晋国", "宋", "宋国", "鲁", "鲁国",
        "卫", "卫国", "郑", "郑国", "陈", "陈国",
        "蔡", "蔡国", "曹", "曹国", "许", "许国",
        "吴", "吴国", "越", "越国",
        # Collective references
        "三晋", "六国", "诸侯", "诸侯国",
        # Other political entities
        "匈奴", "义渠", "中山", "中山国",
    }

    # Common dynasty/state names not covered above (appears later than Warring States)
    POLITY_EXTRA_NAMES: Set[str] = {
        "汉", "唐", "宋", "元", "明", "清",
        "魏", "蜀", "吴", "晋", "隋",
    }

    # School/ideology names (philosophical schools)
    SCHOOL_NAMES: Set[str] = {
        "儒家", "法家", "道家", "墨家", "兵家", "名家", "阴阳家",
        "纵横家", "杂家", "农家", "小说家", "黄老之学", "儒学",
        "儒", "法", "道", "墨", "兵", "名", "阴阳", "纵横",
    }

    # Organization / official-title patterns
    ORGANIZATION_NAMES: Set[str] = {
        "丞相府", "太尉", "太尉府", "御史大夫", "廷尉", "少府",
        "诸侯", "三公", "九卿", "郎中令", "卫尉", "光禄勋",
        "三家",
    }
    
    # Maximum number of names allowed in a single merged group
    # If exceeded, the group is likely incorrectly merged
    MAX_GROUP_SIZE: int = 15
    
    def __init__(self):
        self.segment_year_index: Dict[str, int] = {}
        self.segment_progress_index: Dict[str, int] = {}
        self.segment_progress_labels: Dict[str, str] = {}
        self.book_metadata: Dict[str, str] = {
            "book_id": "swordcoming",
            "unit_label": "章节",
            "progress_label": "叙事进度",
        }
        self.manual_overrides: Dict[str, object] = {}
        self.blocked_aliases: Set[str] = set(self.BLOCKED_ALIASES)
        # Union-Find structure for entity grouping
        self.parent: Dict[str, str] = {}

        # Separate Union-Find for polities
        self.polity_parent: Dict[str, str] = {}
        self.polity_group_size: Dict[str, int] = defaultdict(lambda: 1)
        
        # Track group sizes to prevent runaway merging
        self.group_size: Dict[str, int] = defaultdict(lambda: 1)
        
        # Name -> all occurrences of entities with that name
        self.role_occurrences: Dict[str, List[Tuple[Role, EntityOccurrence]]] = defaultdict(list)
        self.polity_occurrences: Dict[str, List[Tuple[Polity, EntityOccurrence]]] = defaultdict(list)
        self.school_occurrences: Dict[str, List[Tuple[School, EntityOccurrence]]] = defaultdict(list)
        self.organization_occurrences: Dict[str, List[Tuple[Organization, EntityOccurrence]]] = defaultdict(list)
        self.location_occurrences: Dict[str, List[Tuple[Location, EntityOccurrence]]] = defaultdict(list)
        
        # Union-Find for schools and organizations
        self.school_parent: Dict[str, str] = {}
        self.school_group_size: Dict[str, int] = defaultdict(lambda: 1)
        self.organization_parent: Dict[str, str] = {}
        self.organization_group_size: Dict[str, int] = defaultdict(lambda: 1)
        
        # Event merging by name
        self.event_occurrences: Dict[str, List[Tuple[Event, int, int]]] = defaultdict(list)
        
        # Relation aggregation
        self.relation_pairs: Dict[str, List[Action]] = defaultdict(list)

    def set_segment_year_index(self, segment_year_index: Dict[str, int]) -> None:
        """Provide a mapping like {'juan-seg': year} for numeric-year derivation."""
        self.segment_year_index = dict(segment_year_index)

    def set_segment_progress_index(
        self,
        segment_progress_index: Dict[str, int],
        segment_progress_labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Provide a mapping like {'unit-seg': progress_index} for generic timelines."""
        self.segment_progress_index = dict(segment_progress_index)
        self.segment_progress_labels = dict(segment_progress_labels or {})

    def set_book_metadata(self, *, book_id: str, unit_label: str, progress_label: str) -> None:
        self.book_metadata = {
            "book_id": book_id,
            "unit_label": unit_label,
            "progress_label": progress_label,
        }

    def set_manual_overrides(self, overrides: Dict[str, object]) -> None:
        self.manual_overrides = dict(overrides)
        blocked = overrides.get("blocked_aliases", []) if isinstance(overrides, dict) else []
        if isinstance(blocked, list):
            self.blocked_aliases = set(self.BLOCKED_ALIASES).union(
                {str(item).strip() for item in blocked if str(item).strip()}
            )
    
    def _find(self, x: str) -> str:
        """Union-Find: find root with path compression."""
        if x not in self.parent:
            self.parent[x] = x
        if self.parent[x] != x:
            self.parent[x] = self._find(self.parent[x])
        return self.parent[x]

    def _polity_find(self, x: str) -> str:
        if x not in self.polity_parent:
            self.polity_parent[x] = x
        if self.polity_parent[x] != x:
            self.polity_parent[x] = self._polity_find(self.polity_parent[x])
        return self.polity_parent[x]

    def _polity_union(self, x: str, y: str) -> bool:
        px, py = self._polity_find(x), self._polity_find(y)
        if px != py:
            new_size = self.polity_group_size[px] + self.polity_group_size[py]
            if new_size > self.MAX_GROUP_SIZE:
                return False
            if len(px) <= len(py):
                self.polity_parent[py] = px
                self.polity_group_size[px] = new_size
            else:
                self.polity_parent[px] = py
                self.polity_group_size[py] = new_size
        return True

    def _school_find(self, x: str) -> str:
        if x not in self.school_parent:
            self.school_parent[x] = x
        if self.school_parent[x] != x:
            self.school_parent[x] = self._school_find(self.school_parent[x])
        return self.school_parent[x]

    def _school_union(self, x: str, y: str) -> bool:
        px, py = self._school_find(x), self._school_find(y)
        if px != py:
            new_size = self.school_group_size[px] + self.school_group_size[py]
            if new_size > self.MAX_GROUP_SIZE:
                return False
            if len(px) <= len(py):
                self.school_parent[py] = px
                self.school_group_size[px] = new_size
            else:
                self.school_parent[px] = py
                self.school_group_size[py] = new_size
        return True

    def _organization_find(self, x: str) -> str:
        if x not in self.organization_parent:
            self.organization_parent[x] = x
        if self.organization_parent[x] != x:
            self.organization_parent[x] = self._organization_find(self.organization_parent[x])
        return self.organization_parent[x]

    def _organization_union(self, x: str, y: str) -> bool:
        px, py = self._organization_find(x), self._organization_find(y)
        if px != py:
            new_size = self.organization_group_size[px] + self.organization_group_size[py]
            if new_size > self.MAX_GROUP_SIZE:
                return False
            if len(px) <= len(py):
                self.organization_parent[py] = px
                self.organization_group_size[px] = new_size
            else:
                self.organization_parent[px] = py
                self.organization_group_size[py] = new_size
        return True

    def _is_polity_name(self, name: str) -> bool:
        name_norm = name.strip()
        if not name_norm:
            return False

        if name_norm in self.COUNTRY_NAMES or name_norm in self.POLITY_EXTRA_NAMES:
            return True

        # Strong suffix signals
        if name_norm.endswith("国") and len(name_norm) <= 4:
            return True
        if name_norm.endswith("朝") and len(name_norm) <= 4:
            return True
        if name_norm.endswith("王朝") and len(name_norm) <= 6:
            return True

        return False

    def _is_school_name(self, name: str) -> bool:
        """Check if name represents a school/ideology (e.g. 儒家, 法家)."""
        name_norm = name.strip()
        if not name_norm:
            return False

        if name_norm in self.SCHOOL_NAMES:
            return True

        # Exclude numeric-clan patterns like "晋国三家" / "魏三家" / "三家" etc.
        if re.search(r"[一二三四五六七八九十百千两]家$", name_norm):
            return False

        # Suffix pattern: X家 where X is 1-2 chars (儒家/法家/阴阳家)
        if name_norm.endswith("家") and 2 <= len(name_norm) <= 4:
            return True

        # Suffix pattern: X学 (儒学/黄老之学)
        if name_norm.endswith("学") and len(name_norm) <= 6:
            return True

        return False

    def _is_organization_name(self, name: str) -> bool:
        """Check if name represents an organization/official-title/group."""
        name_norm = name.strip()
        if not name_norm:
            return False

        if name_norm in self.ORGANIZATION_NAMES:
            return True

        # Suffix patterns for organizations
        if name_norm.endswith("府") and len(name_norm) <= 5:
            return True
        if name_norm.endswith("军") and len(name_norm) <= 4:
            return True

        # Numeric-clan patterns like "晋国三家" / "三家"
        if re.search(r"[一二三四五六七八九十百千两]家$", name_norm):
            return True

        return False
    
    def _union(self, x: str, y: str) -> bool:
        """
        Union-Find: merge two sets.
        
        Returns True if merge was successful, False if blocked due to size limit.
        """
        px, py = self._find(x), self._find(y)
        if px != py:
            # Check if merging would exceed group size limit
            new_size = self.group_size[px] + self.group_size[py]
            if new_size > self.MAX_GROUP_SIZE:
                # Don't merge - would create too large a group
                return False
            
            # Prefer shorter/simpler name as root
            if len(px) <= len(py):
                self.parent[py] = px
                self.group_size[px] = new_size
            else:
                self.parent[px] = py
                self.group_size[py] = new_size
        return True
    
    def _is_valid_alias_for_person(self, name: str, alias: str) -> bool:
        """
        Check if an alias is valid for merging with a person entity.
        
        Filters out:
        - Generic/ambiguous terms (大王, 臣, etc.)
        - Country names when the entity appears to be a person
        """
        alias_norm = alias.strip()
        
        # Block generic terms
        if alias_norm in self.blocked_aliases:
            return False
        
        # Block country names as person aliases
        # Exception: if the name itself contains the country (e.g., 赵王), allow it
        if alias_norm in self.COUNTRY_NAMES:
            # Check if name clearly indicates this IS a country/state entity
            name_is_country = name in self.COUNTRY_NAMES or name.endswith("国")
            if not name_is_country:
                return False
        
        # Block single-character aliases that are too ambiguous
        # Exception: actual single-character names are fine (e.g., 商鞅's 鞅)
        if len(alias_norm) == 1 and alias_norm in self.COUNTRY_NAMES:
            return False
        
        return True
    
    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for comparison."""
        # Remove common suffixes/prefixes that don't affect identity
        name = name.strip()
        # Could add more normalization rules specific to Chinese historical names
        return name

    def _select_preferred_role_name(self, name_group: Set[str]) -> str:
        overrides = self.manual_overrides.get("canonical_role_names", {}) if isinstance(self.manual_overrides, dict) else {}
        if isinstance(overrides, dict):
            for candidate in name_group:
                preferred = overrides.get(candidate)
                if preferred and preferred in name_group:
                    return preferred

            preferred_values = [value for value in overrides.values() if value in name_group]
            if preferred_values:
                return sorted(preferred_values, key=lambda value: (len(value), value))[0]

        def primary_name_mentions(candidate: str) -> int:
            return sum(
                1
                for role, _ in self.role_occurrences.get(candidate, [])
                if self._normalize_name(role.name) == candidate
            )

        def total_mentions(candidate: str) -> int:
            return len(self.role_occurrences.get(candidate, []))

        return sorted(
            name_group,
            key=lambda candidate: (
                -primary_name_mentions(candidate),
                -total_mentions(candidate),
                len(candidate),
                candidate,
            ),
        )[0]
    
    def add_role(self, role: Role, juan_index: int, segment_index: int, 
                 chunk_index: int, source_sentence: str = "") -> None:
        """Add a role occurrence for later resolution.
        
        Entity type routing priority:
        1. If role.entity_type is explicitly set (by LLM), use that
        2. Otherwise, apply heuristic classification based on name patterns
        """
        occurrence = EntityOccurrence(
            juan_index=juan_index,
            segment_index=segment_index,
            chunk_index=chunk_index,
            sentence_indexes=role.sentence_indexes_in_segment,
            original_description=role.original_description_in_book,
            source_sentence=source_sentence
        )
        
        name = self._normalize_name(role.name)

        # Check entity_type field first (LLM-provided classification)
        entity_type = getattr(role, 'entity_type', 'person')
        
        if entity_type == 'polity':
            polity = Polity(
                name=role.name,
                alias=list(role.alias),
                original_description_in_book=role.original_description_in_book,
                description=role.description,
                sentence_indexes_in_segment=role.sentence_indexes_in_segment,
                juan_index=role.juan_index,
                segment_index=role.segment_index,
            )
            self.add_polity(polity, juan_index, segment_index, chunk_index, source_sentence)
            return
        elif entity_type == 'school':
            school = School(
                name=role.name,
                alias=list(role.alias),
                original_description_in_book=role.original_description_in_book,
                description=role.description,
                sentence_indexes_in_segment=role.sentence_indexes_in_segment,
                juan_index=role.juan_index,
                segment_index=role.segment_index,
            )
            self.add_school(school, juan_index, segment_index, chunk_index, source_sentence)
            return
        elif entity_type == 'organization':
            organization = Organization(
                name=role.name,
                alias=list(role.alias),
                original_description_in_book=role.original_description_in_book,
                description=role.description,
                sentence_indexes_in_segment=role.sentence_indexes_in_segment,
                juan_index=role.juan_index,
                segment_index=role.segment_index,
            )
            self.add_organization(organization, juan_index, segment_index, chunk_index, source_sentence)
            return

        # Fallback heuristics for backward compatibility (when entity_type='person' or unset)
        # Reclassify polity-like extractions (e.g. 秦/秦国/汉/唐) into separate model
        if self._is_polity_name(name):
            polity = Polity(
                name=role.name,
                alias=list(role.alias),
                original_description_in_book=role.original_description_in_book,
                description=role.description,
                sentence_indexes_in_segment=role.sentence_indexes_in_segment,
                juan_index=role.juan_index,
                segment_index=role.segment_index,
            )
            self.add_polity(polity, juan_index, segment_index, chunk_index, source_sentence)
            return

        # Reclassify school-like extractions (e.g. 儒家/法家)
        if self._is_school_name(name):
            school = School(
                name=role.name,
                alias=list(role.alias),
                original_description_in_book=role.original_description_in_book,
                description=role.description,
                sentence_indexes_in_segment=role.sentence_indexes_in_segment,
                juan_index=role.juan_index,
                segment_index=role.segment_index,
            )
            self.add_school(school, juan_index, segment_index, chunk_index, source_sentence)
            return

        # Reclassify organization-like extractions (e.g. 丞相府)
        if self._is_organization_name(name):
            organization = Organization(
                name=role.name,
                alias=list(role.alias),
                original_description_in_book=role.original_description_in_book,
                description=role.description,
                sentence_indexes_in_segment=role.sentence_indexes_in_segment,
                juan_index=role.juan_index,
                segment_index=role.segment_index,
            )
            self.add_organization(organization, juan_index, segment_index, chunk_index, source_sentence)
            return
        
        # Skip if the primary name itself is a blocked/generic term
        # These entities should not participate in merging at all
        if name in self.blocked_aliases:
            # Still record the occurrence but don't merge
            self.role_occurrences[name].append((role, occurrence))
            return
        
        self.role_occurrences[name].append((role, occurrence))
        
        # Union name with valid aliases only
        for alias in role.alias:
            alias_norm = self._normalize_name(alias)
            if alias_norm and self._is_valid_alias_for_person(name, alias_norm):
                self._union(name, alias_norm)
                self.role_occurrences[alias_norm].append((role, occurrence))

    def add_polity(self, polity: Polity, juan_index: int, segment_index: int,
                   chunk_index: int, source_sentence: str = "") -> None:
        occurrence = EntityOccurrence(
            juan_index=juan_index,
            segment_index=segment_index,
            chunk_index=chunk_index,
            sentence_indexes=polity.sentence_indexes_in_segment,
            original_description=polity.original_description_in_book,
            source_sentence=source_sentence,
        )

        name = self._normalize_name(polity.name)
        self.polity_occurrences[name].append((polity, occurrence))
        for alias in polity.alias:
            alias_norm = self._normalize_name(alias)
            if alias_norm:
                self._polity_union(name, alias_norm)
                self.polity_occurrences[alias_norm].append((polity, occurrence))

        # Also unify common "X国" -> "X" form
        if name.endswith("国") and len(name) <= 4:
            base = name[:-1]
            if base:
                self._polity_union(name, base)

    def add_school(self, school: School, juan_index: int, segment_index: int,
                   chunk_index: int, source_sentence: str = "") -> None:
        """Add a school/ideology occurrence for later resolution."""
        occurrence = EntityOccurrence(
            juan_index=juan_index,
            segment_index=segment_index,
            chunk_index=chunk_index,
            sentence_indexes=school.sentence_indexes_in_segment,
            original_description=school.original_description_in_book,
            source_sentence=source_sentence,
        )

        name = self._normalize_name(school.name)
        self.school_occurrences[name].append((school, occurrence))
        for alias in school.alias:
            alias_norm = self._normalize_name(alias)
            if alias_norm:
                self._school_union(name, alias_norm)
                self.school_occurrences[alias_norm].append((school, occurrence))

        # Unify "X家" -> "X" form (e.g. 儒家 -> 儒)
        if name.endswith("家") and len(name) <= 4:
            base = name[:-1]
            if base:
                self._school_union(name, base)

    def add_organization(self, organization: Organization, juan_index: int, segment_index: int,
                         chunk_index: int, source_sentence: str = "") -> None:
        """Add an organization/official-title occurrence for later resolution."""
        occurrence = EntityOccurrence(
            juan_index=juan_index,
            segment_index=segment_index,
            chunk_index=chunk_index,
            sentence_indexes=organization.sentence_indexes_in_segment,
            original_description=organization.original_description_in_book,
            source_sentence=source_sentence,
        )

        name = self._normalize_name(organization.name)
        self.organization_occurrences[name].append((organization, occurrence))
        for alias in organization.alias:
            alias_norm = self._normalize_name(alias)
            if alias_norm:
                self._organization_union(name, alias_norm)
                self.organization_occurrences[alias_norm].append((organization, occurrence))
    
    def add_location(self, location: Location, juan_index: int, 
                     segment_index: int, chunk_index: int) -> None:
        """Add a location occurrence for later resolution."""
        occurrence = EntityOccurrence(
            juan_index=juan_index,
            segment_index=segment_index,
            chunk_index=chunk_index,
            sentence_indexes=location.sentence_indexes_in_segment,
            original_description=location.description
        )
        
        name = self._normalize_name(location.name)
        self.location_occurrences[name].append((location, occurrence))
        
        for alias in location.alias:
            alias_norm = self._normalize_name(alias)
            # For locations, we still block generic terms but allow country names
            if alias_norm and alias_norm not in self.BLOCKED_ALIASES:
                self._union(name, alias_norm)
                self.location_occurrences[alias_norm].append((location, occurrence))
    
    def add_event(self, event: Event, juan_index: int, segment_index: int) -> None:
        """Add an event occurrence for later merging.

        Events with the same name are merged only within the same juan (volume).
        Using a composite key ``"<name>@<juan_index>"`` prevents the mega-merge
        where a recurring event name (e.g. '阿良过境') collapses every occurrence
        across all 328 chapters into a single UnifiedEvent.
        """
        if event.name:
            key = f"{event.name}@{juan_index}"
            self.event_occurrences[key].append((event, juan_index, segment_index))
    
    @staticmethod
    def _canonical_relation_key(a: str, b: str) -> str:
        """Return a stable undirected key for the entity pair (a, b).

        The smaller name (lexicographic) is always placed first so that
        'A->B' and 'B->A' map to the same bucket, preventing the 252
        bidirectional-duplicate relations observed in the current output.
        """
        return f"{min(a, b)}->{max(a, b)}"

    def add_relation(self, action: Action) -> None:
        """Add a relation for later aggregation."""
        if action.is_commentary:
            return

        for from_role in action.from_roles:
            for to_role in action.to_roles:
                a = self._normalize_name(from_role)
                b = self._normalize_name(to_role)
                if not a or not b or a == b:
                    continue
                key = self._canonical_relation_key(a, b)
                self.relation_pairs[key].append(action)
    
    EDITORIAL_DESCRIPTION_PATTERNS: tuple[str, ...] = (
        '适合补强',
        '适合补足',
        '适合扩展',
        '适合增强',
        '可补足',
        '可补强',
        '可扩展',
        '可增强',
        '能补足',
        '能扩展',
        '能增强',
        '前三季叙事中多次出现',
        '山上线',
        '山上势力',
        '山上人物',
        '山上支线',
        '山上女性',
        '山上强者',
    )

    def _looks_editorial_description(self, text: str) -> bool:
        normalized = (text or '').strip()
        if not normalized:
            return False
        return any(pattern in normalized for pattern in self.EDITORIAL_DESCRIPTION_PATTERNS)

    def _select_best_description(self, descriptions: List[str], original_descriptions: Optional[List[str]] = None) -> str:
        """Select the most informative end-user-facing description.

        Prefer non-editorial descriptions; if all candidates look editorial,
        fall back to in-book original descriptions when available.
        """
        cleaned = [d.strip() for d in descriptions if d and d.strip()]
        cleaned_original = [d.strip() for d in (original_descriptions or []) if d and d.strip()]

        if not cleaned:
            return max(cleaned_original, key=len) if cleaned_original else ''

        non_editorial = [d for d in cleaned if not self._looks_editorial_description(d)]
        if non_editorial:
            return max(non_editorial, key=len)

        if cleaned_original:
            return max(cleaned_original, key=len)

        return max(cleaned, key=len)
    
    # Generic / category-level labels that should not be used as a role's
    # primary power when a more specific alternative exists.
    GENERIC_POWERS: set[str] = {
        '山上', '山下', '山水', '江湖', '道家', '武道', '未归类',
    }

    def _select_primary_power(self, powers: List[str]) -> Optional[str]:
        """Select the most common *specific* power affiliation.

        Prefers the most-frequent non-generic label.  Falls back to a
        generic label only when every occurrence is generic.
        """
        if not powers:
            return None
        power_counts: Dict[str, int] = defaultdict(int)
        for p in powers:
            if p:
                power_counts[p] += 1
        if not power_counts:
            return None
        # Try non-generic first
        concrete = {k: v for k, v in power_counts.items() if k not in self.GENERIC_POWERS}
        if concrete:
            return max(concrete, key=concrete.get)  # type: ignore[arg-type]
        return max(power_counts, key=power_counts.get)  # type: ignore[arg-type]
    
    def resolve_roles(self) -> Dict[str, UnifiedRole]:
        """Resolve all roles into unified entities."""
        # Group names by their Union-Find root
        groups: Dict[str, Set[str]] = defaultdict(set)
        for name in self.role_occurrences:
            root = self._find(name)
            groups[root].add(name)
        
        unified_roles: Dict[str, UnifiedRole] = {}
        
        for _, name_group in groups.items():
            canonical_name = self._select_preferred_role_name(name_group)
            if canonical_name in self.blocked_aliases:
                continue
            # Collect all occurrences for this entity group
            all_occurrences: List[EntityOccurrence] = []
            all_descriptions: List[str] = []
            all_original_descriptions: List[str] = []
            all_powers: List[str] = []
            all_names: Set[str] = set()
            juans_appeared: Set[int] = set()
            related_entities: Set[str] = set()
            
            for name in name_group:
                all_names.add(name)
                for role, occurrence in self.role_occurrences[name]:
                    all_occurrences.append(occurrence)
                    if role.description:
                        all_descriptions.append(role.description)
                    if role.original_description_in_book:
                        all_original_descriptions.append(role.original_description_in_book)
                    if role.power:
                        all_powers.append(role.power)
                    juans_appeared.add(occurrence.juan_index)
                    # Add aliases to all_names
                    for alias in role.alias:
                        all_names.add(alias)
            
            # Remove duplicates from original descriptions
            unique_original = list(dict.fromkeys(all_original_descriptions))
            
            # Create unified role
            unified = UnifiedRole(
                id=canonical_name,
                canonical_name=canonical_name,
                all_names=all_names,
                description=self._select_best_description(all_descriptions, unique_original),
                original_descriptions=unique_original[:10],  # Keep top 10
                powers=list(dict.fromkeys(all_powers)),  # Unique, preserve order
                primary_power=self._select_primary_power(all_powers),
                first_appearance_juan=min(juans_appeared) if juans_appeared else 0,
                last_appearance_juan=max(juans_appeared) if juans_appeared else 0,
                occurrences=all_occurrences,
                total_mentions=len(all_occurrences),
                juans_appeared=juans_appeared,
                units_appeared=juans_appeared,
                related_entities=related_entities
            )
            
            unified_roles[canonical_name] = unified
        
        return unified_roles
    
    def resolve_locations(self) -> Dict[str, UnifiedLocation]:
        """Resolve all locations into unified entities."""
        groups: Dict[str, Set[str]] = defaultdict(set)
        for name in self.location_occurrences:
            root = self._find(name)
            groups[root].add(name)
        
        unified_locations: Dict[str, UnifiedLocation] = {}
        
        for canonical_name, name_group in groups.items():
            all_occurrences: List[EntityOccurrence] = []
            all_names: Set[str] = set()
            all_types: List[str] = []
            all_descriptions: List[str] = []
            all_modern_names: List[str] = []
            coordinates = None
            associated_entities: Set[str] = set()
            juans_appeared: Set[int] = set()
            
            for name in name_group:
                all_names.add(name)
                for location, occurrence in self.location_occurrences[name]:
                    all_occurrences.append(occurrence)
                    juans_appeared.add(occurrence.juan_index)
                    if location.type:
                        all_types.append(location.type)
                    if location.description:
                        all_descriptions.append(location.description)
                    if location.modern_name:
                        all_modern_names.append(location.modern_name)
                    if location.coordinates and not coordinates:
                        coordinates = location.coordinates
                    for entity in location.related_entities:
                        associated_entities.add(entity)
                    for alias in location.alias:
                        all_names.add(alias)
            
            # Select most common type
            type_counts = defaultdict(int)
            for t in all_types:
                type_counts[t] += 1
            location_type = max(type_counts, key=type_counts.get) if type_counts else ""
            
            unified = UnifiedLocation(
                id=canonical_name,
                canonical_name=canonical_name,
                all_names=all_names,
                location_type=location_type,
                description=self._select_best_description(all_descriptions),
                modern_name=all_modern_names[0] if all_modern_names else "",
                coordinates=coordinates,
                associated_entities=associated_entities,
                occurrences=all_occurrences,
                total_mentions=len(all_occurrences),
                juans_appeared=juans_appeared,
                units_appeared=juans_appeared,
            )
            
            unified_locations[canonical_name] = unified
        
        return unified_locations

    def resolve_polities(self) -> Dict[str, UnifiedPolity]:
        unified_polities: Dict[str, UnifiedPolity] = {}

        # Group occurrences by union-find root
        groups: Dict[str, List[Tuple[Polity, EntityOccurrence]]] = defaultdict(list)
        for name, occurrences in self.polity_occurrences.items():
            root = self._polity_find(name)
            groups[root].extend(occurrences)

        for root_name, occurrences in groups.items():
            all_names: Set[str] = set()
            descriptions: List[str] = []
            original_descriptions: List[str] = []
            juans: Set[int] = set()
            occs: List[EntityOccurrence] = []

            for polity, occ in occurrences:
                all_names.add(self._normalize_name(polity.name))
                for a in polity.alias:
                    if a:
                        all_names.add(self._normalize_name(a))
                if polity.description:
                    descriptions.append(polity.description)
                if polity.original_description_in_book:
                    original_descriptions.append(polity.original_description_in_book)
                juans.add(occ.juan_index)
                occs.append(occ)

            canonical = min(all_names, key=len) if all_names else root_name
            unified_polities[canonical] = UnifiedPolity(
                id=canonical,
                canonical_name=canonical,
                all_names=all_names,
                description=self._select_best_description(descriptions),
                original_descriptions=list(dict.fromkeys(original_descriptions)),
                occurrences=occs,
                total_mentions=len(occs),
                juans_appeared=juans,
            )

        return unified_polities

    def resolve_schools(self) -> Dict[str, UnifiedSchool]:
        """Resolve all schools/ideologies into unified entities."""
        unified_schools: Dict[str, UnifiedSchool] = {}

        # Group occurrences by union-find root
        groups: Dict[str, List[Tuple[School, EntityOccurrence]]] = defaultdict(list)
        for name, occurrences in self.school_occurrences.items():
            root = self._school_find(name)
            groups[root].extend(occurrences)

        for root_name, occurrences in groups.items():
            all_names: Set[str] = set()
            descriptions: List[str] = []
            original_descriptions: List[str] = []
            juans: Set[int] = set()
            occs: List[EntityOccurrence] = []

            for school, occ in occurrences:
                all_names.add(self._normalize_name(school.name))
                for a in school.alias:
                    if a:
                        all_names.add(self._normalize_name(a))
                if school.description:
                    descriptions.append(school.description)
                if school.original_description_in_book:
                    original_descriptions.append(school.original_description_in_book)
                juans.add(occ.juan_index)
                occs.append(occ)

            canonical = min(all_names, key=len) if all_names else root_name
            unified_schools[canonical] = UnifiedSchool(
                id=canonical,
                canonical_name=canonical,
                all_names=all_names,
                description=self._select_best_description(descriptions),
                original_descriptions=list(dict.fromkeys(original_descriptions)),
                occurrences=occs,
                total_mentions=len(occs),
                juans_appeared=juans,
            )

        return unified_schools

    def resolve_organizations(self) -> Dict[str, UnifiedOrganization]:
        """Resolve all organizations/official-titles into unified entities."""
        unified_organizations: Dict[str, UnifiedOrganization] = {}

        # Group occurrences by union-find root
        groups: Dict[str, List[Tuple[Organization, EntityOccurrence]]] = defaultdict(list)
        for name, occurrences in self.organization_occurrences.items():
            root = self._organization_find(name)
            groups[root].extend(occurrences)

        for root_name, occurrences in groups.items():
            all_names: Set[str] = set()
            descriptions: List[str] = []
            original_descriptions: List[str] = []
            juans: Set[int] = set()
            occs: List[EntityOccurrence] = []

            for organization, occ in occurrences:
                all_names.add(self._normalize_name(organization.name))
                for a in organization.alias:
                    if a:
                        all_names.add(self._normalize_name(a))
                if organization.description:
                    descriptions.append(organization.description)
                if organization.original_description_in_book:
                    original_descriptions.append(organization.original_description_in_book)
                juans.add(occ.juan_index)
                occs.append(occ)

            canonical = min(all_names, key=len) if all_names else root_name
            unified_organizations[canonical] = UnifiedOrganization(
                id=canonical,
                canonical_name=canonical,
                all_names=all_names,
                description=self._select_best_description(descriptions),
                original_descriptions=list(dict.fromkeys(original_descriptions)),
                occurrences=occs,
                total_mentions=len(occs),
                juans_appeared=juans,
            )

        return unified_organizations
    
    def resolve_events(self) -> Dict[str, UnifiedEvent]:
        """Resolve events with the same name within the same juan.

        The internal key is ``"<event_name>@<juan_index>"``; the public ``name``
        field is restored to the original event name without the suffix.

        After all events are resolved this method also:
        - Picks the best provenance (earliest + highest match_score) for each
          event when multiple occurrences exist.
        - Computes whole-book frequency metadata: ``name_occurrence_count``,
          ``first_occurrence_unit`` and ``is_first_occurrence``.
        """
        unified_events: Dict[str, UnifiedEvent] = {}

        for event_key, occurrences in self.event_occurrences.items():
            # Strip the @juan suffix to recover the human-readable event name.
            if "@" in event_key:
                event_name, _juan_suffix = event_key.rsplit("@", 1)
            else:
                event_name = event_key
            all_participants: Set[str] = set()
            source_juans: Set[int] = set()
            source_segments: List[str] = []
            descriptions: List[str] = []
            backgrounds: List[str] = []
            significances: List[str] = []
            times: List[str] = []
            locations: List[str] = []
            progress_points: List[int] = []
            progress_labels: List[str] = []

            # Track the best provenance across occurrences:
            # prefer earliest juan first, then highest match-keyword count.
            best_evidence_excerpt = ""
            best_matched_keywords: List[str] = []
            best_matched_rule_name = ""
            best_evidence_sentence_indexes: List[int] = []
            _best_prov_key: tuple[int, int] = (10**9, 0)  # (juan_idx, -match_kw_count)

            for event, juan_idx, seg_idx in occurrences:
                all_participants.update(event.participants)
                source_juans.add(juan_idx)
                source_segments.append(f"{juan_idx}-{seg_idx}")
                if event.description:
                    descriptions.append(event.description)
                if event.background:
                    backgrounds.append(event.background)
                if event.significance:
                    significances.append(event.significance)
                if event.time:
                    times.append(event.time)
                if event.location:
                    locations.append(event.location)
                seg_key = f"{juan_idx}-{seg_idx}"
                progress = self.segment_progress_index.get(seg_key)
                if progress is not None:
                    progress_points.append(int(progress))
                label = self.segment_progress_labels.get(seg_key)
                if label:
                    progress_labels.append(label)

                # Pick best provenance (earliest juan, then most keywords)
                kw_count = len(getattr(event, "matched_keywords", None) or [])
                prov_key = (juan_idx, -kw_count)
                if prov_key < _best_prov_key:
                    _best_prov_key = prov_key
                    best_evidence_excerpt = getattr(event, "evidence_excerpt", "") or ""
                    best_matched_keywords = list(getattr(event, "matched_keywords", None) or [])
                    best_matched_rule_name = getattr(event, "matched_rule_name", "") or ""
                    best_evidence_sentence_indexes = list(getattr(event, "sentence_indexes_in_segment", None) or [])

            # Parse numeric time
            time_str = times[0] if times else None
            time_numeric = self._parse_year(time_str)

            # Impute numeric year from segment_year_index when missing
            imputed_years: List[int] = []
            if time_numeric is None:
                for _, juan_idx, seg_idx in occurrences:
                    seg_key = f"{juan_idx}-{seg_idx}"
                    year = self.segment_year_index.get(seg_key)
                    if year is not None:
                        imputed_years.append(int(year))
            
            unified = UnifiedEvent(
                id=event_key,
                name=event_name,
                time=time_str,
                time_text=time_str,
                time_start=time_numeric,
                time_end=time_numeric,
                progress_start=min(progress_points) if progress_points else None,
                progress_end=max(progress_points) if progress_points else None,
                progress_label=progress_labels[0] if progress_labels else None,
                imputed_time_start=min(imputed_years) if imputed_years else None,
                imputed_time_end=max(imputed_years) if imputed_years else None,
                location=locations[0] if locations else None,
                participants=all_participants,
                description=self._select_best_description(descriptions),
                background=self._select_best_description(backgrounds),
                significance=self._select_best_description(significances),
                source_juans=source_juans,
                source_units=source_juans,
                source_segments=source_segments,
                action_count=len(occurrences),
                # Provenance
                evidence_excerpt=best_evidence_excerpt,
                matched_keywords=best_matched_keywords,
                matched_rule_name=best_matched_rule_name,
                evidence_sentence_indexes=best_evidence_sentence_indexes,
            )

            if event_name not in unified_events:
                unified_events[event_name] = unified
            else:
                unified_events[event_key] = unified

        # --- Whole-book frequency metadata ---
        # Count how many distinct event_ids share each event name.
        name_counts: Dict[str, int] = {}
        name_first_unit: Dict[str, int] = {}
        for ue in unified_events.values():
            name_counts[ue.name] = name_counts.get(ue.name, 0) + 1
            first_unit = min(ue.source_units) if ue.source_units else None
            if first_unit is not None:
                prev = name_first_unit.get(ue.name)
                if prev is None or first_unit < prev:
                    name_first_unit[ue.name] = first_unit

        for ue in unified_events.values():
            ue.name_occurrence_count = name_counts.get(ue.name, 1)
            ue.first_occurrence_unit = name_first_unit.get(ue.name)
            first_unit = min(ue.source_units) if ue.source_units else None
            ue.is_first_occurrence = (
                first_unit is not None
                and first_unit == name_first_unit.get(ue.name)
            )

        return unified_events
    
    def resolve_relations(self) -> Dict[str, UnifiedRelation]:
        """Aggregate relations between entity pairs."""
        unified_relations: Dict[str, UnifiedRelation] = {}
        
        for pair_key, actions in self.relation_pairs.items():
            # pair_key is always "<min_name>-><max_name>" (canonical order)
            from_entity, to_entity = pair_key.split("->")
            
            action_types: List[str] = []
            contexts: List[str] = []
            source_juans: Set[int] = set()
            times: List[str] = []
            years: List[int] = []
            progress_points: List[int] = []
            progress_labels: List[str] = []
            
            for action in actions:
                if action.action:
                    action_types.append(action.action)
                if action.context:
                    contexts.append(action.context)
                source_juans.add(action.juan_index)
                if action.time:
                    times.append(action.time)

                year = self._parse_year(action.time)
                if year is None:
                    seg_key = f"{action.juan_index}-{action.segment_index}"
                    year = self.segment_year_index.get(seg_key)
                if year is not None:
                    years.append(int(year))
                seg_key = f"{action.juan_index}-{action.segment_index}"
                progress = self.segment_progress_index.get(seg_key)
                if progress is not None:
                    progress_points.append(int(progress))
                label = self.segment_progress_labels.get(seg_key)
                if label:
                    progress_labels.append(label)
            
            # Find most common action type
            action_counts = defaultdict(int)
            for a in action_types:
                action_counts[a] += 1
            primary_action = max(action_counts, key=action_counts.get) if action_counts else ""
            
            unified = UnifiedRelation(
                id=pair_key,
                from_entity=from_entity,
                to_entity=to_entity,
                action_types=list(dict.fromkeys(action_types)),  # Unique, preserve order
                primary_action=primary_action,
                interaction_count=len(actions),
                first_interaction_time=times[0] if times else None,
                last_interaction_time=times[-1] if len(times) > 1 else None,
                first_interaction_text=times[0] if times else None,
                last_interaction_text=times[-1] if len(times) > 1 else None,
                progress_start=min(progress_points) if progress_points else None,
                progress_end=max(progress_points) if progress_points else None,
                progress_label=progress_labels[0] if progress_labels else None,
                first_interaction_year=min(years) if years else None,
                last_interaction_year=max(years) if years else None,
                contexts=contexts[:5],  # Keep top 5 contexts
                source_juans=source_juans,
                source_units=source_juans,
            )
            
            unified_relations[pair_key] = unified
        
        return unified_relations
    
    def _parse_year(self, time_str: Optional[str]) -> Optional[int]:
        """Parse Chinese year format to numeric value."""
        if not time_str:
            return None

        # BCE: "公元前403" or "前403" (including inside parentheses)
        bc_match = re.search(r'公元前\s*(\d+)', time_str)
        if bc_match:
            return -int(bc_match.group(1))

        bc_match = re.search(r'前\s*(\d+)', time_str)
        if bc_match:
            return -int(bc_match.group(1))

        # CE explicit: "公元655年"
        ad_match = re.search(r'公元\s*(\d+)', time_str)
        if ad_match:
            return int(ad_match.group(1))

        # Common dataset format: "（...、3）", "（...、116）" etc
        paren_match = re.search(r'[（(][^）)]*?[、，,]\s*(\d{1,4})\s*(?:年)?\s*[）)]', time_str)
        if paren_match:
            return int(paren_match.group(1))

        return None
    
    def build_knowledge_base(self) -> UnifiedKnowledgeBase:
        """Build the complete unified knowledge base."""
        roles = self.resolve_roles()
        polities = self.resolve_polities()
        schools = self.resolve_schools()
        organizations = self.resolve_organizations()
        locations = self.resolve_locations()
        events = self.resolve_events()
        relations = self.resolve_relations()
        
        # Build indexes
        name_to_role_id: Dict[str, str] = {}
        for role_id, role in roles.items():
            for name in role.all_names:
                name_to_role_id[name] = role_id
        
        name_to_location_id: Dict[str, str] = {}
        for loc_id, loc in locations.items():
            for name in loc.all_names:
                name_to_location_id[name] = loc_id

        name_to_polity_id: Dict[str, str] = {}
        for polity_id, polity in polities.items():
            for name in polity.all_names:
                name_to_polity_id[name] = polity_id

        name_to_school_id: Dict[str, str] = {}
        for school_id, school in schools.items():
            for name in school.all_names:
                name_to_school_id[name] = school_id

        name_to_organization_id: Dict[str, str] = {}
        for org_id, org in organizations.items():
            for name in org.all_names:
                name_to_organization_id[name] = org_id
        
        # Power index
        power_to_roles: Dict[str, List[str]] = defaultdict(list)
        for role_id, role in roles.items():
            if role.primary_power:
                power_to_roles[role.primary_power].append(role_id)
        
        # Juan index
        juan_to_roles: Dict[int, List[str]] = defaultdict(list)
        for role_id, role in roles.items():
            for juan in role.juans_appeared:
                juan_to_roles[juan].append(role_id)
        
        juan_to_events: Dict[int, List[str]] = defaultdict(list)
        for event_id, event in events.items():
            for juan in event.source_juans:
                juan_to_events[juan].append(event_id)

        juan_to_polities: Dict[int, List[str]] = defaultdict(list)
        for polity_id, polity in polities.items():
            for juan in polity.juans_appeared:
                juan_to_polities[juan].append(polity_id)

        juan_to_schools: Dict[int, List[str]] = defaultdict(list)
        for school_id, school in schools.items():
            for juan in school.juans_appeared:
                juan_to_schools[juan].append(school_id)

        juan_to_organizations: Dict[int, List[str]] = defaultdict(list)
        for org_id, org in organizations.items():
            for juan in org.juans_appeared:
                juan_to_organizations[juan].append(org_id)

        unit_to_roles = dict(juan_to_roles)
        unit_to_polities = dict(juan_to_polities)
        unit_to_schools = dict(juan_to_schools)
        unit_to_organizations = dict(juan_to_organizations)
        unit_to_events = dict(juan_to_events)
        
        # Update related entities based on relations
        for rel in relations.values():
            from_id = name_to_role_id.get(rel.from_entity)
            to_id = name_to_role_id.get(rel.to_entity)
            if from_id and from_id in roles:
                roles[from_id].related_entities.add(rel.to_entity)
            if to_id and to_id in roles:
                roles[to_id].related_entities.add(rel.from_entity)
        
        # Collect all processed juans
        all_juans: Set[int] = set()
        for role in roles.values():
            all_juans.update(role.juans_appeared)
        
        return UnifiedKnowledgeBase(
            book_id=self.book_metadata["book_id"],
            unit_label=self.book_metadata["unit_label"],
            progress_label=self.book_metadata["progress_label"],
            roles=roles,
            polities=polities,
            schools=schools,
            organizations=organizations,
            locations=locations,
            events=events,
            relations=relations,
            name_to_role_id=dict(name_to_role_id),
            name_to_polity_id=dict(name_to_polity_id),
            name_to_school_id=dict(name_to_school_id),
            name_to_organization_id=dict(name_to_organization_id),
            name_to_location_id=dict(name_to_location_id),
            power_to_roles=dict(power_to_roles),
            juan_to_roles=dict(juan_to_roles),
            juan_to_polities=dict(juan_to_polities),
            juan_to_schools=dict(juan_to_schools),
            juan_to_organizations=dict(juan_to_organizations),
            juan_to_events=dict(juan_to_events),
            unit_to_roles=unit_to_roles,
            unit_to_polities=unit_to_polities,
            unit_to_schools=unit_to_schools,
            unit_to_organizations=unit_to_organizations,
            unit_to_events=unit_to_events,
            total_roles=len(roles),
            total_polities=len(polities),
            total_schools=len(schools),
            total_organizations=len(organizations),
            total_locations=len(locations),
            total_events=len(events),
            total_relations=len(relations),
            juans_processed=sorted(all_juans)
        )


def _load_json_file(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _apply_role_overrides(entity: dict, overrides: dict) -> dict:
    if not entity.get("name"):
        return entity

    name = entity["name"]
    role_aliases = overrides.get("role_aliases", {})
    primary_powers = overrides.get("role_primary_powers", {})
    type_overrides = overrides.get("entity_type_overrides", {})
    description_overrides = overrides.get("role_descriptions", {})

    if isinstance(role_aliases, dict) and name in role_aliases:
        existing = list(entity.get("alias", []))
        additions = [alias for alias in role_aliases[name] if alias and alias not in existing]
        entity["alias"] = existing + additions

    if isinstance(primary_powers, dict) and name in primary_powers:
        entity["power"] = primary_powers[name]

    if isinstance(type_overrides, dict) and name in type_overrides:
        entity["entity_type"] = type_overrides[name]

    if isinstance(description_overrides, dict) and name in description_overrides:
        entity["description"] = description_overrides[name]

    return entity


def _apply_event_overrides(event: dict, overrides: dict) -> dict:
    if not event.get("name"):
        return event

    name = event["name"]
    event_names = overrides.get("event_names", {})
    if isinstance(event_names, dict) and name in event_names:
        event["name"] = event_names[name]
    return event


def load_and_resolve(
    store_dir: str,
    segment_year_index_path: Optional[str] = None,
    unit_progress_index_path: Optional[str] = None,
    book_config_path: Optional[str] = None,
    manual_overrides_path: Optional[str] = None,
) -> UnifiedKnowledgeBase:
    """
    Load all juan data files and resolve into unified knowledge base.
    
    Args:
        store_dir: Path to directory containing juan_*.json files
        
    Returns:
        UnifiedKnowledgeBase with all entities resolved
    """
    store_path = Path(store_dir)
    resolver = EntityResolver()

    if segment_year_index_path:
        payload = _load_json_file(segment_year_index_path)
        if payload:
            seg_map: Dict[str, int] = {}
            for key, seg in payload.get('segments', {}).items():
                year = seg.get('year')
                if year is not None:
                    seg_map[key] = int(year)
            resolver.set_segment_year_index(seg_map)
            print(f"Loaded segment year index: {segment_year_index_path} (entries={len(seg_map)})")
        else:
            print(f"Segment year index not found: {segment_year_index_path} (skipping)")

    if unit_progress_index_path:
        payload = _load_json_file(unit_progress_index_path)
        if payload:
            progress_map: Dict[str, int] = {}
            label_map: Dict[str, str] = {}
            for key, seg in payload.get('segments', {}).items():
                progress = seg.get('progress_index')
                if progress is not None:
                    progress_map[key] = int(progress)
                label = seg.get('progress_label')
                if label:
                    label_map[key] = str(label)
            resolver.set_segment_progress_index(progress_map, label_map)
            resolver.set_book_metadata(
                book_id=str(payload.get('book_id', 'swordcoming')),
                unit_label=str(payload.get('unit_label', '章节')),
                progress_label=str(payload.get('progress_label', '叙事进度')),
            )
            print(f"Loaded unit progress index: {unit_progress_index_path} (entries={len(progress_map)})")
        else:
            print(f"Unit progress index not found: {unit_progress_index_path} (skipping)")

    if book_config_path:
        payload = _load_json_file(book_config_path)
        if payload:
            resolver.set_book_metadata(
                book_id=str(payload.get('book_id', resolver.book_metadata['book_id'])),
                unit_label=str(payload.get('unit_label', resolver.book_metadata['unit_label'])),
                progress_label=str(payload.get('progress_label', resolver.book_metadata['progress_label'])),
            )
            print(f"Loaded book config: {book_config_path}")

    manual_overrides = _load_json_file(manual_overrides_path) or {}
    if manual_overrides:
        resolver.set_manual_overrides(manual_overrides)
        print(f"Loaded manual overrides: {manual_overrides_path}")
    
    # Load all juan files
    for juan_file in sorted(store_path.glob("juan_*.json")):
        print(f"Processing {juan_file.name}...")
        
        with open(juan_file, 'r', encoding='utf-8') as f:
            juan_data = json.load(f)
        
        for chunk_key, extraction in juan_data.items():
            juan_idx = extraction.get('juan_index', 0)
            seg_idx = extraction.get('segment_index', 0)
            chunk_idx = extraction.get('chunk_start_index', 0)
            source_sentences = extraction.get('source_sentences', [])
            source_text = ' '.join(source_sentences)
            
            # Add roles
            for entity in extraction.get('entities', []):
                entity = _apply_role_overrides(dict(entity), manual_overrides)
                role = Role(**entity)
                resolver.add_role(role, juan_idx, seg_idx, chunk_idx, source_text)
            
            # Add locations
            for loc in extraction.get('locations', []):
                location = Location(**loc)
                resolver.add_location(location, juan_idx, seg_idx, chunk_idx)
            
            # Add events
            for evt in extraction.get('events', []):
                evt = _apply_event_overrides(dict(evt), manual_overrides)
                event = Event(**evt)
                resolver.add_event(event, juan_idx, seg_idx)
            
            # Add relations
            for rel in extraction.get('relations', []):
                action = Action(**rel)
                resolver.add_relation(action)
    
    return resolver.build_knowledge_base()


def save_unified_knowledge_base(kb: UnifiedKnowledgeBase, output_path: str) -> None:
    """Save unified knowledge base to JSON file."""
    
    def serialize(obj):
        """Custom serializer for sets and other non-JSON types."""
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, 'model_dump'):
            return obj.model_dump()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(kb.model_dump(), f, ensure_ascii=False, indent=2, default=serialize)
    
    print(f"Saved unified knowledge base to {output_path}")
    print(f"  - {kb.total_roles} unique roles (persons)")
    print(f"  - {kb.total_polities} unique polities (states/dynasties)")
    print(f"  - {kb.total_schools} unique schools (ideologies)")
    print(f"  - {kb.total_organizations} unique organizations")
    print(f"  - {kb.total_locations} unique locations")
    print(f"  - {kb.total_events} unique events")
    print(f"  - {kb.total_relations} unique relations")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Build unified knowledge base from extractions")
    parser.add_argument("--store-dir", default="data/store", help="Directory containing juan_*.json files")
    parser.add_argument("--output", default="data/unified_knowledge.json", help="Output file path")
    parser.add_argument(
        "--segment-year-index",
        default="data/segment_year_index.json",
        help="Optional segment-year index JSON for deriving numeric years",
    )
    parser.add_argument(
        "--unit-progress-index",
        default="data/unit_progress_index.json",
        help="Optional unit-progress index JSON for generic narrative progress",
    )
    parser.add_argument(
        "--book-config",
        default="data/book_config.json",
        help="Optional book config JSON for generic labels and metadata",
    )
    parser.add_argument(
        "--manual-overrides",
        default="data/swordcoming_manual_overrides.json",
        help="Optional manual overrides JSON for aliases, powers, and blocked aliases",
    )
    
    args = parser.parse_args()
    
    seg_path = args.segment_year_index if args.segment_year_index else None
    unit_progress_path = args.unit_progress_index if args.unit_progress_index else None
    book_config_path = args.book_config if args.book_config else None
    manual_overrides_path = args.manual_overrides if args.manual_overrides else None
    kb = load_and_resolve(
        args.store_dir,
        segment_year_index_path=seg_path,
        unit_progress_index_path=unit_progress_path,
        book_config_path=book_config_path,
        manual_overrides_path=manual_overrides_path,
    )
    save_unified_knowledge_base(kb, args.output)
