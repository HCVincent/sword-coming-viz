import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useBookConfig, useChapterIndex, useUnitProgressIndex } from './hooks/useBookArtifacts';
import { useUnifiedKnowledgeBase, useUnifiedVisualizationData } from './hooks/useUnifiedData';
import { useFilteredWriterInsights, useWriterInsights } from './hooks/useWriterInsights';
import {
  ConflictChainsView,
  EventDetail,
  FilterControls,
  ForeshadowingView,
  LocationDetail,
  LocationsView,
  NetworkGraph,
  NetworkRoleRelationsDetail,
  PowerChart,
  RelationDetail,
  RoleDetail,
  RoleListModal,
  Timeline,
  WriterArcsView,
} from './components';
import { parseUrlGlobalContext, type TabType, writeUrlGlobalContext } from './state';
import type {
  RoleLinkUnified,
  RoleNodeUnified,
  TimelineEventUnified,
  UnifiedEvent,
  UnifiedKnowledgeBase,
  UnifiedLocation,
} from './types/unified';
import type { WriterInsightEventRef } from './types/writerInsights';
import { toChineseRelationshipKind } from './utils/writerInsightText';

interface SelectedRelationPair {
  sourceId: string;
  targetId: string;
  sourceName: string;
  targetName: string;
  relations: RoleLinkUnified[];
}

interface RoleRelationGroup {
  counterpartId: string;
  counterpartName: string;
  relations: RoleLinkUnified[];
  totalWeight: number;
  actionTypes: string[];
  sourceUnits: number[];
  earliestProgress: number | null;
}

interface RoleListConfig {
  title: string;
  subtitle?: string;
  roleIds: string[];
}

type ModalHistoryEntry =
  | { kind: 'eventDetail'; tab: TabType; focusRoleId: string | null; event: TimelineEventUnified }
  | { kind: 'roleDetail'; tab: TabType; focusRoleId: string | null; role: RoleNodeUnified }
  | { kind: 'networkRoleRelations'; tab: TabType; focusRoleId: string | null; role: RoleNodeUnified }
  | { kind: 'locationDetail'; tab: TabType; focusRoleId: string | null; location: UnifiedLocation }
  | { kind: 'relationDetail'; tab: TabType; focusRoleId: string | null; relationPair: SelectedRelationPair }
  | { kind: 'roleList'; tab: TabType; focusRoleId: string | null; config: RoleListConfig };

function toTimelineEvent(event: UnifiedEvent): TimelineEventUnified {
  const units = event.source_units && event.source_units.length > 0 ? event.source_units : event.source_juans;
  return {
    id: event.id,
    name: event.name,
    timeText: event.time_text ?? event.time,
    timeNumeric: event.time_start,
    progressStart: event.progress_start ?? null,
    progressEnd: event.progress_end ?? null,
    progressLabel: event.progress_label ?? null,
    location: event.location,
    participants: Array.from(event.participants ?? []),
    description: event.description,
    unitIndex: units[0] || 0,
    type: 'event',
    significance: event.significance,
    background: event.background,
  };
}

const GENERIC_POWER_LABELS = new Set(['山上', '山下', '山水', '江湖', '道家', '武道', '未归类']);

function resolveDisplayPowerFromRole(role: { primary_power: string | null; powers?: string[] }): string | null {
  const candidates = [role.primary_power, ...(role.powers ?? [])].map((v) => (v ?? '').trim()).filter(Boolean);
  return candidates.find((v) => !GENERIC_POWER_LABELS.has(v)) ?? null;
}

function toRoleNode(role: UnifiedKnowledgeBase['roles'][string]): RoleNodeUnified {
  return {
    id: role.id,
    name: role.canonical_name,
    power: resolveDisplayPowerFromRole(role),
    description: role.description,
    appearances: role.total_mentions,
    units: role.units_appeared && role.units_appeared.length > 0 ? role.units_appeared : role.juans_appeared,
    aliases: Array.from(role.all_names || []).filter((name) => name !== role.canonical_name),
    relatedEntities: Array.from(role.related_entities || []),
  };
}

function insightEventToTimeline(ref: WriterInsightEventRef): TimelineEventUnified {
  return {
    id: ref.event_id,
    name: ref.name,
    timeText: null,
    timeNumeric: null,
    progressStart: ref.progress_start,
    progressEnd: ref.progress_end,
    progressLabel: ref.progress_label ?? null,
    location: ref.location,
    participants: Array.from(ref.participants ?? []),
    description: ref.description,
    unitIndex: ref.unit_index ?? 0,
    type: 'event',
    significance: ref.significance,
    background: '',
  };
}

function resolveRoleId(kb: UnifiedKnowledgeBase | null, nameOrId: string): string | null {
  if (!kb) return null;
  if (kb.roles?.[nameOrId]) return nameOrId;
  const fromIndex = kb.name_to_role_id?.[nameOrId];
  if (fromIndex && kb.roles?.[fromIndex]) return fromIndex;
  for (const role of Object.values(kb.roles ?? {})) {
    if (role.all_names?.includes(nameOrId)) return role.id;
  }
  return null;
}

function App() {
  const { kb, loading: kbLoading, error: kbError } = useUnifiedKnowledgeBase();
  const { writerInsights, loading: writerLoading, error: writerError } = useWriterInsights();
  const { bookConfig } = useBookConfig();
  const { chapterIndex } = useChapterIndex();
  const { unitProgressIndex } = useUnitProgressIndex();
  const [searchParams, setSearchParams] = useSearchParams();

  const maxUnit = unitProgressIndex?.total_units ?? 328;
  const dashboardRef = useRef<HTMLElement | null>(null);
  const workbenchRef = useRef<HTMLElement | null>(null);

  const [unitRange, setUnitRange] = useState<[number, number]>([1, maxUnit]);
  const [progressRange, setProgressRange] = useState<[number | null, number | null]>([null, null]);
  const [activeTab, setActiveTab] = useState<TabType>('timeline');
  const [syncUnitProgress, setSyncUnitProgress] = useState(true);
  const [showMobileFilters, setShowMobileFilters] = useState(false);

  const [selectedEvent, setSelectedEvent] = useState<TimelineEventUnified | null>(null);
  const [selectedRole, setSelectedRole] = useState<RoleNodeUnified | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<UnifiedLocation | null>(null);
  const [selectedRelationPair, setSelectedRelationPair] = useState<SelectedRelationPair | null>(null);
  const [roleListConfig, setRoleListConfig] = useState<RoleListConfig | null>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [modalHistory, setModalHistory] = useState<ModalHistoryEntry[]>([]);

  const {
    nodes: roles,
    networkNodes,
    isolatedNodes,
    links: roleLinks,
    totalRoleCount,
    linkedRoleCount,
    timelineEvents: rawTimelineEvents,
    locations,
    powerDistribution,
  } = useUnifiedVisualizationData(kb, unitRange, progressRange);

  const { seasonOverviews, characterArcs, curatedRelationships, conflictChains, foreshadowingThreads } =
    useFilteredWriterInsights(writerInsights, unitRange, progressRange);

  const rolesRef = useRef<RoleNodeUnified[]>([]);
  const roleLinksRef = useRef<RoleLinkUnified[]>([]);

  useEffect(() => {
    rolesRef.current = roles;
  }, [roles]);

  useEffect(() => {
    roleLinksRef.current = roleLinks;
  }, [roleLinks]);

  const addSeasonPrefixToEvent = useCallback(
    (event: TimelineEventUnified): TimelineEventUnified => {
      const unit = chapterIndex?.units.find((item) => item.unit_index === event.unitIndex);
      if (!unit?.season_name || !event.progressLabel || event.progressLabel.startsWith(unit.season_name)) {
        return event;
      }
      return {
        ...event,
        progressLabel: `${unit.season_name} · ${event.progressLabel}`,
      };
    },
    [chapterIndex]
  );

  const timelineEvents = useMemo(
    () => rawTimelineEvents.map((event) => addSeasonPrefixToEvent(event)),
    [addSeasonPrefixToEvent, rawTimelineEvents]
  );

  const clearModalSelections = useCallback(() => {
    setSelectedEvent(null);
    setSelectedRole(null);
    setSelectedLocation(null);
    setSelectedRelationPair(null);
    setRoleListConfig(null);
  }, []);

  const currentModalEntry = useMemo<ModalHistoryEntry | null>(() => {
    if (roleListConfig) {
      return { kind: 'roleList', tab: activeTab, focusRoleId: focusNodeId, config: roleListConfig };
    }
    if (selectedRelationPair) {
      return { kind: 'relationDetail', tab: activeTab, focusRoleId: focusNodeId, relationPair: selectedRelationPair };
    }
    if (selectedLocation) {
      return { kind: 'locationDetail', tab: activeTab, focusRoleId: focusNodeId, location: selectedLocation };
    }
    if (selectedRole) {
      return activeTab === 'network'
        ? { kind: 'networkRoleRelations', tab: activeTab, focusRoleId: focusNodeId, role: selectedRole }
        : { kind: 'roleDetail', tab: activeTab, focusRoleId: focusNodeId, role: selectedRole };
    }
    if (selectedEvent) {
      return { kind: 'eventDetail', tab: activeTab, focusRoleId: focusNodeId, event: selectedEvent };
    }
    return null;
  }, [activeTab, focusNodeId, roleListConfig, selectedEvent, selectedLocation, selectedRelationPair, selectedRole]);

  const selectionFromModalEntry = useCallback((entry: ModalHistoryEntry | null) => {
    if (!entry) return undefined;
    switch (entry.kind) {
      case 'eventDetail':
        return { type: 'event' as const, id: entry.event.id };
      case 'roleDetail':
      case 'networkRoleRelations':
        return { type: 'role' as const, id: entry.role.id };
      case 'locationDetail':
        return { type: 'location' as const, id: entry.location.id };
      case 'relationDetail':
        return {
          type: 'relationPair' as const,
          sourceId: entry.relationPair.sourceId,
          targetId: entry.relationPair.targetId,
        };
      case 'roleList':
        return undefined;
    }
  }, []);

  const applyModalEntry = useCallback(
    (entry: ModalHistoryEntry | null) => {
      clearModalSelections();
      if (!entry) return;
      setActiveTab(entry.tab);
      setFocusNodeId(entry.focusRoleId);
      switch (entry.kind) {
        case 'eventDetail':
          setSelectedEvent(entry.event);
          return;
        case 'roleDetail':
        case 'networkRoleRelations':
          setSelectedRole(entry.role);
          return;
        case 'locationDetail':
          setSelectedLocation(entry.location);
          return;
        case 'relationDetail':
          setSelectedRelationPair(entry.relationPair);
          return;
        case 'roleList':
          setRoleListConfig(entry.config);
          return;
      }
    },
    [clearModalSelections]
  );

  const unitEntries = useMemo(() => {
    const units = unitProgressIndex?.units ?? {};
    return Object.values(units).sort((a, b) => a.unit_index - b.unit_index);
  }, [unitProgressIndex]);

  const normalizeUnitRange = useCallback(
    (range: [number, number]): [number, number] => {
      let [start, end] = range;
      start = Math.max(1, Math.min(maxUnit, start));
      end = Math.max(1, Math.min(maxUnit, end));
      return start <= end ? [start, end] : [end, start];
    },
    [maxUnit]
  );

  const normalizeProgressRange = useCallback(
    (range: [number | null, number | null]): [number | null, number | null] => {
      const [start, end] = range;
      if (start === null || end === null) return [start, end];
      return start <= end ? [start, end] : [end, start];
    },
    []
  );

  const deriveProgressRangeFromUnitRange = useCallback(
    (range: [number, number]): [number | null, number | null] | null => {
      if (!unitEntries.length) return null;
      const filtered = unitEntries.filter((entry) => entry.unit_index >= range[0] && entry.unit_index <= range[1]);
      if (!filtered.length) return null;
      return [filtered[0].progress_start, filtered[filtered.length - 1].progress_end];
    },
    [unitEntries]
  );

  const deriveUnitRangeFromProgressRange = useCallback(
    (range: [number | null, number | null]): [number, number] | null => {
      if (!unitEntries.length) return null;
      const [start, end] = normalizeProgressRange(range);
      if (start === null && end === null) return null;
      const effectiveStart = start ?? -Infinity;
      const effectiveEnd = end ?? Infinity;
      const overlapping = unitEntries.filter(
        (entry) => entry.progress_end >= effectiveStart && entry.progress_start <= effectiveEnd
      );
      if (!overlapping.length) return null;
      return [overlapping[0].unit_index, overlapping[overlapping.length - 1].unit_index];
    },
    [normalizeProgressRange, unitEntries]
  );

  useEffect(() => {
    const ctx = parseUrlGlobalContext(searchParams, maxUnit);
    const normalizedTab = ctx.tab === 'map' ? 'timeline' : ctx.tab;
    setActiveTab(normalizedTab);
    setUnitRange((prev) => (prev[0] === ctx.unitRange[0] && prev[1] === ctx.unitRange[1] ? prev : ctx.unitRange));
    setProgressRange((prev) =>
      prev[0] === ctx.progressRange[0] && prev[1] === ctx.progressRange[1] ? prev : ctx.progressRange
    );
    setFocusNodeId(ctx.focusRoleId ?? null);

    if (ctx.tab === 'map') {
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'timeline',
        unitRange: ctx.unitRange,
        progressRange: ctx.progressRange,
        focusRoleId: ctx.focusRoleId,
        selection: ctx.selection,
      });
      next.delete('mapLoc');
      setSearchParams(next, { replace: true });
    }

    const selection = ctx.selection;
    if (!kb || !selection) {
      setSelectedEvent(null);
      setSelectedRole(null);
      setSelectedLocation(null);
      setSelectedRelationPair(null);
      return;
    }

    if (selection.type === 'event') {
      const event = kb.events?.[selection.id];
      setSelectedEvent(event ? addSeasonPrefixToEvent(toTimelineEvent(event)) : null);
      setSelectedRole(null);
      setSelectedLocation(null);
      setSelectedRelationPair(null);
      return;
    }

    if (selection.type === 'role') {
      const role = kb.roles?.[selection.id];
      setSelectedRole(role ? toRoleNode(role) : null);
      setSelectedEvent(null);
      setSelectedLocation(null);
      setSelectedRelationPair(null);
      return;
    }

    if (selection.type === 'location') {
      setSelectedLocation(kb.locations?.[selection.id] ?? null);
      setSelectedEvent(null);
      setSelectedRole(null);
      setSelectedRelationPair(null);
      return;
    }

    if (selection.type === 'relationPair') {
      const relations = roleLinksRef.current.filter((link) => {
        const linkSourceId = typeof link.source === 'object' ? (link.source as never as { id: string }).id : link.source;
        const linkTargetId = typeof link.target === 'object' ? (link.target as never as { id: string }).id : link.target;
        return (
          (linkSourceId === selection.sourceId && linkTargetId === selection.targetId) ||
          (linkSourceId === selection.targetId && linkTargetId === selection.sourceId)
        );
      });
      const sourceNode = rolesRef.current.find((node) => node.id === selection.sourceId);
      const targetNode = rolesRef.current.find((node) => node.id === selection.targetId);
      setSelectedRelationPair({
        sourceId: selection.sourceId,
        targetId: selection.targetId,
        sourceName: sourceNode?.name || selection.sourceId,
        targetName: targetNode?.name || selection.targetId,
        relations,
      });
      setSelectedEvent(null);
      setSelectedRole(null);
      setSelectedLocation(null);
    }
  }, [addSeasonPrefixToEvent, kb, maxUnit, searchParams]);

  const selectionForUrl = useMemo(() => {
    if (selectedEvent) return { type: 'event' as const, id: selectedEvent.id };
    if (selectedRole) return { type: 'role' as const, id: selectedRole.id };
    if (selectedLocation) return { type: 'location' as const, id: selectedLocation.id };
    if (selectedRelationPair) {
      return {
        type: 'relationPair' as const,
        sourceId: selectedRelationPair.sourceId,
        targetId: selectedRelationPair.targetId,
      };
    }
    return undefined;
  }, [selectedEvent, selectedLocation, selectedRelationPair, selectedRole]);

  const updateUrlContext = useCallback(
    (
      next: Partial<{
        tab: TabType;
        unitRange: [number, number];
        progressRange: [number | null, number | null];
        focusRoleId: string | undefined;
      }>,
      opts: { replace: boolean }
    ) => {
      const params = writeUrlGlobalContext(searchParams, {
        tab: next.tab ?? activeTab,
        unitRange: next.unitRange ?? unitRange,
        progressRange: next.progressRange ?? progressRange,
        focusRoleId: (next.focusRoleId ?? focusNodeId ?? undefined) as string | undefined,
        selection: selectionForUrl,
      });
      setSearchParams(params, { replace: opts.replace });
    },
    [activeTab, focusNodeId, progressRange, searchParams, selectionForUrl, setSearchParams, unitRange]
  );

  const clearSelectionFromUrl = useCallback(
    (tab: TabType) => {
      const next = writeUrlGlobalContext(searchParams, {
        tab,
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: undefined,
      });
      setSearchParams(next, { replace: false });
    },
    [focusNodeId, progressRange, searchParams, setSearchParams, unitRange]
  );

  const closeActiveModal = useCallback(() => {
    clearModalSelections();
    setModalHistory([]);
    clearSelectionFromUrl(activeTab);
  }, [activeTab, clearModalSelections, clearSelectionFromUrl]);

  const restorePreviousModal = useCallback(() => {
    if (!modalHistory.length) return;
    const previous = modalHistory[modalHistory.length - 1];
    setModalHistory((prev) => prev.slice(0, -1));
    applyModalEntry(previous);
    const next = writeUrlGlobalContext(searchParams, {
      tab: previous.tab,
      unitRange,
      progressRange,
      focusRoleId: previous.focusRoleId ?? undefined,
      selection: selectionFromModalEntry(previous),
    });
    setSearchParams(next, { replace: false });
  }, [applyModalEntry, modalHistory, progressRange, searchParams, selectionFromModalEntry, setSearchParams, unitRange]);

  const resolveTimelineEventById = useCallback(
    (eventId: string): TimelineEventUnified | null => {
      const existing = timelineEvents.find((event) => event.id === eventId);
      if (existing) return existing;
      const event = kb?.events?.[eventId];
      return event ? addSeasonPrefixToEvent(toTimelineEvent(event)) : null;
    },
    [addSeasonPrefixToEvent, kb, timelineEvents]
  );

  const switchTab = useCallback(
    (tab: TabType) => {
      setActiveTab(tab);
      clearModalSelections();
      setModalHistory([]);
      const next = writeUrlGlobalContext(searchParams, {
        tab,
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: undefined,
      });
      next.delete('mapLoc');
      setSearchParams(next, { replace: false });
      workbenchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [clearModalSelections, focusNodeId, progressRange, searchParams, setSearchParams, unitRange]
  );

  const openRoleDetail = useCallback(
    (roleName: string, tab: TabType = activeTab, options?: { pushCurrent?: boolean }) => {
      const roleId = resolveRoleId(kb, roleName);
      if (!roleId || !kb?.roles?.[roleId]) return;
      const role = toRoleNode(kb.roles[roleId]);
      if (options?.pushCurrent && currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      setActiveTab(tab);
      clearModalSelections();
      setSelectedRole(role);
      const next = writeUrlGlobalContext(searchParams, {
        tab,
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: { type: 'role', id: role.id },
      });
      setSearchParams(next, { replace: false });
    },
    [activeTab, clearModalSelections, currentModalEntry, focusNodeId, kb, progressRange, searchParams, setSearchParams, unitRange]
  );

  const openLocationDetail = useCallback(
    (locationName: string, tab: TabType = activeTab, options?: { pushCurrent?: boolean }) => {
      const location = locations.find(
        (item) => item.canonical_name === locationName || item.all_names?.includes(locationName)
      );
      if (!location) return;
      if (options?.pushCurrent && currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      setActiveTab(tab);
      clearModalSelections();
      setSelectedLocation(location);
      const next = writeUrlGlobalContext(searchParams, {
        tab,
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: { type: 'location', id: location.id },
      });
      setSearchParams(next, { replace: false });
    },
    [activeTab, clearModalSelections, currentModalEntry, focusNodeId, locations, progressRange, searchParams, setSearchParams, unitRange]
  );

  const openEventDetail = useCallback(
    (eventId: string, tab: TabType = activeTab, options?: { pushCurrent?: boolean; fallbackEvent?: TimelineEventUnified }) => {
      const event = resolveTimelineEventById(eventId) ?? options?.fallbackEvent ?? null;
      if (!event) return;
      if (options?.pushCurrent && currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      setActiveTab(tab);
      clearModalSelections();
      setSelectedEvent(event);
      /* Only write event selection into the URL if the event exists in kb.events,
         so the URL-sync useEffect won't null it out on the next render. */
      const kbHasEvent = Boolean(kb?.events?.[event.id]);
      const next = writeUrlGlobalContext(searchParams, {
        tab,
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: kbHasEvent ? { type: 'event', id: event.id } : undefined,
      });
      setSearchParams(next, { replace: false });
    },
    [activeTab, clearModalSelections, currentModalEntry, focusNodeId, kb, progressRange, resolveTimelineEventById, searchParams, setSearchParams, unitRange]
  );

  const openRoleList = useCallback(
    (config: RoleListConfig) => {
      if (currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      clearModalSelections();
      setRoleListConfig(config);
    },
    [clearModalSelections, currentModalEntry]
  );

  const handleFocusNode = useCallback(
    (entityName: string, options?: { pushCurrent?: boolean }) => {
      const roleId = resolveRoleId(kb, entityName);
      if (!roleId || !kb?.roles?.[roleId]) return;
      const role = toRoleNode(kb.roles[roleId]);
      if (options?.pushCurrent && currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      setActiveTab('network');
      setFocusNodeId(roleId);
      clearModalSelections();
      setSelectedRole(role);
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'network',
        unitRange,
        progressRange,
        focusRoleId: roleId,
        selection: { type: 'role', id: roleId },
      });
      setSearchParams(next, { replace: false });
      workbenchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [clearModalSelections, currentModalEntry, kb, progressRange, searchParams, setSearchParams, unitRange]
  );

  const handleLinkClick = useCallback(
    (sourceId: string, targetId: string, options?: { pushCurrent?: boolean }) => {
      const relations = roleLinks.filter((link) => {
        const linkSourceId = typeof link.source === 'object' ? (link.source as { id: string }).id : link.source;
        const linkTargetId = typeof link.target === 'object' ? (link.target as { id: string }).id : link.target;
        return (
          (linkSourceId === sourceId && linkTargetId === targetId) ||
          (linkSourceId === targetId && linkTargetId === sourceId)
        );
      });

      const sourceNode = roles.find((node) => node.id === sourceId);
      const targetNode = roles.find((node) => node.id === targetId);
      if (options?.pushCurrent && currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      setActiveTab('network');
      clearModalSelections();
      setSelectedRelationPair({
        sourceId,
        targetId,
        sourceName: sourceNode?.name || sourceId,
        targetName: targetNode?.name || targetId,
        relations,
      });

      const next = writeUrlGlobalContext(searchParams, {
        tab: 'network',
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: { type: 'relationPair', sourceId, targetId },
      });
      setSearchParams(next, { replace: false });
      workbenchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [clearModalSelections, currentModalEntry, focusNodeId, progressRange, roleLinks, roles, searchParams, setSearchParams, unitRange]
  );

  const openNetworkRoleRelations = useCallback(
    (roleId: string, options?: { pushCurrent?: boolean }) => {
      if (!kb?.roles?.[roleId]) return;
      const role = toRoleNode(kb.roles[roleId]);
      if (options?.pushCurrent && currentModalEntry) setModalHistory((prev) => [...prev, currentModalEntry]);
      else setModalHistory([]);
      setActiveTab('network');
      setFocusNodeId(roleId);
      clearModalSelections();
      setSelectedRole(role);
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'network',
        unitRange,
        progressRange,
        focusRoleId: role.id,
        selection: { type: 'role', id: role.id },
      });
      setSearchParams(next, { replace: false });
    },
    [clearModalSelections, currentModalEntry, kb, progressRange, searchParams, setSearchParams, unitRange]
  );

  const availableRoleIds = useMemo(() => new Set(roles.map((role) => role.id)), [roles]);

  const selectedRoleRelationGroups = useMemo<RoleRelationGroup[]>(() => {
    if (!selectedRole) return [];

    const groups = new Map<string, RoleRelationGroup>();
    for (const link of roleLinks) {
      const sourceId = typeof link.source === 'object' ? (link.source as { id: string }).id : link.source;
      const targetId = typeof link.target === 'object' ? (link.target as { id: string }).id : link.target;
      if (sourceId !== selectedRole.id && targetId !== selectedRole.id) continue;

      const counterpartId = sourceId === selectedRole.id ? targetId : sourceId;
      const counterpartNode = roles.find((node) => node.id === counterpartId);
      const existing = groups.get(counterpartId);
      if (existing) {
        existing.relations.push(link);
        existing.totalWeight += link.weight;
        existing.actionTypes = Array.from(new Set([...existing.actionTypes, ...link.actionTypes]));
        existing.sourceUnits = Array.from(new Set([...existing.sourceUnits, ...(link.sourceUnits || [])])).sort(
          (a, b) => a - b
        );
        if (link.progressStart !== null) {
          existing.earliestProgress =
            existing.earliestProgress === null ? link.progressStart : Math.min(existing.earliestProgress, link.progressStart);
        }
        continue;
      }

      groups.set(counterpartId, {
        counterpartId,
        counterpartName: counterpartNode?.name || counterpartId,
        relations: [link],
        totalWeight: link.weight,
        actionTypes: Array.from(new Set(link.actionTypes)),
        sourceUnits: Array.from(new Set(link.sourceUnits || [])).sort((a, b) => a - b),
        earliestProgress: link.progressStart,
      });
    }

    return Array.from(groups.values()).sort(
      (left, right) =>
        right.totalWeight - left.totalWeight ||
        right.relations.length - left.relations.length ||
        left.counterpartName.localeCompare(right.counterpartName, 'zh-CN')
    );
  }, [roleLinks, roles, selectedRole]);

  const selectedRoleRelatedNames = useMemo(() => {
    if (!selectedRole) return [];
    if (selectedRoleRelationGroups.length > 0) {
      return selectedRoleRelationGroups.map((group) => group.counterpartName);
    }
    return selectedRole.relatedEntities;
  }, [selectedRole, selectedRoleRelationGroups]);

  const roleListRoles = useMemo<RoleNodeUnified[]>(() => {
    if (!roleListConfig || !kb) return [];
    const idSet = new Set(roleListConfig.roleIds);
    return roles.filter((role) => idSet.has(role.id));
  }, [kb, roleListConfig, roles]);

  const unitLabel = bookConfig?.unit_label ?? kb?.unit_label ?? '章节';
  const progressLabel = bookConfig?.progress_label ?? kb?.progress_label ?? '叙事进度';
  const title = bookConfig?.title ?? '剑来';
  const subtitle = bookConfig?.subtitle ?? '原著内容可视化试点';
  const isolatedRoleCount = Math.max(totalRoleCount - linkedRoleCount, 0);
  const spotlightRoleName = writerInsights?.spotlight_role_name ?? null;

  const currentSeasonNames = useMemo(() => {
    const names = unitEntries
      .filter((entry) => entry.unit_index >= unitRange[0] && entry.unit_index <= unitRange[1])
      .map((entry) => entry.season_name);
    return Array.from(new Set(names));
  }, [unitEntries, unitRange]);

  const currentSeasonLabel = currentSeasonNames.length > 0 ? currentSeasonNames.join(' / ') : '当前范围';

  const spotlightArcInRange = useMemo(
    () =>
      characterArcs.find((arc) => arc.spotlight || (spotlightRoleName ? arc.role_name === spotlightRoleName : false)) ??
      null,
    [characterArcs, spotlightRoleName]
  );

  const spotlightArc = useMemo(
    () =>
      spotlightArcInRange ??
      writerInsights?.character_arcs.find(
        (arc) => arc.spotlight || (spotlightRoleName ? arc.role_name === spotlightRoleName : false)
      ) ??
      characterArcs[0] ??
      writerInsights?.character_arcs[0] ??
      null,
    [characterArcs, spotlightArcInRange, spotlightRoleName, writerInsights?.character_arcs]
  );

  const spotlightHasCurrentContent = Boolean(
    spotlightArcInRange &&
      (spotlightArcInRange.key_events.length > 0 || spotlightArcInRange.relationship_phases.length > 0)
  );

  const spotlightCounterparts = useMemo(() => {
    if (!spotlightArc) return [];
    const seen = new Set<string>();
    return spotlightArc.relationship_phases.filter((phase) => {
      const key = phase.counterpart_id || phase.counterpart_name;
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [spotlightArc]);

  const currentSeasonOverview = useMemo(() => {
    if (seasonOverviews.length === 0) return null;
    if (currentSeasonNames.length === 1) {
      return (
        seasonOverviews.find((overview) => overview.season_name === currentSeasonNames[0]) ??
        seasonOverviews[0] ??
        null
      );
    }
    return seasonOverviews.length === 1 ? seasonOverviews[0] : null;
  }, [currentSeasonNames, seasonOverviews]);

  const dashboardRoles = useMemo(
    () => {
      const preferredRoles =
        currentSeasonOverview?.priority_roles.length
          ? currentSeasonOverview.priority_roles
          : currentSeasonOverview?.top_roles ?? [];

      if (preferredRoles.length > 0) {
        const roleByName = new Map(roles.map((role) => [role.name, role]));
        return preferredRoles
          .map((item) => {
            const inRange = roleByName.get(item.role_name);
            if (inRange) return inRange;

            const roleId = resolveRoleId(kb, item.role_name);
            const role = roleId ? kb?.roles?.[roleId] : null;
            return role ? toRoleNode(role) : null;
          })
          .filter((role): role is RoleNodeUnified => Boolean(role))
          .slice(0, 8);
      }

      return [...roles]
        .sort((a, b) => b.appearances - a.appearances || a.name.localeCompare(b.name, 'zh-CN'))
        .slice(0, 8);
    },
    [currentSeasonOverview, kb, roles]
  );

  const dashboardLocations = useMemo(
    () =>
      [...locations]
        .sort(
          (a, b) =>
            (b.total_mentions ?? 0) - (a.total_mentions ?? 0) ||
            (b.associated_events?.length ?? 0) - (a.associated_events?.length ?? 0)
        )
        .slice(0, 5),
    [locations]
  );

  const dashboardRelationships = useMemo(() => {
    const preferredRelationships = currentSeasonOverview?.priority_relationships ?? [];
    if (preferredRelationships.length > 0) {
      const relationshipById = new Map(curatedRelationships.map((item) => [item.id, item]));
      return preferredRelationships
        .map((item) => relationshipById.get(item.relationship_id))
        .filter((relationship): relationship is (typeof curatedRelationships)[number] => Boolean(relationship))
        .slice(0, 4);
    }
    return curatedRelationships.slice(0, 4);
  }, [curatedRelationships, currentSeasonOverview]);

  const entryCards = useMemo(
    () => [
      { id: 'writerArcs' as const, label: '角色弧光', icon: '🎭', copy: '按季整理角色线、锚点事件和可改编线索。' },
      { id: 'conflicts' as const, label: '冲突链', icon: '⚔️', copy: '把关系变化压成对立、试探、转折和落点。' },
      { id: 'foreshadowing' as const, label: '伏笔回收', icon: '🪶', copy: '追踪前段埋线与后段兑现，方便抓改编回收。' },
      { id: 'network' as const, label: '人物关系网', icon: '🕸️', copy: '进入人物互动图谱，聚焦主线与支线关系群。' },
    ],
    []
  );

  const tabs: { id: TabType; label: string; icon: string }[] = [
    { id: 'timeline', label: '时间轴', icon: '📜' },
    { id: 'network', label: '关系网络', icon: '🕸️' },
    { id: 'power', label: '阵营分布', icon: '📊' },
    { id: 'locations', label: '地点', icon: '📍' },
    { id: 'writerArcs', label: '角色弧光', icon: '🎭' },
    { id: 'conflicts', label: '冲突链', icon: '⚔️' },
    { id: 'foreshadowing', label: '伏笔回收', icon: '🪶' },
  ];

  const modalBackHandler = modalHistory.length > 0 ? restorePreviousModal : undefined;
  const loading = kbLoading || writerLoading;
  const error = kbError ?? writerError;

  const applySeasonOverview = useCallback(
    (seasonName: string) => {
      const matched =
        seasonOverviews.find((item) => item.season_name === seasonName) ??
        writerInsights?.season_overviews.find((item) => item.season_name === seasonName);
      if (!matched) return;
      setUnitRange(matched.unit_range);
      setProgressRange(matched.progress_range);
      setActiveTab('writerArcs');
      setSelectedEvent(null);
      setSelectedRole(null);
      setSelectedLocation(null);
      setSelectedRelationPair(null);
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'writerArcs',
        unitRange: matched.unit_range,
        progressRange: matched.progress_range,
        focusRoleId: undefined,
        selection: undefined,
      });
      next.delete('mapLoc');
      setSearchParams(next, { replace: false });
      workbenchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [searchParams, seasonOverviews, setSearchParams, writerInsights?.season_overviews]
  );

  const applyQuickFilter = useCallback(
    (unitRangeValue: [number, number], progressRangeValue: [number, number]) => {
      setUnitRange(unitRangeValue);
      setProgressRange(progressRangeValue);
      const next = writeUrlGlobalContext(searchParams, {
        tab: activeTab,
        unitRange: unitRangeValue,
        progressRange: progressRangeValue,
        focusRoleId: undefined,
        selection: undefined,
      });
      next.delete('mapLoc');
      setSearchParams(next, { replace: false });
      dashboardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [activeTab, searchParams, setSearchParams]
  );

  if (loading) {
    return (
      <div className="app-shell">
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="paper-panel-strong panel-inner max-w-lg text-center">
            <p className="section-kicker">正在装载</p>
            <h1 className="section-title">正在整理《剑来》内容总览</h1>
            <p className="section-subtitle">正在装载人物、事件、地点、关系与编剧视图数据，请稍候。</p>
            <div className="mt-6 mx-auto h-12 w-12 rounded-full border-4 border-[var(--accent-deep)] border-t-transparent animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app-shell">
        <div className="min-h-screen flex items-center justify-center px-4">
          <div className="paper-panel-strong panel-inner max-w-xl text-center">
            <p className="section-kicker">读取异常</p>
            <h1 className="section-title">数据装载失败</h1>
            <p className="section-subtitle">{error}</p>
            <p className="status-note mt-4">请确认数据文件已经同步到 `visualization/public/data`，再重新启动前端。</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="hero-shell">
        <div className="shell-container hero-grid">
          <div className="hero-copy">
            <p className="hero-kicker">剑来内容总览</p>
            <h1 className="hero-title">{title}</h1>
            <p className="hero-subtitle">
              {subtitle}
              <br />
              这一版保留原有时间轴、人物网、地点、冲突链与伏笔分析，只把首屏整理成更容易先看全局、再细看人物的阅读页。
            </p>

            <div className="hero-meta">
              <span className="hero-chip">
                当前范围 <strong>{currentSeasonLabel}</strong>
              </span>
              <span className="hero-chip">
                {unitLabel} <strong>{unitRange[0]} - {unitRange[1]}</strong>
              </span>
              <span className="hero-chip">
                {progressLabel} <strong>{progressRange[0] ?? '不限'} - {progressRange[1] ?? '不限'}</strong>
              </span>
            </div>

            <div className="hero-ribbon">
              {bookConfig?.quick_filters.slice(0, 4).map((filter) => (
                <button
                  key={filter.label}
                  type="button"
                  className="hero-ribbon-item"
                  onClick={() => applyQuickFilter(filter.unit_range, filter.progress_range)}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <div className="hero-actions">
              <button
                type="button"
                className="hero-action-primary"
                onClick={() => dashboardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              >
                先看全局
              </button>
              <button type="button" className="hero-action-secondary" onClick={() => switchTab('writerArcs')}>
                看角色弧光
              </button>
            </div>
          </div>

          <div className="hero-side">
            <div className="hero-side-panel">
              <span className="hero-side-kicker">当前概况</span>
              <strong className="hero-side-value">
                {timelineEvents.length} 条事件 / {roleLinks.length} 条关系
              </strong>
              <p className="hero-side-copy">
                当前筛选范围内保留 {totalRoleCount} 位人物、{locations.length} 个地点，适合先看整体分布，再到下方继续细看。
              </p>
              <div className="hero-stat-grid">
                <div className="hero-stat">
                  <span className="hero-stat-label">关系网人物</span>
                  <strong className="hero-stat-value">{linkedRoleCount}</strong>
                </div>
                <div className="hero-stat">
                  <span className="hero-stat-label">孤立人物</span>
                  <strong className="hero-stat-value">{isolatedRoleCount}</strong>
                </div>
                <div className="hero-stat">
                  <span className="hero-stat-label">角色弧光</span>
                  <strong className="hero-stat-value">{characterArcs.length}</strong>
                </div>
                <div className="hero-stat">
                  <span className="hero-stat-label">冲突链</span>
                  <strong className="hero-stat-value">{conflictChains.length}</strong>
                </div>
              </div>
            </div>

            {spotlightArc && (
              <div className="hero-side-panel">
                <span className="hero-side-kicker">主角主线</span>
                <strong className="hero-side-value">{spotlightArc.role_name}</strong>
                <p className="hero-side-copy">{spotlightArc.summary}</p>
                {spotlightHasCurrentContent ? (
                  <div className="hero-meta mt-4">
                    {spotlightArc.key_locations.slice(0, 3).map((location) => (
                      <button
                        key={location}
                        type="button"
                        className="hero-chip"
                        onClick={() => openLocationDetail(location, 'locations')}
                      >
                        {location}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="status-note mt-4">当前范围内暂时没有整理好的陈平安片段，可先看下方关系和季别概览。</p>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="page-section">
        <div className="shell-container page-layout">
          <aside className="control-column">
            <div className="mobile-toolbar lg:hidden">
              <div>
                <div className="section-kicker">筛选</div>
                <div className="mobile-toolbar-copy">
                  当前范围 {unitRange[0]} - {unitRange[1]}，{progressLabel} {progressRange[0] ?? '不限'} -{' '}
                  {progressRange[1] ?? '不限'}。
                </div>
                </div>
                <button type="button" className="ink-button" onClick={() => setShowMobileFilters(true)}>
                  打开筛选
                </button>
              </div>

            <div className="desktop-control-stack">
              <div className="sticky-console">
                <FilterControls
                  bookConfig={bookConfig}
                  unitRange={unitRange}
                  onUnitRangeChange={(range) => {
                    const nextUnitRange = normalizeUnitRange(range);
                    setUnitRange(nextUnitRange);

                    if (syncUnitProgress) {
                      const derived = deriveProgressRangeFromUnitRange(nextUnitRange);
                      if (derived) {
                        setProgressRange(derived);
                        updateUrlContext({ unitRange: nextUnitRange, progressRange: derived }, { replace: true });
                        return;
                      }
                    }

                    updateUrlContext({ unitRange: nextUnitRange }, { replace: true });
                  }}
                  onUnitRangeCommit={(range) => {
                    const nextUnitRange = normalizeUnitRange(range);
                    if (syncUnitProgress) {
                      const derived = deriveProgressRangeFromUnitRange(nextUnitRange);
                      if (derived) {
                        setProgressRange(derived);
                        updateUrlContext({ unitRange: nextUnitRange, progressRange: derived }, { replace: false });
                        return;
                      }
                    }
                    updateUrlContext({ unitRange: nextUnitRange }, { replace: false });
                  }}
                  maxUnit={maxUnit}
                  progressRange={progressRange}
                  onProgressRangeChange={(range) => {
                    const nextProgressRange = normalizeProgressRange(range);
                    setProgressRange(nextProgressRange);

                    if (syncUnitProgress) {
                      const derived = deriveUnitRangeFromProgressRange(nextProgressRange);
                      if (derived) {
                        setUnitRange(derived);
                        updateUrlContext({ unitRange: derived, progressRange: nextProgressRange }, { replace: true });
                        return;
                      }
                    }

                    updateUrlContext({ progressRange: nextProgressRange }, { replace: true });
                  }}
                  onProgressRangeCommit={(range) => {
                    const nextProgressRange = normalizeProgressRange(range);
                    if (syncUnitProgress) {
                      const derived = deriveUnitRangeFromProgressRange(nextProgressRange);
                      if (derived) {
                        setUnitRange(derived);
                        updateUrlContext({ unitRange: derived, progressRange: nextProgressRange }, { replace: false });
                        return;
                      }
                    }
                    updateUrlContext({ progressRange: nextProgressRange }, { replace: false });
                  }}
                  syncUnitProgress={syncUnitProgress}
                  syncAvailable={Boolean(unitProgressIndex)}
                  onSyncUnitProgressChange={(enabled) => {
                    setSyncUnitProgress(enabled);
                    if (!enabled) return;
                    const derived = deriveProgressRangeFromUnitRange(unitRange);
                    if (derived) {
                      setProgressRange(derived);
                      updateUrlContext({ progressRange: derived }, { replace: true });
                    }
                  }}
                />

                <section className="paper-panel">
                  <div className="panel-inner">
                    <p className="section-kicker">数据概况</p>
                    <h2 className="section-title">当前数据密度</h2>
                    <p className="section-subtitle">左侧保持原有范围筛选逻辑，只把信息组织成更适合连续决策的控制台。</p>
                    <div className="stats-list mt-6">
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => openRoleList({ title: '全部人物', roleIds: roles.map((r) => r.id) })}>
                        <span>人物总数</span>
                        <strong>{totalRoleCount}</strong>
                      </button>
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => openRoleList({ title: '关系网人物', subtitle: '至少有一条关系边的人物', roleIds: networkNodes.map((r) => r.id) })}>
                        <span>关系网人物</span>
                        <strong>{linkedRoleCount}</strong>
                      </button>
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => openRoleList({ title: '孤立人物', subtitle: '当前范围内没有关系边的人物', roleIds: isolatedNodes.map((r) => r.id) })}>
                        <span>孤立人物</span>
                        <strong>{isolatedRoleCount}</strong>
                      </button>
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => switchTab('timeline')}>
                        <span>事件</span>
                        <strong>{timelineEvents.length}</strong>
                      </button>
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => switchTab('locations')}>
                        <span>地点</span>
                        <strong>{locations.length}</strong>
                      </button>
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => switchTab('writerArcs')}>
                        <span>人工主线</span>
                        <strong>{curatedRelationships.length}</strong>
                      </button>
                      <button type="button" className="stats-row stats-row--clickable" onClick={() => switchTab('foreshadowing')}>
                        <span>伏笔线</span>
                        <strong>{foreshadowingThreads.length}</strong>
                      </button>
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </aside>

          <section className="workbench-shell">
            <section ref={dashboardRef} className="paper-panel-strong">
              <div className="panel-inner">
                <div className="view-header">
                  <div>
                    <p className="section-kicker">先看全局</p>
                    <h2 className="section-title">先看全局</h2>
                    <p className="section-subtitle">先在这里看清这一段主要人物、关系和地点，再往下继续细看。</p>
                  </div>
                  <div className="view-toolbar">
                    <button type="button" className="ghost-button" onClick={() => switchTab('timeline')}>
                      看时间轴
                    </button>
                    <button type="button" className="outline-button" onClick={() => switchTab('network')}>
                      进关系网
                    </button>
                  </div>
                </div>

                <dl className="metric-grid">
                  <button type="button" className="metric-card metric-card--clickable" onClick={() => switchTab('writerArcs')}>
                    <dt>当前季别</dt>
                    <dd>{currentSeasonLabel}</dd>
                  </button>
                  <button type="button" className="metric-card metric-card--clickable" onClick={() => switchTab('timeline')}>
                    <dt>剧情事件</dt>
                    <dd>{timelineEvents.length}</dd>
                  </button>
                  <button type="button" className="metric-card metric-card--clickable" onClick={() => switchTab('network')}>
                    <dt>人物密度</dt>
                    <dd>{totalRoleCount}</dd>
                  </button>
                  <button type="button" className="metric-card metric-card--clickable" onClick={() => switchTab('writerArcs')}>
                    <dt>可改编线索</dt>
                    <dd>{seasonOverviews.length + curatedRelationships.length}</dd>
                  </button>
                </dl>

                <div className="dashboard-grid mt-6">
                  <article className="dashboard-card lg:col-span-8">
                    <p className="dashboard-eyebrow">分季查看</p>
                    <h3 className="dashboard-title">分季概览</h3>
                    <p className="dashboard-copy">每张季别卡都会把范围、主线摘要和三拍结构列出来，点卡后会同步筛选并跳到角色弧光页。</p>
                    <div className="masonry-two mt-5">
                      {(seasonOverviews.length > 0 ? seasonOverviews : writerInsights?.season_overviews ?? [])
                        .slice(0, 3)
                        .map((overview) => (
                          <button
                            key={overview.season_name}
                            type="button"
                            className="dashboard-card dashboard-card--clickable text-left"
                            onClick={() => applySeasonOverview(overview.season_name)}
                          >
                            <p className="dashboard-eyebrow">{overview.season_name}</p>
                            <h4 className="dashboard-title">
                              {unitLabel} {overview.unit_range[0]} - {overview.unit_range[1]}
                            </h4>
                            <p className="dashboard-copy">{overview.summary}</p>
                            <div className="dashboard-meta-row">
                              {overview.story_beats.slice(0, 3).map((beat) => (
                                <span key={`${overview.season_name}-${beat.beat_type}`} className="dashboard-pill">
                                  {beat.label}
                                </span>
                              ))}
                            </div>
                          </button>
                        ))}
                    </div>
                  </article>

                  <article className="dashboard-card lg:col-span-4">
                    <p className="dashboard-eyebrow">主角主线</p>
                    <h3 className="dashboard-title">主角主线</h3>
                    {spotlightArc ? (
                      <>
                        <div className="dashboard-stat-display">
                          <strong>{spotlightArc.role_name}</strong>
                          <span>当前重点人物</span>
                        </div>
                        <p className="dashboard-copy">{spotlightArc.summary}</p>
                        {spotlightHasCurrentContent ? (
                          <div className="dashboard-meta-row">
                            {spotlightCounterparts.slice(0, 4).map((phase) => (
                              <button
                                key={`${spotlightArc.role_id}-${phase.relation_id}-${phase.counterpart_id}`}
                                type="button"
                                className="dashboard-pill"
                                onClick={() => openRoleDetail(phase.counterpart_name, 'writerArcs')}
                              >
                                {phase.counterpart_name}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <div className="empty-state mt-4">当前范围内暂无已整理的陈平安片段。</div>
                        )}
                        <div className="dashboard-meta-row">
                          <button type="button" className="ink-button" onClick={() => openRoleDetail(spotlightArc.role_name, 'writerArcs')}>
                            查看角色弧光
                          </button>
                          <button type="button" className="outline-button" onClick={() => handleFocusNode(spotlightArc.role_name)}>
                            聚焦关系网
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="empty-state mt-5">当前范围内暂时没有可展示的主角弧光。</div>
                    )}
                  </article>

                  <article className="dashboard-card lg:col-span-5">
                    <p className="dashboard-eyebrow">重点关系</p>
                    <h3 className="dashboard-title">优先关系</h3>
                    <div className="insight-list mt-5">
                      {dashboardRelationships.length > 0 ? (
                        dashboardRelationships.map((relationship) => (
                          <button
                              key={relationship.id}
                              type="button"
                              className="detail-card text-left"
                              onClick={() => handleLinkClick(relationship.source_role_id, relationship.target_role_id)}
                            >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <strong className="text-lg font-semibold text-[var(--accent-deep)]">{relationship.title}</strong>
                              <span className="tag-pill">{toChineseRelationshipKind(relationship.kind)}</span>
                            </div>
                            <p className="dashboard-copy mt-2">{relationship.summary}</p>
                            <div className="dashboard-meta-row">
                              {relationship.phase_labels.slice(0, 3).map((phase) => (
                                <span key={`${relationship.id}-${phase}`} className="dashboard-pill">
                                  {phase}
                                </span>
                              ))}
                            </div>
                          </button>
                        ))
                      ) : (
                        <div className="empty-state">当前范围内还没有人工优先关系卡。</div>
                      )}
                    </div>
                  </article>

                  <article className="dashboard-card lg:col-span-3">
                    <p className="dashboard-eyebrow">关键人物</p>
                    <h3 className="dashboard-title">关键人物</h3>
                    <div className="dashboard-stat-row">
                      {dashboardRoles.map((role) => (
                        <div key={role.id} className="dashboard-stat-line">
                          <button type="button" className="text-left text-[var(--accent-deep)] hover:underline" onClick={() => openRoleDetail(role.name, 'writerArcs')}>
                            {role.name}
                          </button>
                          <strong>{role.appearances}</strong>
                        </div>
                      ))}
                    </div>
                  </article>

                  <article className="dashboard-card lg:col-span-4">
                    <p className="dashboard-eyebrow">重点场景</p>
                    <h3 className="dashboard-title">关键地点</h3>
                    <div className="dashboard-stat-row">
                      {dashboardLocations.map((location) => (
                        <div key={location.id} className="dashboard-stat-line">
                          <button
                            type="button"
                            className="text-left text-[var(--accent-deep)] hover:underline"
                            onClick={() => openLocationDetail(location.canonical_name, 'locations')}
                          >
                            {location.canonical_name}
                          </button>
                          <strong>{location.total_mentions}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="dashboard-meta-row">
                      <button type="button" className="outline-button" onClick={() => switchTab('locations')}>
                        进入地点页
                      </button>
                    </div>
                  </article>

                  <article className="dashboard-card lg:col-span-12">
                    <p className="dashboard-eyebrow">继续细看</p>
                    <h3 className="dashboard-title">继续细看</h3>
                    <div className="metric-grid mt-5">
                      {entryCards.map((entry) => (
                        <button
                          key={entry.id}
                          type="button"
                          className="dashboard-card dashboard-card--clickable text-left"
                          onClick={() => switchTab(entry.id)}
                        >
                          <p className="dashboard-eyebrow">{entry.icon} {entry.label}</p>
                          <h4 className="dashboard-title">{tabs.find((tab) => tab.id === entry.id)?.label}</h4>
                          <p className="dashboard-copy">{entry.copy}</p>
                        </button>
                      ))}
                    </div>
                  </article>
                </div>
              </div>
            </section>
            <section ref={workbenchRef} className="paper-panel">
              <div className="panel-inner">
                <div className="view-header">
                  <div>
                    <p className="section-kicker">详细分析</p>
                    <h2 className="section-title">详细分析</h2>
                    <p className="section-subtitle">这里保留原有全部视图能力，只把层级、样式和进入路径整理得更清楚。</p>
                  </div>
                  <div className="float-stat">当前标签：{tabs.find((tab) => tab.id === activeTab)?.label}</div>
                </div>

                <div className="tab-rail">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => switchTab(tab.id)}
                      className={`tab-pill ${activeTab === tab.id ? 'tab-pill--active' : ''}`}
                    >
                      <span className="tab-pill-icon">{tab.icon}</span>
                      <span>{tab.label}</span>
                    </button>
                  ))}
                </div>

                <div className="tab-panel-shell mt-6">
                  <div className="tab-panel-inner">
                    {activeTab === 'timeline' && (
                      <Timeline
                        bookConfig={bookConfig}
                        chapterIndex={chapterIndex}
                        events={timelineEvents}
                        onEventClick={(event) => openEventDetail(event.id, 'timeline')}
                      />
                    )}

                    {activeTab === 'network' && (
                      <NetworkGraph
                        allNodes={roles}
                        linkedNodes={networkNodes}
                        isolatedNodes={isolatedNodes}
                        links={roleLinks}
                        totalRoleCount={totalRoleCount}
                        linkedRoleCount={linkedRoleCount}
                        spotlightRoleName={writerInsights?.spotlight_role_name ?? '陈平安'}
                        onNodeClick={(role) => openNetworkRoleRelations(role.id)}
                        onLinkClick={handleLinkClick}
                        focusNodeId={focusNodeId}
                        onFocusNodeHandled={() => setFocusNodeId(null)}
                      />
                    )}

                    {activeTab === 'power' && (
                      <PowerChart
                        bookConfig={bookConfig}
                        data={powerDistribution}
                        onPowerClick={(power) => openRoleList({ title: `${power.power} 阵营人物`, subtitle: `共 ${power.count} 人`, roleIds: power.roles })}
                      />
                    )}

                    {activeTab === 'locations' && (
                      <LocationsView
                        locations={locations}
                        onLocationClick={(location) => openLocationDetail(location.canonical_name, 'locations')}
                      />
                    )}

                    {activeTab === 'writerArcs' && (
                      <WriterArcsView
                        seasonOverviews={seasonOverviews}
                        arcs={characterArcs}
                        curatedRelationships={curatedRelationships}
                        selectedRoleId={selectedRole?.id ?? null}
                        spotlightRoleName={writerInsights?.spotlight_role_name ?? null}
                        onRoleClick={(roleName) => openRoleDetail(roleName, 'writerArcs')}
                        onEventClick={(eventId) => openEventDetail(eventId, 'writerArcs')}
                        onLocationClick={(locationName) => openLocationDetail(locationName, 'writerArcs')}
                        onRelationClick={handleLinkClick}
                      />
                    )}

                    {activeTab === 'conflicts' && (
                      <ConflictChainsView
                        curatedRelationships={curatedRelationships}
                        chains={conflictChains}
                        spotlightRoleName={writerInsights?.spotlight_role_name ?? null}
                        onRoleClick={(roleName) => openRoleDetail(roleName, 'conflicts')}
                        onEventClick={(eventId) => openEventDetail(eventId, 'conflicts')}
                        onRelationClick={handleLinkClick}
                      />
                    )}

                    {activeTab === 'foreshadowing' && (
                      <ForeshadowingView
                        threads={foreshadowingThreads}
                        onRoleClick={(roleName) => openRoleDetail(roleName, 'foreshadowing')}
                        onEventClick={(eventId, eventRef) =>
                          openEventDetail(eventId, 'foreshadowing', {
                            fallbackEvent: insightEventToTimeline(eventRef),
                          })
                        }
                      />
                    )}
                  </div>
                </div>
              </div>
            </section>
          </section>
        </div>
      </main>

      <footer className="mt-10 bg-[var(--bg-ink)] text-[rgba(236,245,245,0.9)]">
        <div className="shell-container py-6 text-sm flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <span>{title} 可视化系统</span>
          <span className="text-[rgba(202,216,220,0.72)]">当前前端为电影感国风版本，保留原有分析功能与深链接协议。</span>
        </div>
      </footer>

      {showMobileFilters && (
        <>
          <button
            type="button"
            className="mobile-drawer-backdrop"
            onClick={() => setShowMobileFilters(false)}
            aria-label="关闭筛选台"
          />
          <div className="mobile-drawer">
            <div className="mobile-drawer-handle" />
            <div className="p-4">
              <div className="flex items-center justify-between gap-3 mb-4">
                <div>
                  <p className="section-kicker">移动端筛选</p>
                  <h2 className="section-title">筛选控制台</h2>
                </div>
                <button type="button" className="outline-button" onClick={() => setShowMobileFilters(false)}>
                  关闭
                </button>
              </div>
              <FilterControls
                bookConfig={bookConfig}
                unitRange={unitRange}
                onUnitRangeChange={(range) => {
                  const nextUnitRange = normalizeUnitRange(range);
                  setUnitRange(nextUnitRange);

                  if (syncUnitProgress) {
                    const derived = deriveProgressRangeFromUnitRange(nextUnitRange);
                    if (derived) {
                      setProgressRange(derived);
                      updateUrlContext({ unitRange: nextUnitRange, progressRange: derived }, { replace: true });
                      return;
                    }
                  }

                  updateUrlContext({ unitRange: nextUnitRange }, { replace: true });
                }}
                onUnitRangeCommit={(range) => {
                  const nextUnitRange = normalizeUnitRange(range);
                  if (syncUnitProgress) {
                    const derived = deriveProgressRangeFromUnitRange(nextUnitRange);
                    if (derived) {
                      setProgressRange(derived);
                      updateUrlContext({ unitRange: nextUnitRange, progressRange: derived }, { replace: false });
                      return;
                    }
                  }
                  updateUrlContext({ unitRange: nextUnitRange }, { replace: false });
                }}
                maxUnit={maxUnit}
                progressRange={progressRange}
                onProgressRangeChange={(range) => {
                  const nextProgressRange = normalizeProgressRange(range);
                  setProgressRange(nextProgressRange);

                  if (syncUnitProgress) {
                    const derived = deriveUnitRangeFromProgressRange(nextProgressRange);
                    if (derived) {
                      setUnitRange(derived);
                      updateUrlContext({ unitRange: derived, progressRange: nextProgressRange }, { replace: true });
                      return;
                    }
                  }

                  updateUrlContext({ progressRange: nextProgressRange }, { replace: true });
                }}
                onProgressRangeCommit={(range) => {
                  const nextProgressRange = normalizeProgressRange(range);
                  if (syncUnitProgress) {
                    const derived = deriveUnitRangeFromProgressRange(nextProgressRange);
                    if (derived) {
                      setUnitRange(derived);
                      updateUrlContext({ unitRange: derived, progressRange: nextProgressRange }, { replace: false });
                      return;
                    }
                  }
                  updateUrlContext({ progressRange: nextProgressRange }, { replace: false });
                }}
                syncUnitProgress={syncUnitProgress}
                syncAvailable={Boolean(unitProgressIndex)}
                onSyncUnitProgressChange={(enabled) => {
                  setSyncUnitProgress(enabled);
                  if (!enabled) return;
                  const derived = deriveProgressRangeFromUnitRange(unitRange);
                  if (derived) {
                    setProgressRange(derived);
                    updateUrlContext({ progressRange: derived }, { replace: true });
                  }
                }}
              />
            </div>
          </div>
        </>
      )}

      <EventDetail
        event={selectedEvent}
        onClose={closeActiveModal}
        onBack={modalBackHandler}
        onEntityClick={(entityName) => handleFocusNode(entityName, { pushCurrent: true })}
        onLocationClick={(locationName) => openLocationDetail(locationName, activeTab, { pushCurrent: true })}
        chapterIndex={chapterIndex}
        kb={kb}
        availableRoleIds={availableRoleIds}
      />

      {activeTab === 'network' ? (
        <NetworkRoleRelationsDetail
          role={selectedRole}
          relationGroups={selectedRoleRelationGroups}
          onClose={closeActiveModal}
          onBack={modalBackHandler}
          onRelationClick={(sourceId, targetId) => {
            handleLinkClick(sourceId, targetId, { pushCurrent: true });
          }}
          onEntityClick={(entityName) => {
            handleFocusNode(entityName, { pushCurrent: true });
          }}
          kb={kb}
        />
      ) : (
        <RoleDetail
          role={selectedRole}
          onClose={closeActiveModal}
          onBack={modalBackHandler}
          onEntityClick={(entityName) => handleFocusNode(entityName, { pushCurrent: true })}
          onEventClick={(event) => openEventDetail(event.id, activeTab, { pushCurrent: true })}
          chapterIndex={chapterIndex}
          relatedRoleNames={selectedRoleRelatedNames}
          relatedEvents={
            selectedRole
              ? timelineEvents.filter(
                  (event) => event.participants.some((name) => name === selectedRole.name || selectedRole.aliases.includes(name))
                )
              : []
          }
          kb={kb}
          availableRoleIds={availableRoleIds}
        />
      )}

      {selectedLocation && (
        <LocationDetail
          location={selectedLocation}
          relatedEvents={timelineEvents.filter((event) => event.location === selectedLocation.canonical_name)}
          relatedRoles={selectedLocation.associated_entities || []}
          relatedActions={[]}
          onClose={closeActiveModal}
          onBack={modalBackHandler}
          onEntityClick={(entityName) => handleFocusNode(entityName, { pushCurrent: true })}
          onEventClick={(event) => openEventDetail(event.id, activeTab, { pushCurrent: true })}
          chapterIndex={chapterIndex}
          kb={kb}
          availableRoleIds={availableRoleIds}
        />
      )}

      {selectedRelationPair && (
        <RelationDetail
          relations={selectedRelationPair.relations}
          sourceName={selectedRelationPair.sourceName}
          targetName={selectedRelationPair.targetName}
          onClose={closeActiveModal}
          onBack={modalBackHandler}
          onEntityClick={(entityName) => handleFocusNode(entityName, { pushCurrent: true })}
          onEventClick={(event) => openEventDetail(event.id, activeTab, { pushCurrent: true })}
          relatedEvents={timelineEvents.filter((event) => {
            const sourceRole = kb?.roles?.[selectedRelationPair.sourceId];
            const targetRole = kb?.roles?.[selectedRelationPair.targetId];
            const sourceNames = new Set<string>([selectedRelationPair.sourceName, ...(sourceRole?.all_names || [])]);
            const targetNames = new Set<string>([selectedRelationPair.targetName, ...(targetRole?.all_names || [])]);
            return event.participants.some((name) => sourceNames.has(name)) && event.participants.some((name) => targetNames.has(name));
          })}
          chapterIndex={chapterIndex}
          kb={kb}
          availableRoleIds={availableRoleIds}
        />
      )}

      {roleListConfig && (
        <RoleListModal
          title={roleListConfig.title}
          subtitle={roleListConfig.subtitle}
          roles={roleListRoles}
          onClose={closeActiveModal}
          onRoleClick={(roleName) => openRoleDetail(roleName, activeTab, { pushCurrent: true })}
        />
      )}
    </div>
  );
}

export default App;
