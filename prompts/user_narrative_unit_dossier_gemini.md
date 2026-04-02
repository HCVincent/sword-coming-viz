# Narrative Unit Dossier Rewrite Pass

You already wrote a first draft dossier for one narrative unit in "Sword Coming".
Now rewrite it so it reads like a precise story-doctor note for adaptation work.

Write all output prose in Simplified Chinese.

## Rewrite Rules

Check and fix every issue below:

1. The title must not reuse a chapter title.
2. `display_summary` must give a fast structural read, not an event list.
3. `long_summary` must feel like a judgment about the unit's dramatic work, not
   a chapter recap.
4. `dramatic_function` must clearly state what this unit does in the overall
   structure. Do not use vague phrases like "推动剧情发展" or "承上启下".
5. `what_changes` must state what materially shifts for character, relationship,
   pressure, or story direction.
6. `stakes` must state what would be at risk or what the story would lose if
   this unit unfolded differently.
7. Avoid stock openings such as "这一剧情单元讲述了", "在这几章中", or "从叙事角度看".
8. Do not invent facts beyond the packet.
9. Do not let `display_summary` and `long_summary` become near-duplicates.

## Output Requirement

Return the corrected final JSON only. No markdown fence. No explanation.

## Draft

{draft_json}

## Source Packet

{packet_json}
