import type {
  PowerDistributionUnified,
  RoleLinkUnified,
  RoleNodeUnified,
  TimelineEventUnified,
  UnifiedEvent,
  UnifiedKnowledgeBase,
  UnifiedLocation,
  UnifiedRelation,
  UnifiedRole,
} from '../types/unified';

const GENERIC_POWER_LABELS = new Set(['山上', '山下', '山水', '江湖', '道家', '武道', '未归类']);

function getRoleUnits(role: UnifiedRole): number[] {
  return role.units_appeared && role.units_appeared.length > 0 ? role.units_appeared : role.juans_appeared;
}

function getLocationUnits(location: UnifiedLocation): number[] {
  return location.units_appeared && location.units_appeared.length > 0
    ? location.units_appeared
    : location.juans_appeared;
}

function getEventUnits(event: UnifiedEvent): number[] {
  return event.source_units && event.source_units.length > 0 ? event.source_units : event.source_juans;
}

function getRelationUnits(relation: UnifiedRelation): number[] {
  return relation.source_units && relation.source_units.length > 0
    ? relation.source_units
    : relation.source_juans;
}

function inUnitRange(units: number[], unitRange?: [number, number]) {
  if (!unitRange) return true;
  const [start, end] = unitRange;
  return units.some((unit) => unit >= start && unit <= end);
}

function rangeOverlaps(
  range: [number | null | undefined, number | null | undefined],
  filterRange: [number | null, number | null]
) {
  const [start, end] = range;
  const [filterStart, filterEnd] = filterRange;
  if (filterStart === null && filterEnd === null) return true;
  if (start == null && end == null) return false;

  const effectiveStart = start ?? end ?? null;
  const effectiveEnd = end ?? start ?? null;
  if (effectiveStart == null || effectiveEnd == null) return false;

  const normalizedStart = Math.min(effectiveStart, effectiveEnd);
  const normalizedEnd = Math.max(effectiveStart, effectiveEnd);
  const targetStart = filterStart ?? -Infinity;
  const targetEnd = filterEnd ?? Infinity;
  return normalizedEnd >= targetStart && normalizedStart <= targetEnd;
}

function eventOverlapsProgressRange(
  event: UnifiedEvent,
  progressRange: [number | null, number | null]
) {
  return rangeOverlaps([event.progress_start, event.progress_end], progressRange);
}

function relationOverlapsProgressRange(
  relation: UnifiedRelation,
  progressRange: [number | null, number | null]
) {
  return rangeOverlaps([relation.progress_start, relation.progress_end], progressRange);
}

function countRoleMentionsInUnitRange(role: UnifiedRole, unitRange?: [number, number]) {
  if (!unitRange) return role.total_mentions;
  const [start, end] = unitRange;
  return role.occurrences.filter((occurrence) => occurrence.juan_index >= start && occurrence.juan_index <= end).length;
}

function roleMatchesProgressRange(
  kb: UnifiedKnowledgeBase,
  role: UnifiedRole,
  unitRange: [number, number] | undefined,
  progressRange: [number | null, number | null]
) {
  if (progressRange[0] === null && progressRange[1] === null) return true;

  const names = new Set([role.canonical_name, ...(role.all_names ?? [])]);
  const eventMatch = Object.values(kb.events).some(
    (event) =>
      inUnitRange(getEventUnits(event), unitRange) &&
      eventOverlapsProgressRange(event, progressRange) &&
      event.participants.some((participant) => names.has(participant))
  );
  if (eventMatch) return true;

  return Object.values(kb.relations).some(
    (relation) =>
      inUnitRange(getRelationUnits(relation), unitRange) &&
      relationOverlapsProgressRange(relation, progressRange) &&
      (names.has(relation.from_entity) || names.has(relation.to_entity))
  );
}

function toRoleNode(role: UnifiedRole, unitRange?: [number, number], isIsolated: boolean = false): RoleNodeUnified {
  return {
    id: role.id,
    name: role.canonical_name,
    power: resolveDisplayPower(role) ?? role.primary_power,
    description: role.description,
    appearances: countRoleMentionsInUnitRange(role, unitRange),
    units: getRoleUnits(role),
    aliases: Array.from(role.all_names).filter((n) => n !== role.canonical_name),
    relatedEntities: Array.from(role.related_entities),
    isIsolated,
  };
}

function resolveDisplayPower(role: UnifiedRole): string | null {
  const candidates = [role.primary_power, ...(role.powers ?? [])]
    .map((value) => (value ?? '').trim())
    .filter(Boolean);

  const concrete = candidates.find((value) => !GENERIC_POWER_LABELS.has(value));
  return concrete ?? null;
}

export function unifiedRolesToNodes(
  kb: UnifiedKnowledgeBase,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
): RoleNodeUnified[] {
  const nodes: RoleNodeUnified[] = [];

  for (const role of Object.values(kb.roles)) {
    const units = getRoleUnits(role);
    if (!inUnitRange(units, unitRange)) continue;
    if (!roleMatchesProgressRange(kb, role, unitRange, progressRange)) continue;

    nodes.push(toRoleNode(role, unitRange));
  }

  return nodes.sort((a, b) => b.appearances - a.appearances);
}

export function unifiedNetworkGraphData(
  kb: UnifiedKnowledgeBase,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
): {
  allNodes: RoleNodeUnified[];
  linkedNodes: RoleNodeUnified[];
  isolatedNodes: RoleNodeUnified[];
  links: RoleLinkUnified[];
  totalRoleCount: number;
  linkedRoleCount: number;
} {
  const links: RoleLinkUnified[] = [];

  for (const relation of Object.values(kb.relations)) {
    const sourceUnits = getRelationUnits(relation);
    if (!inUnitRange(sourceUnits, unitRange)) continue;
    if (!relationOverlapsProgressRange(relation, progressRange)) continue;

    const sourceId = kb.name_to_role_id[relation.from_entity];
    const targetId = kb.name_to_role_id[relation.to_entity];
    if (!sourceId || !targetId || !kb.roles[sourceId] || !kb.roles[targetId]) continue;

    links.push({
      source: sourceId,
      target: targetId,
      action: relation.primary_action,
      weight: relation.interaction_count,
      timeText: relation.first_interaction_text ?? relation.first_interaction_time,
      progressStart: relation.progress_start ?? null,
      progressEnd: relation.progress_end ?? null,
      progressLabel: relation.progress_label ?? null,
      actionTypes: relation.action_types,
      contexts: relation.contexts,
      sourceUnits,
    });
  }

  const allNodes = unifiedRolesToNodes(kb, unitRange, progressRange);
  const nodeIds = new Set<string>();
  for (const link of links) {
    nodeIds.add(link.source);
    nodeIds.add(link.target);
  }

  const linkedNodes = allNodes
    .filter((node) => nodeIds.has(node.id))
    .map((node) => ({ ...node, isIsolated: false }))
    .sort((a, b) => b.appearances - a.appearances);

  const isolatedNodes = allNodes
    .filter((node) => !nodeIds.has(node.id))
    .map((node) => ({ ...node, isIsolated: true }))
    .sort((a, b) => b.appearances - a.appearances);

  return {
    allNodes,
    linkedNodes,
    isolatedNodes,
    links,
    totalRoleCount: allNodes.length,
    linkedRoleCount: linkedNodes.length,
  };
}

export function unifiedEventsToTimeline(
  kb: UnifiedKnowledgeBase,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
): TimelineEventUnified[] {
  const events: TimelineEventUnified[] = [];

  for (const event of Object.values(kb.events)) {
    const units = getEventUnits(event);
    if (!inUnitRange(units, unitRange)) continue;
    if (!eventOverlapsProgressRange(event, progressRange)) continue;

    events.push({
      id: event.id,
      name: event.name,
      timeText: event.time_text ?? event.time,
      timeNumeric: event.time_start,
      progressStart: event.progress_start ?? null,
      progressEnd: event.progress_end ?? null,
      progressLabel: event.progress_label ?? null,
      location: event.location,
      participants: Array.from(event.participants),
      description: event.description,
      unitIndex: units[0] || 0,
      type: 'event',
      significance: event.significance,
      background: event.background,
    });
  }

  return events.sort((a, b) => {
    if (a.progressStart === null && b.progressStart === null) return 0;
    if (a.progressStart === null) return 1;
    if (b.progressStart === null) return -1;
    return a.progressStart - b.progressStart;
  });
}

export function unifiedLocationsToList(
  kb: UnifiedKnowledgeBase,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
): UnifiedLocation[] {
  const inRangeEvents = new Set(
    Object.values(kb.events)
      .filter((event) => inUnitRange(getEventUnits(event), unitRange) && eventOverlapsProgressRange(event, progressRange))
      .map((event) => event.id)
  );

  return Object.values(kb.locations)
    .filter((location) => {
      if (!inUnitRange(getLocationUnits(location), unitRange)) return false;
      if (progressRange[0] === null && progressRange[1] === null) return true;
      return (location.associated_events ?? []).some((eventId) => inRangeEvents.has(eventId));
    })
    .sort((a, b) => b.total_mentions - a.total_mentions);
}

export function calculateUnifiedPowerDistribution(
  kb: UnifiedKnowledgeBase,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
): PowerDistributionUnified[] {
  const distribution = new Map<string, { count: number; roles: string[] }>();

  for (const role of Object.values(kb.roles)) {
    const displayPower = resolveDisplayPower(role);
    const units = getRoleUnits(role);
    if (!inUnitRange(units, unitRange)) continue;

    if (progressRange[0] !== null || progressRange[1] !== null) {
      const relatedEvent = Object.values(kb.events).some(
        (event) =>
          event.participants.includes(role.canonical_name) &&
          inUnitRange(getEventUnits(event), unitRange) &&
          eventOverlapsProgressRange(event, progressRange)
      );
      if (!relatedEvent) continue;
    }

    const bucket = displayPower ?? '其他';
    const entry = distribution.get(bucket) ?? { count: 0, roles: [] };
    entry.count += 1;
    entry.roles.push(role.id);
    distribution.set(bucket, entry);
  }

  return Array.from(distribution.entries())
    .map(([power, value]) => ({ power, count: value.count, roles: value.roles }))
    .sort((a, b) => b.count - a.count);
}

export function searchUnifiedKnowledgeBase(
  kb: UnifiedKnowledgeBase,
  query: string,
  limit: number = 20
) {
  const results: Array<{
    type: 'role' | 'location' | 'event';
    id: string;
    name: string;
    description: string;
    score: number;
  }> = [];

  const queryLower = query.toLowerCase();

  for (const role of Object.values(kb.roles)) {
    let score = 0;
    const nameLower = role.canonical_name.toLowerCase();

    if (nameLower === queryLower) score += 100;
    else if (nameLower.includes(queryLower)) score += 50;

    for (const alias of role.all_names) {
      const aliasLower = alias.toLowerCase();
      if (aliasLower === queryLower) score += 80;
      else if (aliasLower.includes(queryLower)) score += 30;
    }

    if (role.description.includes(query)) score += 10;

    if (score > 0) {
      results.push({
        type: 'role',
        id: role.id,
        name: role.canonical_name,
        description: role.description,
        score,
      });
    }
  }

  for (const location of Object.values(kb.locations)) {
    let score = 0;

    if (location.canonical_name === query) score += 100;
    else if (location.canonical_name.includes(query)) score += 50;

    for (const alias of location.all_names) {
      if (alias === query) score += 80;
      else if (alias.includes(query)) score += 30;
    }

    if (location.description.includes(query)) score += 10;
    if (location.modern_name.includes(query)) score += 20;

    if (score > 0) {
      results.push({
        type: 'location',
        id: location.id,
        name: location.canonical_name,
        description: location.description,
        score,
      });
    }
  }

  for (const event of Object.values(kb.events)) {
    let score = 0;

    if (event.name === query) score += 100;
    else if (event.name.includes(query)) score += 50;

    if (event.description.includes(query)) score += 10;

    if (score > 0) {
      results.push({
        type: 'event',
        id: event.id,
        name: event.name,
        description: event.description,
        score,
      });
    }
  }

  return results.sort((a, b) => b.score - a.score).slice(0, limit);
}

export function resolveName(kb: UnifiedKnowledgeBase, name: string): string | null {
  return kb.name_to_role_id[name] || null;
}

export function getRoleByName(kb: UnifiedKnowledgeBase, name: string): UnifiedRole | null {
  const id = kb.name_to_role_id[name];
  if (id) return kb.roles[id] || null;
  return null;
}

export function getRelationsForEntity(kb: UnifiedKnowledgeBase, entityId: string): UnifiedRelation[] {
  const relations: UnifiedRelation[] = [];

  for (const relation of Object.values(kb.relations)) {
    const fromId = kb.name_to_role_id[relation.from_entity];
    const toId = kb.name_to_role_id[relation.to_entity];

    if (fromId === entityId || toId === entityId) {
      relations.push(relation);
    }
  }

  return relations.sort((a, b) => b.interaction_count - a.interaction_count);
}

export function getKnowledgeBaseSummary(kb: UnifiedKnowledgeBase) {
  const powerDistribution = calculateUnifiedPowerDistribution(kb);
  const roles = Object.values(kb.roles).sort((a, b) => b.total_mentions - a.total_mentions);

  return {
    totalRoles: kb.total_roles,
    totalLocations: kb.total_locations,
    totalEvents: kb.total_events,
    totalRelations: kb.total_relations,
    totalPowers: Object.keys(kb.power_to_roles).length,
    unitsProcessed: kb.juans_processed.length,
    topPowers: powerDistribution.slice(0, 10).map((p) => ({ power: p.power, count: p.count })),
    mostMentionedRoles: roles.slice(0, 10).map((r) => ({
      name: r.canonical_name,
      mentions: r.total_mentions,
    })),
  };
}
