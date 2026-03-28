#!/usr/bin/env python3
"""Generate season_overview_audit.json — a machine-readable audit artifact.

For every season overview this script emits:
  - which priority_roles are evidence-backed (appear in that season's chapters)
  - which season_focus names were dropped (zero appearances)
  - whether each story beat event actually falls within the season unit range
  - whether each anchor event falls within the season unit range
  - a per-event "evidence_chain" with source_unit_titles

Run:
    python scripts/build_season_overview_audit.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DATA = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _in_range(unit_index: int | None, unit_range: list[int]) -> bool:
    if unit_index is None:
        return False
    return unit_range[0] <= unit_index <= unit_range[1]


def _audit_event_refs(
    event_refs: list[dict],
    unit_range: list[int],
    label: str,
) -> list[dict]:
    """Audit a list of event refs for range compliance and evidence."""
    results: list[dict] = []
    for ev in event_refs:
        uid = ev.get("unit_index")
        in_range = _in_range(uid, unit_range)
        results.append({
            "event_id": ev.get("event_id"),
            "name": ev.get("name"),
            "unit_index": uid,
            "season_name": ev.get("season_name"),
            "in_season_range": in_range,
            "source_unit_titles": ev.get("source_unit_titles", []),
            "has_description": bool(ev.get("description")),
            "has_significance": bool(ev.get("significance")),
            "context": label,
        })
    return results


def build_audit(wi: dict, upi: dict) -> dict:
    """Build the audit payload from writer_insights and unit_progress_index."""
    # Build a lookup: role_name -> set of season_names where they have units
    role_season_units: Dict[str, Dict[str, int]] = {}
    for uid, meta in upi.get("units", {}).items():
        sn = meta.get("season_name")
        if not sn:
            continue
        # We'll populate this per-season from the overview's top_roles later

    season_audits: List[dict] = []
    for overview in wi.get("season_overviews", []):
        sn = overview["season_name"]
        ur = overview["unit_range"]

        # --- Priority roles audit ---
        # top_roles in the output is truncated ([:8]), but the full list
        # was used for evidence gating.  The real evidence check is whether
        # the role has unit_appearance_count > 0 (= appeared in chapter data).
        top_role_names = {r["role_name"] for r in overview.get("top_roles", [])}
        all_priority_names = {r["role_name"] for r in overview.get("priority_roles", [])}
        priority_roles_audit: List[dict] = []
        for role in overview.get("priority_roles", []):
            rn = role["role_name"]
            uac = role.get("unit_appearance_count", 0)
            priority_roles_audit.append({
                "role_name": rn,
                "in_season_top_roles": rn in top_role_names,
                "unit_appearance_count": uac,
                "event_count": role.get("event_count", 0),
                "evidence_status": "chapter_backed" if uac > 0 else "no_chapter_evidence",
            })

        # --- Priority relationships audit ---
        # Use the full priority_roles set (not just top 8) to check
        # whether both participants are season-backed.
        priority_rels_audit: List[dict] = []
        for rel in overview.get("priority_relationships", []):
            src = rel.get("source_role_name", "")
            tgt = rel.get("target_role_name", "")
            src_in_season = src in all_priority_names or src in top_role_names
            tgt_in_season = tgt in all_priority_names or tgt in top_role_names
            priority_rels_audit.append({
                "title": rel.get("title"),
                "source_role_name": src,
                "target_role_name": tgt,
                "source_in_season": src_in_season,
                "target_in_season": tgt_in_season,
                "both_in_season": src_in_season and tgt_in_season,
            })

        # --- Story beats audit ---
        beat_audits = []
        beat_names_used: list[str] = []
        for beat in overview.get("story_beats", []):
            ev = beat.get("event")
            if ev:
                uid = ev.get("unit_index")
                in_range = _in_range(uid, ur)
                name = ev.get("name", "")
                beat_audits.append({
                    "beat_type": beat.get("beat_type"),
                    "event_name": name,
                    "unit_index": uid,
                    "in_season_range": in_range,
                    "name_is_duplicate": name in beat_names_used,
                    "source_unit_titles": ev.get("source_unit_titles", []),
                })
                beat_names_used.append(name)
            else:
                beat_audits.append({
                    "beat_type": beat.get("beat_type"),
                    "event_name": None,
                    "in_season_range": False,
                    "name_is_duplicate": False,
                })

        # --- Anchor events audit ---
        anchor_audits = _audit_event_refs(
            overview.get("anchor_events", []), ur, "anchor_event"
        )

        # --- Must-keep scenes audit ---
        scene_audits = []
        for sc in overview.get("must_keep_scenes", []):
            ev = sc.get("event")
            if ev:
                uid = ev.get("unit_index")
                scene_audits.append({
                    "label": sc.get("label"),
                    "event_name": ev.get("name"),
                    "unit_index": uid,
                    "in_season_range": _in_range(uid, ur),
                })

        # --- Template parameter audit ---
        # Check that the role names injected into summary/spotlight/hooks
        # templates are all found in the season's evidence-backed role pool.
        # The pool = top_roles (density-ranked, chapter-backed) ∪ priority_roles
        # (season_focus, evidence-gated).
        all_evidence_backed_names = top_role_names | all_priority_names
        template_role_names: list[str] = []
        for pr in overview.get("priority_roles", []):
            template_role_names.append(pr["role_name"])
        # adaptation_hooks reference priority_relationship titles/names,
        # but never inject raw character names that bypass priority_roles.
        # We only need to verify the top-3 names that appear in summary.
        summary_injected_names = template_role_names[:3]
        unbacked_summary_names = [
            name for name in summary_injected_names
            if name not in all_evidence_backed_names
        ]

        # spotlight_summary counterparts come from priority_relationship_items
        # + season_curated + season_conflicts.  We check whether the spotlight
        # and its counterparts are all in the evidence pool.
        spotlight_names: list[str] = []
        prov_data = overview.get("data_provenance", {})
        ss = overview.get("spotlight_summary") or ""
        # Extract names that precede "形成主线互动" — they are the counterparts
        # generated by the template.  Rather than NER, we just verify the
        # spotlight role itself and all priority_relationship participants.
        for rel in overview.get("priority_relationships", []):
            spotlight_names.append(rel.get("source_role_name", ""))
            spotlight_names.append(rel.get("target_role_name", ""))
        spotlight_names = list(dict.fromkeys(n for n in spotlight_names if n))
        unbacked_spotlight_names = [
            name for name in spotlight_names
            if name not in all_evidence_backed_names
        ]

        template_params_audit = {
            "summary_injected_names": summary_injected_names,
            "unbacked_summary_names": unbacked_summary_names,
            "spotlight_relationship_names": spotlight_names,
            "unbacked_spotlight_names": unbacked_spotlight_names,
            "all_template_names_backed": (
                len(unbacked_summary_names) == 0
                and len(unbacked_spotlight_names) == 0
            ),
        }

        # --- Provenance passthrough ---
        provenance = overview.get("data_provenance", {})

        season_audits.append({
            "season_name": sn,
            "unit_range": ur,
            "priority_roles_audit": priority_roles_audit,
            "priority_roles_all_evidence_backed": all(
                r["evidence_status"] == "chapter_backed" for r in priority_roles_audit
            ),
            "priority_roles_dropped": provenance.get("priority_roles_dropped", []),
            "priority_relationships_audit": priority_rels_audit,
            "priority_relationships_both_in_season": all(
                r["both_in_season"] for r in priority_rels_audit
            ),
            "story_beats_audit": beat_audits,
            "story_beats_all_in_range": all(b["in_season_range"] for b in beat_audits if b.get("event_name")),
            "story_beats_all_unique_names": not any(b.get("name_is_duplicate") for b in beat_audits),
            "anchor_events_audit": anchor_audits,
            "anchor_events_all_in_range": all(a["in_season_range"] for a in anchor_audits),
            "must_keep_scenes_audit": scene_audits,
            "template_params_audit": template_params_audit,
            "data_provenance": provenance,
        })

    return {
        "version": "season-overview-audit-v1",
        "generated_at": datetime.now().isoformat(),
        "total_seasons": len(season_audits),
        "all_seasons_roles_evidence_backed": all(
            s["priority_roles_all_evidence_backed"] for s in season_audits
        ),
        "all_seasons_beats_in_range": all(
            s["story_beats_all_in_range"] for s in season_audits
        ),
        "all_seasons_beats_unique_names": all(
            s["story_beats_all_unique_names"] for s in season_audits
        ),
        "all_seasons_template_names_backed": all(
            s.get("template_params_audit", {}).get("all_template_names_backed", False)
            for s in season_audits
        ),
        "season_audits": season_audits,
    }


def main() -> None:
    wi = load("writer_insights.json")
    upi = load("unit_progress_index.json")
    audit = build_audit(wi, upi)

    out = DATA / "season_overview_audit.json"
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    # Print summary
    print(f"Season overview audit → {out}")
    print(f"  All roles evidence-backed: {audit['all_seasons_roles_evidence_backed']}")
    print(f"  All beats in range:        {audit['all_seasons_beats_in_range']}")
    print(f"  All beats unique names:    {audit['all_seasons_beats_unique_names']}")
    print(f"  All template names backed: {audit['all_seasons_template_names_backed']}")
    for sa in audit["season_audits"]:
        dropped = sa.get("priority_roles_dropped", [])
        if dropped:
            print(f"  {sa['season_name']}: dropped focus names (no chapter evidence): {dropped}")
        bad_roles = [r["role_name"] for r in sa["priority_roles_audit"] if r["evidence_status"] != "chapter_backed"]
        if bad_roles:
            print(f"  {sa['season_name']}: roles without chapter evidence: {bad_roles}")
        bad_beats = [b for b in sa["story_beats_audit"] if b.get("event_name") and not b["in_season_range"]]
        if bad_beats:
            print(f"  {sa['season_name']}: beats out of range: {[(b['event_name'], b['unit_index']) for b in bad_beats]}")


if __name__ == "__main__":
    main()
