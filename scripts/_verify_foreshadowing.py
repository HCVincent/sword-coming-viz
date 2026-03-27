"""Verify foreshadowing thread quality."""
import json

data = json.loads(open(r"d:\code\NovelVisualization\SwordComing\data\writer_insights.json", encoding="utf-8").read())
threads = data["foreshadowing_threads"]
print(f"Total threads: {len(threads)}\n")

for t in threads:
    label = t["label"]
    print(f"=== {label} ===")
    print(f"  Seasons: {t['season_names']}")
    print(f"  Unit span: {t['unit_span']}")
    print(f"  Focus roles: {t['focus_roles']}")
    
    clue_seasons = set()
    for ev in t.get("clue_events", []):
        clue_seasons.add(ev.get("season_name", "?"))
    payoff_seasons = set()
    for ev in t.get("payoff_events", []):
        payoff_seasons.add(ev.get("season_name", "?"))
    print(f"  Clue event seasons: {clue_seasons}")
    print(f"  Payoff event seasons: {payoff_seasons}")
    
    clue_units = [ev.get("unit_index") for ev in t.get("clue_events", []) if ev.get("unit_index")]
    payoff_units = [ev.get("unit_index") for ev in t.get("payoff_events", []) if ev.get("unit_index")]
    print(f"  Clue units: {clue_units}")
    print(f"  Payoff units: {payoff_units}")
    print()
