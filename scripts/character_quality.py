#!/usr/bin/env python3
"""Character name quality auditing for the SwordComing extraction pipeline.

Provides pattern-based detection of pseudo-role names (generic designators,
voice descriptors, action-suffix concatenation, descriptive phrases) and a
unified ``classify_role_name()`` function that enforces the precedence:

    **allow > merge > block**

Used by both Stage B (post-LLM extraction filter) and Stage C (entity
resolution) to apply a single, consistent set of rules.
"""

from __future__ import annotations

import re
from typing import Any, Collection, Dict, List, Literal, Optional, TypedDict

DEFAULT_BLOCKED_TITLED_ROLES = {
    "白衣少年",
    "中年儒士",
    "老道人",
    "老秀才",
    "老剑仙",
    "老僧",
    "老妪",
    "宫装妇人",
    "小道童",
    "阴神",
}

SUSPICIOUS_ROLE_EXACT_NAMES = {
    "管狮子",
    "后笑眯眯",
}

# Voice / sound / manner descriptors that are never character names.
# These arise from speech-tag extraction: "嗓音沙哑" → spurious entity "沙哑".
VOICE_DESCRIPTOR_NAMES: set[str] = {
    "沙哑", "嗓音", "低沉", "清脆", "尖锐", "浑厚", "嘶哑",
    "沉闷", "洪亮", "颤抖", "嘹亮", "凄厉", "凄凉",
}

# Single-char action / adjective suffixes that may be concatenated onto a real
# character name during extraction. E.g. "俞真意" + "冷" → "俞真意冷".
# Detection: if candidate[-1] is in this set **and** candidate[:-1] is a known
# canonical role name, the candidate is a concatenation artefact.
CONCAT_ACTION_SUFFIXES: set[str] = {
    "冷", "道", "笑", "怒", "叹", "惊", "急", "悲", "喜",
    "恨", "嗔", "疑", "哭", "骂", "忧", "愁", "慌", "愣",
}

SUSPICIOUS_ROLE_PREFIXES = (
    "尽管",
    "然后",
    "最后",
    "只是",
    "于是",
    "这个",
    "那个",
    "一个",
    "一位",
    "一名",
    "后",
    "前",
)

SUSPICIOUS_ROLE_SUBSTRINGS = (
    "笑眯眯",
    "笑呵呵",
    "笑吟吟",
    "大开口",
    "小心翼翼",
    "毕恭毕敬",
    "试探性",
    "转头",
    "抬头",
    "低头",
    "点头",
    "摇头",
    "看向",
    "看着",
    "望向",
    "望着",
    "同行",
    "并肩",
    "对视",
    "相视",
    "出声",
)

SUSPICIOUS_ROLE_SUFFIXES = (
    "说道",
    "问道",
    "笑道",
    "答道",
    "怒道",
    "喝道",
    "骂道",
    "轻声",
    "沉声",
    "开口",
)

# ---------------------------------------------------------------------------
# Generic designator variant detection
# ---------------------------------------------------------------------------
# These are *structural patterns* that catch descriptive designators missed by
# the exact blocklists.  Each returns a reason string or ``None``.

# Core generic role words used as building blocks for pattern matching.
_GENERIC_ROLE_WORDS: tuple[str, ...] = (
    "少年", "少女", "道人", "老人", "老头", "老者",
    "女子", "男子", "儒士", "书生", "和尚", "僧人",
    "剑客", "剑修", "武夫", "妇人", "汉子", "姑娘",
    "小姑娘", "丫头", "孩子", "婆婆", "老妇",
    "公子", "夫人",
)

# Pre-compiled patterns (built once at module load).
#   穿X的少年 / 穿X的道人  — clothing-based descriptors
_CLOTHING_DESCRIPTOR_RE = re.compile(
    r"^穿.{1,6}的(" + "|".join(re.escape(w) for w in _GENERIC_ROLE_WORDS) + r")$"
)
#   X的道人 / X的老人  — generic "modifier + 的 + role word"
_MODIFIER_DE_ROLE_RE = re.compile(
    r"^.{1,6}的(" + "|".join(re.escape(w) for w in _GENERIC_ROLE_WORDS) + r")$"
)
#   Appearance-based: 白衣/青衫/黑袍/灰衣… + role word (no 的)
_APPEARANCE_ROLE_RE = re.compile(
    r"^[白青黑灰红蓝绿紫金银褐][衣袍衫裙裳袖帽冠]("
    + "|".join(re.escape(w) for w in _GENERIC_ROLE_WORDS)
    + r")$"
)
#   Demonstrative/quantifier + generic: 那个老头 / 这个少年 / 一位道人
_DEMONSTRATIVE_GENERIC_RE = re.compile(
    r"^(那个|这个|那位|这位|一个|一位|一名|某个|某位)("
    + "|".join(re.escape(w) for w in _GENERIC_ROLE_WORDS)
    + r")$"
)
#   Positional: 身旁的/旁边的/对面的 + role word
_POSITIONAL_ROLE_RE = re.compile(
    r"^(身旁|身边|旁边|对面|面前|身后|左边|右边|左侧|右侧|一旁).{0,2}("
    + "|".join(re.escape(w) for w in _GENERIC_ROLE_WORDS)
    + r")$"
)
#   Bare generic role word used as a standalone name
_BARE_GENERIC_ROLE_SET: frozenset[str] = frozenset(_GENERIC_ROLE_WORDS)


def _detect_generic_designator_variant(candidate: str) -> Optional[str]:
    """Return a reason string if *candidate* is a generic designator variant.

    Returns ``None`` when the candidate does not match any known generic
    designator pattern.
    """
    if not candidate:
        return None

    # Bare generic role word: 少年, 道人, 老人 …
    if candidate in _BARE_GENERIC_ROLE_SET:
        return f"泛称裸词:{candidate}"

    if _CLOTHING_DESCRIPTOR_RE.match(candidate):
        return f"穿着描述泛称:{candidate}"

    if _APPEARANCE_ROLE_RE.match(candidate):
        return f"外貌泛称:{candidate}"

    if _DEMONSTRATIVE_GENERIC_RE.match(candidate):
        return f"指示代词+泛称:{candidate}"

    if _POSITIONAL_ROLE_RE.match(candidate):
        return f"方位泛称:{candidate}"

    # "X的道人" — must come after the more specific patterns above
    if _MODIFIER_DE_ROLE_RE.match(candidate):
        return f"修饰语泛称:{candidate}"

    return None

ALLOWED_SPECIAL_RESOLUTIONS = {"keep_as_canonical", "merge_to_canonical"}


class NameClassification(TypedDict):
    """Structured result from :func:`classify_role_name_detailed`.

    ``decision``
        ``"keep"`` – use the name as-is as a canonical name.
        ``"merge"`` – merge into the entity identified by *canonical_target*.
        ``"block"`` – pseudo-role / noise; exclude from the person graph.

    ``canonical_target``
        The canonical name to merge into when ``decision == "merge"``.
        ``None`` for ``keep`` and ``block``.
    """
    decision: Literal["keep", "merge", "block"]
    canonical_target: Optional[str]


def build_allowed_special_designator_map(
    entries: Collection[Any] | None = None,
) -> Dict[str, Dict[str, str]]:
    """Normalize special stable-designator allowlist entries.

    The allowlist exists to preserve *stable, unambiguous role designators*
    such as 杨老头 / 火龙真人 that should survive noise filtering even though
    they are not always身份证式本名.
    """
    allowed: Dict[str, Dict[str, str]] = {}
    if not entries:
        return allowed

    for raw in entries:
        if isinstance(raw, str):
            name = raw.strip()
            if not name:
                continue
            allowed[name] = {
                "name": name,
                "resolution": "keep_as_canonical",
                "canonical_target": name,
                "kind": "honorific",
            }
            continue

        if not isinstance(raw, dict):
            continue

        name = str(raw.get("name", "")).strip()
        if not name:
            continue

        resolution = str(raw.get("resolution", "keep_as_canonical")).strip() or "keep_as_canonical"
        if resolution not in ALLOWED_SPECIAL_RESOLUTIONS:
            resolution = "keep_as_canonical"

        canonical_target = str(raw.get("canonical_target", "")).strip() or name
        kind = str(raw.get("kind", "honorific")).strip() or "honorific"

        allowed[name] = {
            "name": name,
            "resolution": resolution,
            "canonical_target": canonical_target,
            "kind": kind,
        }

    return allowed


def build_allowed_special_designator_names(
    entries: Collection[Any] | None = None,
) -> set[str]:
    return set(build_allowed_special_designator_map(entries).keys())


def build_blocked_role_name_set(extra_blocked: Collection[str] | None = None) -> set[str]:
    blocked = set(DEFAULT_BLOCKED_TITLED_ROLES)
    if extra_blocked:
        blocked.update(str(item).strip() for item in extra_blocked if str(item).strip())
    return blocked


def audit_role_name(
    name: str,
    blocked_names: Collection[str] | None = None,
    *,
    canonical_roles: Collection[str] | None = None,
    allowed_names: Collection[str] | None = None,
) -> List[str]:
    """Return a list of reasons why *name* looks like a pseudo-role.

    Parameters
    ----------
    canonical_roles:
        Known-good canonical role names.  When supplied, enables
        *name+action-suffix concatenation* detection (e.g. 俞真意冷 =
        俞真意 + 冷).
    """
    candidate = str(name).strip()
    if not candidate:
        return []

    allowed = {str(item).strip() for item in (allowed_names or []) if str(item).strip()}
    if candidate in allowed:
        return []

    reasons: List[str] = []
    blocked = build_blocked_role_name_set(blocked_names)

    if candidate in blocked:
        reasons.append("命中阻断名单")
    if candidate in DEFAULT_BLOCKED_TITLED_ROLES:
        reasons.append("称谓型角色")
    if candidate in SUSPICIOUS_ROLE_EXACT_NAMES:
        reasons.append("明显伪角色")

    # Voice / sound descriptor check
    if candidate in VOICE_DESCRIPTOR_NAMES:
        reasons.append(f"语音描写词:{candidate}")

    # Name + single-char action/adjective concatenation check
    if (
        canonical_roles
        and len(candidate) >= 3
        and candidate[-1] in CONCAT_ACTION_SUFFIXES
        and candidate[:-1] in canonical_roles
    ):
        reasons.append(f"人名粘连:{candidate[:-1]}+{candidate[-1]}")

    # --- Generic designator variant detection ---
    generic_reason = _detect_generic_designator_variant(candidate)
    if generic_reason:
        reasons.append(generic_reason)

    prefix_hit = next(
        (prefix for prefix in SUSPICIOUS_ROLE_PREFIXES if candidate.startswith(prefix) and len(candidate) > len(prefix)),
        None,
    )
    if prefix_hit:
        reasons.append(f"前缀短语残片:{prefix_hit}")

    substring_hit = next((token for token in SUSPICIOUS_ROLE_SUBSTRINGS if token in candidate), None)
    if substring_hit:
        reasons.append(f"包含动作或状态词:{substring_hit}")

    suffix_hit = next((token for token in SUSPICIOUS_ROLE_SUFFIXES if candidate.endswith(token)), None)
    if suffix_hit:
        reasons.append(f"尾部动作短语:{suffix_hit}")

    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def is_pseudo_role_name(
    name: str,
    blocked_names: Collection[str] | None = None,
    *,
    canonical_roles: Collection[str] | None = None,
    allowed_names: Collection[str] | None = None,
) -> bool:
    return bool(
        audit_role_name(
            name,
            blocked_names=blocked_names,
            canonical_roles=canonical_roles,
            allowed_names=allowed_names,
        )
    )


# ---------------------------------------------------------------------------
# Unified classify_role_name — single entry-point for allow > merge > block
# ---------------------------------------------------------------------------

def classify_role_name_detailed(
    name: str,
    *,
    allowed_special_designators: Dict[str, Dict[str, str]] | None = None,
    canonical_role_names: Dict[str, str] | None = None,
    role_aliases: Dict[str, list[str]] | None = None,
    blocked_names: Collection[str] | None = None,
    canonical_roles: Collection[str] | None = None,
    allowed_names: Collection[str] | None = None,
) -> NameClassification:
    """Classify a role name and return a structured :class:`NameClassification`.

    Precedence: **allowed_special_designators > canonical/aliases > noise > unknown**.

    ``decision`` values:
    - ``"keep"``  – use the name as-is as a canonical identity.
    - ``"merge"`` – merge this name into *canonical_target*.
    - ``"block"`` – pseudo-role / noise; exclude from the person graph.

    ``canonical_target``:
    - Set for ``merge`` decisions (the target canonical name).
    - ``None`` for ``keep`` and ``block``.
    """
    candidate = str(name).strip()
    if not candidate:
        return NameClassification(decision="block", canonical_target=None)

    # --- 1. Allowed special designators (highest priority) ---
    asd = allowed_special_designators or {}
    if candidate in asd:
        entry = asd[candidate]
        resolution = entry.get("resolution", "keep_as_canonical")
        target = entry.get("canonical_target", candidate)
        if resolution == "merge_to_canonical" and target != candidate:
            return NameClassification(decision="merge", canonical_target=target)
        return NameClassification(decision="keep", canonical_target=None)

    # Build a merged allowed_names set from the explicit param + ASD keys
    merged_allowed = set(asd.keys())
    if allowed_names:
        merged_allowed.update(str(n).strip() for n in allowed_names if str(n).strip())

    # --- 2. Known canonical or alias → merge / keep ---
    _canonical = canonical_role_names or {}
    _aliases = role_aliases or {}

    # name is a known alias that maps to a canonical name
    if candidate in _canonical:
        return NameClassification(decision="merge", canonical_target=_canonical[candidate])

    # name is the canonical target of some alias mapping → keep
    canonical_targets = set(_canonical.values())
    if candidate in canonical_targets:
        return NameClassification(decision="keep", canonical_target=None)

    # name is the main name in role_aliases dict (i.e. canonical) → keep
    if candidate in _aliases:
        return NameClassification(decision="keep", canonical_target=None)

    # name appears as an alias value → merge to the canonical key
    for _canon, _alias_list in _aliases.items():
        if candidate in _alias_list:
            return NameClassification(decision="merge", canonical_target=_canon)

    # --- 3. Pseudo-role / noise detection → block ---
    reasons = audit_role_name(
        candidate,
        blocked_names=blocked_names,
        canonical_roles=canonical_roles,
        allowed_names=merged_allowed,
    )
    if reasons:
        return NameClassification(decision="block", canonical_target=None)

    # --- 4. Unknown name: benefit of the doubt → keep ---
    return NameClassification(decision="keep", canonical_target=None)


def classify_role_name(
    name: str,
    *,
    allowed_special_designators: Dict[str, Dict[str, str]] | None = None,
    canonical_role_names: Dict[str, str] | None = None,
    role_aliases: Dict[str, list[str]] | None = None,
    blocked_names: Collection[str] | None = None,
    canonical_roles: Collection[str] | None = None,
    allowed_names: Collection[str] | None = None,
) -> Literal["allow", "merge", "block"]:
    """Legacy compatibility wrapper around :func:`classify_role_name_detailed`.

    Maps the new three-valued *decision* to the old three-valued return:
    - ``keep`` → ``"allow"``
    - ``merge`` → ``"merge"``
    - ``block`` → ``"block"``
    """
    result = classify_role_name_detailed(
        name,
        allowed_special_designators=allowed_special_designators,
        canonical_role_names=canonical_role_names,
        role_aliases=role_aliases,
        blocked_names=blocked_names,
        canonical_roles=canonical_roles,
        allowed_names=allowed_names,
    )
    if result["decision"] == "keep":
        return "allow"
    return result["decision"]  # "merge" or "block"
