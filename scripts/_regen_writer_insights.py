"""Standalone script to regenerate writer_insights.json only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model.unified import UnifiedKnowledgeBase
from scripts.build_swordcoming_writer_insights import build_writer_insights_file

DATA = ROOT / "data"

print("Loading unified_knowledge.json ...")
raw = json.loads((DATA / "unified_knowledge.json").read_text(encoding="utf-8"))
kb = UnifiedKnowledgeBase(**raw)
print(f"  Loaded {kb.total_roles} roles, {kb.total_events} events")

payload = build_writer_insights_file(
    kb=kb,
    unit_progress_index_path=DATA / "unit_progress_index.json",
    core_cast_path=DATA / "swordcoming_core_cast.json",
    output_path=DATA / "writer_insights.json",
)

threads = payload.get("foreshadowing_threads", [])
print(f"\nGenerated {len(threads)} foreshadowing threads:")
for t in threads:
    seasons = ", ".join(t.get("season_names", []))
    clue_count = len(t.get("clue_events", []))
    payoff_count = len(t.get("payoff_events", []))
    unit_span = t.get("unit_span", [None, None])
    print(f"  [{t['id']}] {t['label']}")
    print(f"    seasons: {seasons}")
    print(f"    unit_span: {unit_span}")
    print(f"    clue_events: {clue_count}, payoff_events: {payoff_count}")
