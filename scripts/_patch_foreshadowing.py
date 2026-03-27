"""Patch script: replace find_events_for_pattern + build_foreshadowing_threads."""
import pathlib, sys

SRC = pathlib.Path(r"d:\code\NovelVisualization\SwordComing\scripts\build_swordcoming_writer_insights.py")
data = SRC.read_text(encoding="utf-8")

marker_start = "return curated_relationships\n\n\ndef find_events_for_pattern"
marker_end = "\n\ndef focused_event_score"

i = data.index(marker_start)
j = data.index(marker_end)

NEW_BLOCK = r'''return curated_relationships


def find_events_for_pattern(
    *,
    event_refs: Sequence[dict],
    focus_roles: Sequence[str],
    keywords: Sequence[str],
    unit_range: Optional[List[int]] = None,
    event_names: Optional[List[str]] = None,
) -> List[dict]:
    """Find events matching a foreshadowing pattern.

    Supports two modes:
    1. keyword + role matching (original)
    2. explicit event_names / unit_range for precise targeting

    When *unit_range* is provided only events whose unit_index falls inside
    ``[min, max]`` are considered.  When *event_names* is given, events
    whose name contains any of those strings are automatically included.
    """
    normalized_keywords = [str(kw).strip() for kw in keywords if str(kw).strip()]
    normalized_roles = {str(n).strip() for n in focus_roles if str(n).strip()}
    normalized_event_names = [str(n).strip() for n in (event_names or []) if str(n).strip()]
    matches: List[dict] = []
    for event_ref in event_refs:
        uid = event_ref.get("unit_index")
        if unit_range and uid is not None:
            if uid < unit_range[0] or uid > unit_range[1]:
                continue
        haystack = " ".join(
            part
            for part in [
                event_ref.get("name") or "",
                event_ref.get("description") or "",
                event_ref.get("significance") or "",
                event_ref.get("location") or "",
            ]
            if part
        )
        name_hit = normalized_event_names and any(
            en in (event_ref.get("name") or "") for en in normalized_event_names
        )
        role_hit = not normalized_roles or any(
            role in event_ref.get("participants", []) for role in normalized_roles
        )
        keyword_hit = normalized_keywords and any(kw in haystack for kw in normalized_keywords)
        if name_hit or (role_hit and keyword_hit):
            matches.append(event_ref)
    return matches


def _score_foreshadow_event(
    event_ref: dict,
    *,
    keywords: Sequence[str],
    focus_roles: Sequence[str],
) -> int:
    """Score an event for relevance to a foreshadowing pattern (higher = better)."""
    score = 0
    name = event_ref.get("name") or ""
    sig = event_ref.get("significance") or ""
    desc = event_ref.get("description") or ""
    participants = event_ref.get("participants", [])
    for kw in keywords:
        if kw in name:
            score += 5
        if kw in sig:
            score += 3
        if kw in desc:
            score += 1
    for role in focus_roles:
        if role in participants:
            score += 3
    etype = event_ref.get("event_type") or ""
    for t in ("\u63ed\u793a", "\u7acb\u52bf", "\u8f6c\u6298", "\u51b2\u7a81", "\u4f1a\u89c1", "\u522b\u79bb"):
        if t in etype:
            score += 2
    n = len(participants)
    if 1 <= n <= 4:
        score += 2
    elif n > 10:
        score -= 3
    return score


def _dedup_events(events: List[dict], *, max_count: int) -> List[dict]:
    """Keep up to *max_count* unique events spread across different units."""
    seen: set = set()
    unique: List[dict] = []
    for ev in events:
        key = (ev.get("name"), ev.get("unit_index"))
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    if len(unique) <= max_count:
        return unique
    by_unit: Dict[int, List[dict]] = {}
    for ev in unique:
        by_unit.setdefault(ev.get("unit_index") or 0, []).append(ev)
    picked: List[dict] = [lst[0] for lst in sorted(by_unit.values(), key=lambda lst: lst[0].get("unit_index") or 0)]
    if len(picked) > max_count:
        step = max(1, len(picked) // max_count)
        picked = picked[::step][:max_count]
    return picked[:max_count]


def build_foreshadowing_threads(
    *,
    event_refs: Sequence[dict],
    patterns: Sequence[dict],
    spotlight_role: Optional[str],
) -> List[dict]:
    threads: List[dict] = []
    for pattern in patterns:
        label = str(pattern.get("label", "")).strip()
        if not label:
            continue
        focus_roles = [str(name).strip() for name in pattern.get("focus_roles", []) if str(name).strip()]

        clue_kw = pattern.get("clue_keywords", [])
        payoff_kw = pattern.get("payoff_keywords", [])

        clue_events = find_events_for_pattern(
            event_refs=event_refs,
            focus_roles=focus_roles,
            keywords=clue_kw,
            unit_range=pattern.get("clue_unit_range"),
            event_names=pattern.get("clue_event_names"),
        )
        payoff_events = find_events_for_pattern(
            event_refs=event_refs,
            focus_roles=focus_roles,
            keywords=payoff_kw,
            unit_range=pattern.get("payoff_unit_range"),
            event_names=pattern.get("payoff_event_names"),
        )

        # score and sort by relevance
        clue_events.sort(
            key=lambda r: (
                -_score_foreshadow_event(r, keywords=clue_kw, focus_roles=focus_roles),
                r.get("progress_start") or 10**12,
                r.get("unit_index") or 10**12,
            )
        )
        payoff_events.sort(
            key=lambda r: (
                -_score_foreshadow_event(r, keywords=payoff_kw, focus_roles=focus_roles),
                r.get("progress_start") or 10**12,
                r.get("unit_index") or 10**12,
            )
        )

        if not clue_events or not payoff_events:
            continue

        first_clue_unit = min(
            (r.get("unit_index") for r in clue_events if r.get("unit_index") is not None),
            default=None,
        )
        if first_clue_unit is not None:
            payoff_events = [
                r for r in payoff_events
                if r.get("unit_index") is None or r["unit_index"] >= first_clue_unit
            ]
        if not payoff_events:
            continue

        clue_events = _dedup_events(clue_events, max_count=5)
        payoff_events = _dedup_events(payoff_events, max_count=5)

        # chronological order for display
        for grp in (clue_events, payoff_events):
            grp.sort(key=lambda r: (r.get("progress_start") or 10**12, r.get("unit_index") or 10**12))

        seasons: List[str] = []
        for grp in (clue_events, payoff_events):
            for ev in grp:
                sn = ev.get("season_name")
                if sn and sn not in seasons:
                    seasons.append(sn)

        all_evts = clue_events + payoff_events
        prog = [r["progress_start"] for r in all_evts if r["progress_start"] is not None]
        progress_span = [min(prog), max(prog)] if prog else [None, None]
        units = [r["unit_index"] for r in all_evts if r["unit_index"] is not None]

        threads.append(
            {
                "id": str(pattern.get("id") or label),
                "label": label,
                "spotlight": bool(spotlight_role) and spotlight_role in focus_roles,
                "focus_roles": focus_roles,
                "motif_keywords": [str(k).strip() for k in pattern.get("motif_keywords", []) if str(k).strip()],
                "unit_span": [min(units), max(units)] if units else [None, None],
                "progress_span": progress_span,
                "season_names": seasons,
                "clue_events": clue_events,
                "payoff_events": payoff_events,
                "summary": (
                    f"{label}\u5728{('\u3001'.join(seasons) if seasons else '\u5f53\u524d\u8303\u56f4')}\u5f62\u6210\u201c\u524d\u6bb5\u57cb\u7ebf\uff0c\u540e\u6bb5\u5151\u73b0\u201d\u7684\u63a8\u8fdb\u7ed3\u6784\uff0c"
                    f"\u91cd\u70b9\u89d2\u8272\u5305\u62ec{('\u3001'.join(focus_roles) if focus_roles else '\u591a\u4f4d\u4eba\u7269')}\u3002"
                ),
            }
        )

    threads.sort(key=lambda item: (0 if item.get("spotlight") else 1, item["label"]))
    return threads'''

data = data[:i] + NEW_BLOCK + data[j:]
SRC.write_text(data, encoding="utf-8")
print("OK – patched build_swordcoming_writer_insights.py")
