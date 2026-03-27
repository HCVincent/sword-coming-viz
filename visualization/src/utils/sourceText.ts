import type { ChapterIndex, ChapterIndexUnit } from '../types/pipelineArtifacts';

export interface ChapterJumpTarget {
  href: string;
  label: string;
  title: string;
  chapterTitle: string;
  unitIndex: number;
  relativePath: string;
  anchor?: string;
}

function resolveUnit(index: ChapterIndex | null, unitIndex: number | null | undefined): ChapterIndexUnit | null {
  if (!index || unitIndex == null) return null;
  return index.units.find((unit) => unit.unit_index === unitIndex) ?? null;
}

function resolveAnchor(unit: ChapterIndexUnit, progressIndex: number | null | undefined): string | undefined {
  if (progressIndex == null) return undefined;
  const exact = unit.segments.find((segment) => segment.progress_index === progressIndex);
  if (exact) return exact.anchor;

  const nearest = unit.segments.find((segment) => segment.progress_index >= progressIndex) ?? unit.segments[unit.segments.length - 1];
  return nearest?.anchor;
}

function resolveCurrentAnalysisHref() {
  if (typeof window === 'undefined') return undefined;
  if (window.location.pathname.startsWith('/reader/')) return undefined;
  return `${window.location.pathname}${window.location.search}`;
}

export function buildChapterHref(unitIndex: number, anchor?: string, fromHref?: string) {
  const params = new URLSearchParams();
  if (anchor) {
    params.set('anchor', anchor);
  }
  const sourceHref = fromHref ?? resolveCurrentAnalysisHref();
  if (sourceHref) {
    params.set('from', sourceHref);
  }
  const query = params.toString();
  return `/reader/${unitIndex}${query ? `?${query}` : ''}`;
}

export function getPrimaryJumpTarget(
  index: ChapterIndex | null,
  opts: { unitIndex?: number | null; progressIndex?: number | null; fallbackLabel?: string }
): ChapterJumpTarget | null {
  const unit = resolveUnit(index, opts.unitIndex);
  if (!unit) return null;
  const anchor = resolveAnchor(unit, opts.progressIndex);
  return {
    href: buildChapterHref(unit.unit_index, anchor),
    label: opts.fallbackLabel ?? `查看原文：${unit.chapter_title}`,
    title: unit.title,
    chapterTitle: unit.chapter_title,
    unitIndex: unit.unit_index,
    relativePath: unit.relative_path,
    anchor,
  };
}

export function getJumpTargetsByUnits(
  index: ChapterIndex | null,
  unitIndexes: number[] | undefined,
  limit = 8
): ChapterJumpTarget[] {
  if (!index || !unitIndexes?.length) return [];
  const seen = new Set<number>();
  const targets: ChapterJumpTarget[] = [];
  for (const unitIndex of unitIndexes) {
    if (seen.has(unitIndex)) continue;
    seen.add(unitIndex);
    const unit = resolveUnit(index, unitIndex);
    if (!unit) continue;
    targets.push({
      href: buildChapterHref(unit.unit_index),
      label: `章节 ${unit.unit_index}`,
      title: unit.title,
      chapterTitle: unit.chapter_title,
      unitIndex: unit.unit_index,
      relativePath: unit.relative_path,
    });
    if (targets.length >= limit) break;
  }
  return targets;
}
