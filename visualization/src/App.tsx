import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useBookConfig, useUnitProgressIndex } from './hooks/useBookArtifacts';
import { useUnifiedKnowledgeBase, useUnifiedVisualizationData } from './hooks/useUnifiedData';
import { useFilteredWriterInsights, useWriterInsights } from './hooks/useWriterInsights';
import {
  ConflictChainsView,
  EventDetail,
  FilterControls,
  ForeshadowingView,
  LocationDetail,
  LocationsView,
  MapView,
  NetworkRoleRelationsDetail,
  NetworkGraph,
  PowerChart,
  RelationDetail,
  RoleDetail,
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

function toRoleNode(role: UnifiedKnowledgeBase['roles'][string]): RoleNodeUnified {
  return {
    id: role.id,
    name: role.canonical_name,
    power: role.primary_power,
    description: role.description,
    appearances: role.total_mentions,
    units: role.units_appeared && role.units_appeared.length > 0 ? role.units_appeared : role.juans_appeared,
    aliases: Array.from(role.all_names || []).filter((name) => name !== role.canonical_name),
    relatedEntities: Array.from(role.related_entities || []),
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
  const { unitProgressIndex } = useUnitProgressIndex();

  const [searchParams, setSearchParams] = useSearchParams();
  const maxUnit = unitProgressIndex?.total_units ?? 328;

  const [unitRange, setUnitRange] = useState<[number, number]>([1, Math.min(3, maxUnit)]);
  const [progressRange, setProgressRange] = useState<[number | null, number | null]>([null, null]);
  const [activeTab, setActiveTab] = useState<TabType>('timeline');
  const [syncUnitProgress, setSyncUnitProgress] = useState(true);

  const [selectedEvent, setSelectedEvent] = useState<TimelineEventUnified | null>(null);
  const [selectedRole, setSelectedRole] = useState<RoleNodeUnified | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<UnifiedLocation | null>(null);
  const [selectedRelationPair, setSelectedRelationPair] = useState<SelectedRelationPair | null>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  const {
    nodes: roles,
    networkNodes,
    isolatedNodes,
    links: roleLinks,
    totalRoleCount,
    linkedRoleCount,
    timelineEvents,
    locations,
    powerDistribution,
  } = useUnifiedVisualizationData(kb, unitRange, progressRange);
  const { seasonOverviews, characterArcs, curatedRelationships, conflictChains, foreshadowingThreads } = useFilteredWriterInsights(
    writerInsights,
    unitRange,
    progressRange
  );

  const rolesRef = useRef<RoleNodeUnified[]>([]);
  const roleLinksRef = useRef<RoleLinkUnified[]>([]);

  useEffect(() => {
    rolesRef.current = roles;
  }, [roles]);

  useEffect(() => {
    roleLinksRef.current = roleLinks;
  }, [roleLinks]);

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
      if (start === null || end === null) return [start, end] as [number | null, number | null];
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
    setActiveTab(ctx.tab);
    setUnitRange((prev) => (prev[0] === ctx.unitRange[0] && prev[1] === ctx.unitRange[1] ? prev : ctx.unitRange));
    setProgressRange((prev) =>
      prev[0] === ctx.progressRange[0] && prev[1] === ctx.progressRange[1] ? prev : ctx.progressRange
    );
    setFocusNodeId(ctx.focusRoleId ?? null);

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
      setSelectedEvent(event ? toTimelineEvent(event) : null);
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
  }, [kb, maxUnit, searchParams]);

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

  const mapFocusLocationId = useMemo(() => searchParams.get('mapLoc') ?? null, [searchParams]);

  const resolveTimelineEventById = useCallback(
    (eventId: string): TimelineEventUnified | null => {
      const existing = timelineEvents.find((event) => event.id === eventId);
      if (existing) return existing;
      const event = kb?.events?.[eventId];
      return event ? toTimelineEvent(event) : null;
    },
    [kb, timelineEvents]
  );

  const openRoleDetail = useCallback(
    (roleName: string, tab: TabType = activeTab) => {
      const roleId = resolveRoleId(kb, roleName);
      if (!roleId || !kb?.roles?.[roleId]) return;
      const role = toRoleNode(kb.roles[roleId]);
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
    [activeTab, focusNodeId, kb, progressRange, searchParams, setSearchParams, unitRange]
  );

  const openLocationDetail = useCallback(
    (locationName: string, tab: TabType = activeTab) => {
      const location = locations.find(
        (item) => item.canonical_name === locationName || item.all_names?.includes(locationName)
      );
      if (!location) return;
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
    [activeTab, focusNodeId, locations, progressRange, searchParams, setSearchParams, unitRange]
  );

  const openEventDetail = useCallback(
    (eventId: string, tab: TabType = activeTab) => {
      const event = resolveTimelineEventById(eventId);
      if (!event) return;
      setSelectedEvent(event);
      const next = writeUrlGlobalContext(searchParams, {
        tab,
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: { type: 'event', id: event.id },
      });
      setSearchParams(next, { replace: false });
    },
    [activeTab, focusNodeId, progressRange, resolveTimelineEventById, searchParams, setSearchParams, unitRange]
  );

  const handleFocusNode = useCallback(
    (entityName: string) => {
      const roleId = resolveRoleId(kb, entityName);
      if (!roleId) return;
      setActiveTab('network');
      setFocusNodeId(roleId);
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'network',
        unitRange,
        progressRange,
        focusRoleId: roleId,
        selection: { type: 'role', id: roleId },
      });
      setSearchParams(next, { replace: false });
    },
    [kb, progressRange, searchParams, setSearchParams, unitRange]
  );

  const handleNavigateToMap = useCallback(
    (focusLocationId?: string) => {
      setSelectedEvent(null);
      setSelectedRole(null);
      setSelectedLocation(null);
      setSelectedRelationPair(null);
      setActiveTab('map');
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'map',
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: undefined,
      });
      if (focusLocationId) next.set('mapLoc', focusLocationId);
      else next.delete('mapLoc');
      setSearchParams(next, { replace: false });
    },
    [focusNodeId, progressRange, searchParams, setSearchParams, unitRange]
  );

  const handleLinkClick = useCallback(
    (sourceId: string, targetId: string) => {
      const relations = roleLinks.filter((link) => {
        const linkSourceId = typeof link.source === 'object' ? (link.source as never as { id: string }).id : link.source;
        const linkTargetId = typeof link.target === 'object' ? (link.target as never as { id: string }).id : link.target;
        return (
          (linkSourceId === sourceId && linkTargetId === targetId) ||
          (linkSourceId === targetId && linkTargetId === sourceId)
        );
      });

      const sourceNode = roles.find((node) => node.id === sourceId);
      const targetNode = roles.find((node) => node.id === targetId);
      setSelectedEvent(null);
      setSelectedRole(null);
      setSelectedLocation(null);
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
    },
    [focusNodeId, progressRange, roleLinks, roles, searchParams, setSearchParams, unitRange]
  );

  const openNetworkRoleRelations = useCallback(
    (roleId: string) => {
      if (!kb?.roles?.[roleId]) return;
      const role = toRoleNode(kb.roles[roleId]);
      setSelectedEvent(null);
      setSelectedRole(role);
      setSelectedLocation(null);
      setSelectedRelationPair(null);
      const next = writeUrlGlobalContext(searchParams, {
        tab: 'network',
        unitRange,
        progressRange,
        focusRoleId: focusNodeId ?? undefined,
        selection: { type: 'role', id: role.id },
      });
      setSearchParams(next, { replace: false });
    },
    [focusNodeId, kb, progressRange, searchParams, setSearchParams, unitRange]
  );

  const availableRoleIds = useMemo(() => new Set(roles.map((role) => role.id)), [roles]);

  const selectedRoleRelationGroups = useMemo<RoleRelationGroup[]>(() => {
    if (!selectedRole) return [];

    const groups = new Map<string, RoleRelationGroup>();
    for (const link of roleLinks) {
      const sourceId = typeof link.source === 'object' ? (link.source as never as { id: string }).id : link.source;
      const targetId = typeof link.target === 'object' ? (link.target as never as { id: string }).id : link.target;
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

  const unitLabel = bookConfig?.unit_label ?? kb?.unit_label ?? '章节';
  const title = bookConfig?.title ?? '小说';
  const subtitle = bookConfig?.subtitle ?? '内容可视化';

  const loading = kbLoading || writerLoading;
  const error = kbError ?? writerError;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#faf8f5]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-[#8b4513] border-t-transparent mx-auto mb-4" />
          <p className="text-[#2c1810]">正在加载统一知识库...</p>
          <p className="text-sm text-gray-500 mt-2">正在准备人物、事件、地点与编剧分析数据</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#faf8f5]">
        <div className="text-center text-red-600">
          <p className="text-xl mb-2">加载失败</p>
          <p className="text-sm">{error}</p>
          <p className="text-sm mt-4 text-gray-500">
            请确认数据文件已同步到 visualization/public/data
          </p>
        </div>
      </div>
    );
  }

  const tabs: { id: TabType; label: string; icon: string }[] = [
    { id: 'timeline', label: '时间轴', icon: '📚' },
    { id: 'network', label: '关系网络', icon: '🔗' },
    { id: 'power', label: '阵营分布', icon: '📊' },
    { id: 'locations', label: '地点', icon: '📍' },
    { id: 'map', label: '地点关系', icon: '🧭' },
    { id: 'writerArcs', label: '角色弧光', icon: '🎭' },
    { id: 'conflicts', label: '冲突链', icon: '⚔️' },
    { id: 'foreshadowing', label: '伏笔回收', icon: '🧵' },
  ];

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <header className="bg-gradient-to-r from-[#8b4513] to-[#5d2e0c] text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div>
            <h1 className="text-3xl font-bold">{title}可视化系统</h1>
            <p className="text-[#d4a574] mt-1">{subtitle}</p>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-1">
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

            <div className="bg-white rounded-lg shadow-md p-4 mt-4">
              <h3 className="text-lg font-bold text-[#2c1810] mb-3">数据统计</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">人物总数：</span>
                  <span className="font-semibold">{totalRoleCount}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">关系网人物：</span>
                  <span className="font-semibold">{linkedRoleCount}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">孤立人物：</span>
                  <span className="font-semibold">{Math.max(totalRoleCount - linkedRoleCount, 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">事件数量：</span>
                  <span className="font-semibold">{timelineEvents.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">地点数量：</span>
                  <span className="font-semibold">{locations.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">关系数量：</span>
                  <span className="font-semibold">{roleLinks.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">分季总览：</span>
                  <span className="font-semibold">{seasonOverviews.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">角色弧光：</span>
                  <span className="font-semibold">{characterArcs.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">人工校订主线：</span>
                  <span className="font-semibold">{curatedRelationships.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">冲突链：</span>
                  <span className="font-semibold">{conflictChains.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">伏笔线：</span>
                  <span className="font-semibold">{foreshadowingThreads.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">{unitLabel}范围：</span>
                  <span className="font-semibold">
                    {unitRange[0]} - {unitRange[1]}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-3">
            <div className="bg-white rounded-lg shadow-md mb-4">
              <div className="flex flex-wrap border-b border-[#d4c5b5]">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => {
                      setActiveTab(tab.id);
                      const next = writeUrlGlobalContext(searchParams, {
                        tab: tab.id,
                        unitRange,
                        progressRange,
                        focusRoleId: focusNodeId ?? undefined,
                        selection: undefined,
                      });
                      next.delete('mapLoc');
                      setSearchParams(next, { replace: false });
                    }}
                    className={`px-4 py-3 text-sm font-medium transition-colors min-w-[120px] ${
                      activeTab === tab.id
                        ? 'text-[#8b4513] border-b-2 border-[#8b4513] bg-[#faf8f5]'
                        : 'text-gray-500 hover:text-[#8b4513] hover:bg-[#faf8f5]'
                    }`}
                  >
                    <span className="mr-2">{tab.icon}</span>
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              {activeTab === 'timeline' && (
                <Timeline bookConfig={bookConfig} events={timelineEvents} onEventClick={(event) => openEventDetail(event.id, 'timeline')} />
              )}

              {activeTab === 'network' && (
                <NetworkGraph
                  allNodes={roles}
                  linkedNodes={networkNodes}
                  isolatedNodes={isolatedNodes}
                  links={roleLinks}
                  totalRoleCount={totalRoleCount}
                  linkedRoleCount={linkedRoleCount}
                  onNodeClick={(role) => openNetworkRoleRelations(role.id)}
                  onLinkClick={handleLinkClick}
                  focusNodeId={focusNodeId}
                  onFocusNodeHandled={() => setFocusNodeId(null)}
                />
              )}

              {activeTab === 'power' && <PowerChart bookConfig={bookConfig} data={powerDistribution} />}

              {activeTab === 'locations' && (
                <LocationsView
                  locations={locations}
                  onLocationClick={(location) => openLocationDetail(location.canonical_name, 'locations')}
                  onNavigateToMap={(location) => handleNavigateToMap(location.id)}
                />
              )}

              {activeTab === 'map' && (
                <MapView
                  bookConfig={bookConfig}
                  locations={locations}
                  eventsInRange={timelineEvents}
                  selectedRole={selectedRole}
                  selectedEvent={selectedEvent}
                  focusLocationId={mapFocusLocationId}
                  onLocationClick={(location) => {
                    setSelectedLocation(location);
                    const next = writeUrlGlobalContext(searchParams, {
                      tab: 'map',
                      unitRange,
                      progressRange,
                      focusRoleId: focusNodeId ?? undefined,
                      selection: { type: 'location', id: location.id },
                    });
                    next.set('mapLoc', location.id);
                    setSearchParams(next, { replace: false });
                  }}
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
                  onEventClick={(eventId) => openEventDetail(eventId, 'foreshadowing')}
                />
              )}
            </div>
          </div>
        </div>
      </main>

      <footer className="bg-[#2c1810] text-[#d4a574] py-4 mt-8">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm">{title}内容可视化系统 © 2026</div>
      </footer>

      <EventDetail
        event={selectedEvent}
        onClose={() => {
          setSelectedEvent(null);
          clearSelectionFromUrl(activeTab);
        }}
        onEntityClick={handleFocusNode}
        onLocationClick={(locationName) => openLocationDetail(locationName, activeTab)}
        kb={kb}
        availableRoleIds={availableRoleIds}
      />

      {activeTab === 'network' ? (
        <NetworkRoleRelationsDetail
          role={selectedRole}
          relationGroups={selectedRoleRelationGroups}
          onClose={() => {
            setSelectedRole(null);
            clearSelectionFromUrl(activeTab);
          }}
          onRelationClick={(sourceId, targetId) => {
            setSelectedRole(null);
            handleLinkClick(sourceId, targetId);
          }}
          onEntityClick={(entityName) => {
            setSelectedRole(null);
            handleFocusNode(entityName);
          }}
          kb={kb}
        />
      ) : (
        <RoleDetail
          role={selectedRole}
          onClose={() => {
            setSelectedRole(null);
            clearSelectionFromUrl(activeTab);
          }}
          onEntityClick={handleFocusNode}
          onEventClick={(event) => openEventDetail(event.id, activeTab)}
          relatedEvents={
            selectedRole
              ? timelineEvents.filter(
                  (event) =>
                    event.participants.some((name) => name === selectedRole.name || selectedRole.aliases.includes(name))
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
          onClose={() => {
            setSelectedLocation(null);
            clearSelectionFromUrl(activeTab);
          }}
          onEntityClick={handleFocusNode}
          onNavigateToMap={() => handleNavigateToMap(selectedLocation.id)}
          kb={kb}
          availableRoleIds={availableRoleIds}
        />
      )}

      {selectedRelationPair && (
        <RelationDetail
          relations={selectedRelationPair.relations}
          sourceName={selectedRelationPair.sourceName}
          targetName={selectedRelationPair.targetName}
          onClose={() => {
            setSelectedRelationPair(null);
            clearSelectionFromUrl(activeTab);
          }}
          onEntityClick={handleFocusNode}
          onEventClick={(event) => openEventDetail(event.id, activeTab)}
          relatedEvents={timelineEvents.filter((event) => {
            const sourceRole = kb?.roles?.[selectedRelationPair.sourceId];
            const targetRole = kb?.roles?.[selectedRelationPair.targetId];
            const sourceNames = new Set<string>([
              selectedRelationPair.sourceName,
              ...(sourceRole?.all_names || []),
            ]);
            const targetNames = new Set<string>([
              selectedRelationPair.targetName,
              ...(targetRole?.all_names || []),
            ]);
            return event.participants.some((name) => sourceNames.has(name)) && event.participants.some((name) => targetNames.has(name));
          })}
          kb={kb}
          availableRoleIds={availableRoleIds}
        />
      )}
    </div>
  );
}

export default App;
