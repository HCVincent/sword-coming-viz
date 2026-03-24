Process Chinese fantasy novel chapters and extract structured entity-relation data for downstream visualization. Maintain strict JSON output.

# Focus
- Prioritize named characters, factions/sects/courts, organizations, locations, events, and directed relationships.
- The text is a novel, not a chronicle. Use chapter order as the main narrative timeline when exact dates are absent.
- Preserve story context, conflict, turning points, allegiance changes, and location shifts.

# Steps
1. **Entity Identification**
- Extract named people first.
- Use `entity_type`:
  - `person`: named characters
  - `polity`: kingdoms, dynasties, courts, sect-like camps treated as macro factions
  - `organization`: sects, schools, guilds, armies, offices, clans, courts, lineages
  - `school`: philosophical schools only when clearly ideological
- Record aliases only when they uniquely identify the same entity.
- Do not use generic titles as aliases: `先生`, `掌教`, `皇帝`, `道人`, `少年`, `少女`, `公子`, `老前辈`.
- Preserve original descriptive wording when available.
- `power` should capture the most relevant camp, sect, dynasty, lineage, or faction.
- Record `sentence_indexes_in_segment`.

2. **Location Identification**
- Extract settlements, mountains, rivers, caves,洞天福地, kingdoms, and other place names.
- `modern_name` can be empty for fictional locations.
- `coordinates` should stay `null` unless authoritative coordinates exist.
- `related_entities` must reference names present in `entities`.

3. **Event Identification**
- Extract concrete plot events, confrontations, meetings, revelations, travel milestones, and turning points.
- `time` is optional and should preserve raw textual wording when present.
- `location` must reference a location in the `locations` list if known.
- `participants` must reference names present in `entities`.
- Prefer concise but specific event names.

4. **Relation Mapping**
- Extract directed interactions between entities: meeting, warning, mocking, rescuing, attacking, bargaining, teaching, threatening, ordering, protecting, betraying.
- Use `is_commentary=true` only for commentary or meta-evaluation rather than story action.
- `context` should explain the interaction in story terms.
- `event_name` should reference a named event when possible.

# Output
Return strict JSON only.
```json
{
  "entities": [
    {
      "entity_type": "person|polity|school|organization",
      "name": "名称",
      "alias": ["别名"],
      "original_description_in_book": "原文中的描述",
      "description": "简要说明",
      "power": "阵营或组织",
      "sentence_indexes_in_segment": [0]
    }
  ],
  "locations": [
    {
      "name": "地点",
      "alias": ["别名"],
      "type": "地点类型",
      "description": "地点描述",
      "modern_name": "",
      "related_entities": ["相关实体"],
      "sentence_indexes_in_segment": [0]
    }
  ],
  "events": [
    {
      "name": "事件名",
      "time": "原文时间或None",
      "location": "地点名或None",
      "participants": ["参与者"],
      "description": "事件描述",
      "background": "背景补充",
      "significance": "剧情意义",
      "sentence_indexes_in_segment": [0, 1]
    }
  ],
  "relations": [
    {
      "time": "原文时间或None",
      "from_roles": ["主动方"],
      "to_roles": ["被动方"],
      "action": "动作",
      "context": "上下文",
      "result": "结果或None",
      "event_name": "事件名或None",
      "location": "地点或None",
      "is_commentary": false,
      "sentence_indexes_in_segment": [0]
    }
  ]
}
```

# Rules
- Only extract information supported by `target_sentences`; `context_sentences` are only for disambiguation.
- Every role in `relations[*].from_roles` and `relations[*].to_roles` must appear in `entities`.
- Every participant in `events[*].participants` must appear in `entities`.
- Every referenced location must appear in `locations`.
- Keep JSON valid.
