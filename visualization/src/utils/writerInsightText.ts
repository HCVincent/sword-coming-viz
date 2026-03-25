const RELATION_KIND_LABELS: Record<string, string> = {
  mirror: '镜像',
  emotion: '情感',
  mentor: '引路',
  friend: '同伴',
  guide: '指引',
  mystery: '隐线',
  opposition: '对立',
};

export function toChineseRelationshipKind(kind: string | null | undefined): string {
  const normalized = String(kind ?? '').trim();
  if (!normalized) return '关系';

  const lower = normalized.toLowerCase();
  return RELATION_KIND_LABELS[lower] ?? normalized;
}
