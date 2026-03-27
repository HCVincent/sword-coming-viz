import { useEffect, useMemo, useState } from 'react';
import type {
  WriterCharacterArc,
  WriterCuratedRelationship,
  WriterConflictChain,
  WriterForeshadowingThread,
  WriterInsightsPayload,
  WriterSeasonOverview,
} from '../types/writerInsights';

function rangeOverlaps(
  currentRange: [number | null | undefined, number | null | undefined],
  filterRange: [number | null, number | null]
) {
  const [currentStart, currentEnd] = currentRange;
  const [filterStart, filterEnd] = filterRange;
  if (filterStart === null && filterEnd === null) return true;
  if (currentStart == null && currentEnd == null) return false;

  const effectiveCurrentStart = currentStart ?? currentEnd ?? null;
  const effectiveCurrentEnd = currentEnd ?? currentStart ?? null;
  if (effectiveCurrentStart == null || effectiveCurrentEnd == null) return false;

  const normalizedCurrentStart = Math.min(effectiveCurrentStart, effectiveCurrentEnd);
  const normalizedCurrentEnd = Math.max(effectiveCurrentStart, effectiveCurrentEnd);
  const normalizedFilterStart = filterStart ?? -Infinity;
  const normalizedFilterEnd = filterEnd ?? Infinity;

  return normalizedCurrentEnd >= normalizedFilterStart && normalizedCurrentStart <= normalizedFilterEnd;
}

function eventInRange(
  event:
    | { unit_index: number | null; progress_start: number | null; progress_end?: number | null }
    | { unit_index?: number | null; progress_start?: number | null; progress_end?: number | null },
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
) {
  const unitHit =
    !unitRange ||
    (event.unit_index != null && event.unit_index >= unitRange[0] && event.unit_index <= unitRange[1]);
  const progressHit = rangeOverlaps(
    [event.progress_start ?? null, event.progress_end ?? event.progress_start ?? null],
    progressRange
  );
  return unitHit && progressHit;
}

function arcOverlapsRange(
  arc: WriterCharacterArc,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
) {
  const unitHit =
    !unitRange ||
    rangeOverlaps(
      [arc.unit_span[0], arc.unit_span[1]],
      [unitRange[0], unitRange[1]]
    );
  const progressHit = rangeOverlaps(arc.progress_span, progressRange);
  return unitHit && progressHit;
}

function chainOverlapsRange(
  chain: WriterConflictChain | WriterForeshadowingThread | WriterCuratedRelationship | WriterSeasonOverview,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
) {
  const unitSpan = 'unit_span' in chain ? chain.unit_span : chain.unit_range;
  const progressSpan = 'progress_span' in chain ? chain.progress_span : chain.progress_range;
  const unitHit =
    !unitRange ||
    rangeOverlaps(
      [unitSpan[0], unitSpan[1]],
      [unitRange[0], unitRange[1]]
    );
  const progressHit = rangeOverlaps(progressSpan, progressRange);
  return unitHit && progressHit;
}

export function useWriterInsights() {
  const [writerInsights, setWriterInsights] = useState<WriterInsightsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/writer_insights.json`);
        if (!response.ok) {
          throw new Error(`读取编剧视图数据失败：${response.status}`);
        }
        const data = (await response.json()) as WriterInsightsPayload;
        setWriterInsights(data);
      } catch (err) {
        console.error('Error loading writer insights:', err);
        setError(err instanceof Error ? err.message : '读取编剧视图数据时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { writerInsights, loading, error };
}

export function useFilteredWriterInsights(
  payload: WriterInsightsPayload | null,
  unitRange?: [number, number],
  progressRange: [number | null, number | null] = [null, null]
) {
  const spotlightRoleName = payload?.spotlight_role_name?.trim() || null;

  const characterArcs = useMemo(() => {
    if (!payload) return [];
    return payload.character_arcs
      .filter((arc) => arcOverlapsRange(arc, unitRange, progressRange))
      .map((arc) => ({
        ...arc,
        key_events: arc.key_events.filter((event) => eventInRange(event, unitRange, progressRange)),
        relationship_phases: arc.relationship_phases.filter((phase) =>
          eventInRange(
            { unit_index: phase.unit_index, progress_start: phase.progress_start, progress_end: phase.progress_start },
            unitRange,
            progressRange
          )
        ),
      }))
      .filter(
        (arc) =>
          arc.key_events.length > 0 ||
          arc.relationship_phases.length > 0 ||
          arc.spotlight ||
          (spotlightRoleName ? arc.role_name === spotlightRoleName : false)
      );
  }, [payload, progressRange, spotlightRoleName, unitRange]);

  const seasonOverviews = useMemo(() => {
    if (!payload) return [];
    return payload.season_overviews.filter((overview) => chainOverlapsRange(overview, unitRange, progressRange));
  }, [payload, progressRange, unitRange]);

  const curatedRelationships = useMemo(() => {
    if (!payload) return [];
    return payload.curated_relationships
      .filter((relationship) => chainOverlapsRange(relationship, unitRange, progressRange))
      .map((relationship) => ({
        ...relationship,
        manual_beats: relationship.manual_beats.filter((beat) =>
          eventInRange(
            { unit_index: beat.unit_index, progress_start: beat.progress_start, progress_end: beat.progress_start },
            unitRange,
            progressRange
          )
        ),
        key_events: relationship.key_events.filter((event) => eventInRange(event, unitRange, progressRange)),
      }))
      .filter(
        (relationship) =>
          relationship.key_events.length > 0 ||
          relationship.phase_labels.length > 0 ||
          relationship.manual_beats.length > 0
      );
  }, [payload, progressRange, unitRange]);

  const conflictChains = useMemo(() => {
    if (!payload) return [];
    return payload.conflict_chains
      .filter((chain) => chainOverlapsRange(chain, unitRange, progressRange))
      .map((chain) => ({
        ...chain,
        beats: chain.beats.filter((beat) =>
          eventInRange(
            { unit_index: beat.unit_index, progress_start: beat.progress_start, progress_end: beat.progress_start },
            unitRange,
            progressRange
          )
        ),
      }))
      .filter((chain) => chain.beats.length > 0);
  }, [payload, progressRange, unitRange]);

  const foreshadowingThreads = useMemo(() => {
    if (!payload) return [];
    return payload.foreshadowing_threads
      .filter((thread) => chainOverlapsRange(thread, unitRange, progressRange))
      .map((thread) => ({
        ...thread,
        clue_events: thread.clue_events.filter((event) => eventInRange(event, unitRange, progressRange)),
        payoff_events: thread.payoff_events.filter((event) => eventInRange(event, unitRange, progressRange)),
      }))
      .filter((thread) => thread.clue_events.length > 0 || thread.payoff_events.length > 0);
  }, [payload, progressRange, unitRange]);

  return {
    seasonOverviews,
    characterArcs,
    curatedRelationships,
    conflictChains,
    foreshadowingThreads,
  };
}
