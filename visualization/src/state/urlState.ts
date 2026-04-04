export type TabType =
  | 'timeline'
  | 'narrativeUnits'
  | 'network'
  | 'power'
  | 'locations'
  | 'map'
  | 'writerArcs'
  | 'conflicts'
  | 'foreshadowing';

export type SelectionType = 'event' | 'role' | 'location' | 'relationPair';

export interface UrlGlobalContext {
  tab: TabType;
  unitRange: [number, number];
  progressRange: [number | null, number | null];
  selection?:
  | { type: 'event'; id: string }
  | { type: 'role'; id: string }
  | { type: 'location'; id: string }
  | { type: 'relationPair'; sourceId: string; targetId: string };
  focusRoleId?: string;
  narrativeUnitId?: string;
}

const DEFAULT_CONTEXT: UrlGlobalContext = {
  tab: 'narrativeUnits',
  unitRange: [1, 1],
  progressRange: [null, null],
};

function toInt(value: string | null): number | null {
  if (value == null || value.trim() === '') return null;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) ? n : null;
}

function clampUnit(value: number, maxUnit: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.min(maxUnit, Math.max(1, value));
}

function parseTab(value: string | null): TabType {
  if (
    value === 'timeline' ||
    value === 'narrativeUnits' ||
    value === 'network' ||
    value === 'power' ||
    value === 'locations' ||
    value === 'map' ||
    value === 'writerArcs' ||
    value === 'conflicts' ||
    value === 'foreshadowing'
  ) {
    return value;
  }
  return DEFAULT_CONTEXT.tab;
}

export function parseUrlGlobalContext(params: URLSearchParams, maxUnit: number): UrlGlobalContext {
  const tab = parseTab(params.get('tab'));

  const us = toInt(params.get('us'));
  const ue = toInt(params.get('ue'));
  const startUnit = clampUnit(us ?? DEFAULT_CONTEXT.unitRange[0], maxUnit);
  const endUnit = clampUnit(ue ?? maxUnit, maxUnit);
  const unitRange: [number, number] = [Math.min(startUnit, endUnit), Math.max(startUnit, endUnit)];

  const ps = toInt(params.get('ps'));
  const pe = toInt(params.get('pe'));
  const progressRange: [number | null, number | null] = [ps, pe];

  const selType = params.get('selType') as SelectionType | null;
  const selId = params.get('selId');

  let selection: UrlGlobalContext['selection'] | undefined;
  if (selType === 'event' && selId) selection = { type: 'event', id: selId };
  if (selType === 'role' && selId) selection = { type: 'role', id: selId };
  if (selType === 'location' && selId) selection = { type: 'location', id: selId };
  if (selType === 'relationPair' && selId && selId.includes('|')) {
    const [sourceId, targetId] = selId.split('|', 2);
    if (sourceId && targetId) selection = { type: 'relationPair', sourceId, targetId };
  }

  const focusRoleId = params.get('focus') || undefined;
  const narrativeUnitId = params.get('nuId') || undefined;

  return {
    tab,
    unitRange,
    progressRange,
    selection,
    focusRoleId,
    narrativeUnitId,
  };
}

export function writeUrlGlobalContext(
  params: URLSearchParams,
  ctx: Pick<UrlGlobalContext, 'tab' | 'unitRange' | 'progressRange' | 'selection' | 'focusRoleId' | 'narrativeUnitId'>
) {
  const next = new URLSearchParams(params);

  next.set('tab', ctx.tab);
  next.set('us', String(ctx.unitRange[0]));
  next.set('ue', String(ctx.unitRange[1]));

  const [ps, pe] = ctx.progressRange;
  if (ps == null) next.delete('ps');
  else next.set('ps', String(ps));

  if (pe == null) next.delete('pe');
  else next.set('pe', String(pe));

  if (ctx.focusRoleId) next.set('focus', ctx.focusRoleId);
  else next.delete('focus');

  if (!ctx.selection) {
    next.delete('selType');
    next.delete('selId');
  } else {
    next.set('selType', ctx.selection.type);
    if (ctx.selection.type === 'relationPair') {
      next.set('selId', `${ctx.selection.sourceId}|${ctx.selection.targetId}`);
    } else {
      next.set('selId', ctx.selection.id);
    }
  }

  if (ctx.narrativeUnitId) next.set('nuId', ctx.narrativeUnitId);
  else next.delete('nuId');

  return next;
}
