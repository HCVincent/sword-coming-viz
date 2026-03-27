import { useEffect, useMemo, useState } from 'react';
import type { UnifiedKnowledgeBase } from '../types/unified';
import {
  calculateUnifiedPowerDistribution,
  unifiedEventsToTimeline,
  unifiedLocationsToList,
  unifiedNetworkGraphData,
} from '../utils/unifiedDataProcessing';

export function useUnifiedKnowledgeBase() {
  const [kb, setKb] = useState<UnifiedKnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/unified_knowledge.json`);

        if (!response.ok) {
          throw new Error(`读取统一知识库失败：${response.status}`);
        }

        const data = (await response.json()) as UnifiedKnowledgeBase;
        setKb(data);
      } catch (err) {
        console.error('Error loading unified knowledge base:', err);
        setError(err instanceof Error ? err.message : '读取知识库时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  return { kb, loading, error };
}

export function useUnifiedVisualizationData(
  kb: UnifiedKnowledgeBase | null,
  unitRange?: [number, number],
  progressRange?: [number | null, number | null]
) {
  const { allNodes, linkedNodes, isolatedNodes, links, totalRoleCount, linkedRoleCount } = useMemo(() => {
    if (!kb) {
      return {
        allNodes: [],
        linkedNodes: [],
        isolatedNodes: [],
        links: [],
        totalRoleCount: 0,
        linkedRoleCount: 0,
      };
    }
    return unifiedNetworkGraphData(kb, unitRange, progressRange ?? [null, null]);
  }, [kb, unitRange, progressRange]);

  const timelineEvents = useMemo(() => {
    if (!kb) return [];
    return unifiedEventsToTimeline(kb, unitRange, progressRange ?? [null, null]);
  }, [kb, unitRange, progressRange]);

  const locations = useMemo(() => {
    if (!kb) return [];
    return unifiedLocationsToList(kb, unitRange, progressRange ?? [null, null]);
  }, [kb, unitRange, progressRange]);

  const powerDistribution = useMemo(() => {
    if (!kb) return [];
    return calculateUnifiedPowerDistribution(kb, unitRange, progressRange ?? [null, null]);
  }, [kb, unitRange, progressRange]);

  return {
    nodes: allNodes,
    networkNodes: linkedNodes,
    isolatedNodes,
    links,
    totalRoleCount,
    linkedRoleCount,
    timelineEvents,
    locations,
    powerDistribution,
  };
}

export function useUnifiedSearch(
  kb: UnifiedKnowledgeBase | null,
  query: string,
  limit: number = 20
) {
  const results = useMemo(() => {
    if (!kb || !query.trim()) return [];

    const queryLower = query.toLowerCase();
    const results: Array<{
      type: 'role' | 'location' | 'event';
      id: string;
      name: string;
      description: string;
      score: number;
    }> = [];

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
  }, [kb, query, limit]);

  return results;
}
