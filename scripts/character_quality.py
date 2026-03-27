#!/usr/bin/env python3

from __future__ import annotations

from typing import Collection, List

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

SUSPICIOUS_ROLE_PREFIXES = (
    "尽管",
    "然后",
    "最后",
    "只是",
    "于是",
    "这个",
    "那个",
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


def build_blocked_role_name_set(extra_blocked: Collection[str] | None = None) -> set[str]:
    blocked = set(DEFAULT_BLOCKED_TITLED_ROLES)
    if extra_blocked:
        blocked.update(str(item).strip() for item in extra_blocked if str(item).strip())
    return blocked


def audit_role_name(name: str, blocked_names: Collection[str] | None = None) -> List[str]:
    candidate = str(name).strip()
    if not candidate:
        return []

    reasons: List[str] = []
    blocked = build_blocked_role_name_set(blocked_names)

    if candidate in blocked:
        reasons.append("命中阻断名单")
    if candidate in DEFAULT_BLOCKED_TITLED_ROLES:
        reasons.append("称谓型角色")
    if candidate in SUSPICIOUS_ROLE_EXACT_NAMES:
        reasons.append("明显伪角色")

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


def is_pseudo_role_name(name: str, blocked_names: Collection[str] | None = None) -> bool:
    return bool(audit_role_name(name, blocked_names=blocked_names))
