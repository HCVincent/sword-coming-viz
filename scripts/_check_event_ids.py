"""Check if foreshadowing event IDs exist in unified_knowledge."""
import json

wi = json.load(open('visualization/public/data/writer_insights.json', 'r', encoding='utf-8'))
uk = json.load(open('data/unified_knowledge.json', 'r', encoding='utf-8'))

events = uk.get('events', {})
print(f"Total events in kb: {len(events)}")

missing = []
found = []
for thread in wi['foreshadowing_threads']:
    for evt in thread['clue_events'] + thread['payoff_events']:
        eid = evt['event_id']
        if eid in events:
            found.append(eid)
        else:
            missing.append((thread['label'], eid))

print(f"Found: {len(found)}, Missing: {len(missing)}")
if missing:
    print("\nMISSING event IDs:")
    for label, eid in missing[:20]:
        print(f"  [{label}] {eid}")
