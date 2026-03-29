import { type ReactNode, useMemo, useState } from 'react';
import type { ChapterIndex } from '../types/pipelineArtifacts';
import type {
  RoleLinkUnified,
  RoleNodeUnified,
  TimelineEventUnified,
  UnifiedKnowledgeBase,
  UnifiedLocation,
  UnifiedRelation,
} from '../types/unified';
import { getJumpTargetsByUnits, getPrimaryJumpTarget, type ChapterJumpTarget } from '../utils/sourceText';

function formatEventContextLabel(event: TimelineEventUnified, chapterIndex: ChapterIndex | null): string {
  const baseLabel = event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`;
  if (!chapterIndex) return baseLabel;
  const unit = chapterIndex.units.find((item) => item.unit_index === event.unitIndex);
  if (!unit?.season_name) return baseLabel;
  return baseLabel.startsWith(unit.season_name) ? baseLabel : `${unit.season_name} · ${baseLabel}`;
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

function formatUnitSpan(units: number[] | undefined, unitLabel: string): string {
  if (!units || units.length === 0) return `未知${unitLabel}`;
  const sorted = [...units].sort((a, b) => a - b);
  const start = sorted[0];
  const end = sorted[sorted.length - 1];
  return start === end ? `${unitLabel}${start}` : `${unitLabel}${start}-${end}`;
}

/* ------------------------------------------------------------------ */
/*  Shared paginated "related events" section                         */
/* ------------------------------------------------------------------ */

const EVENTS_PAGE_SIZE = 10;

function RelatedEventsSection(props: {
  events: TimelineEventUnified[];
  chapterIndex: ChapterIndex | null;
  onEventClick?: (event: TimelineEventUnified) => void;
}) {
  const { events, chapterIndex, onEventClick } = props;
  const [page, setPage] = useState(0);
  const [ascending, setAscending] = useState(true);
  const [jumpInput, setJumpInput] = useState('');

  const sortedEvents = useMemo(
    () => (ascending ? events : [...events].reverse()),
    [events, ascending],
  );

  const total = sortedEvents.length;
  const totalPages = Math.max(1, Math.ceil(total / EVENTS_PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * EVENTS_PAGE_SIZE;
  const pageEvents = sortedEvents.slice(start, start + EVENTS_PAGE_SIZE);

  function handleJump() {
    const n = Number.parseInt(jumpInput, 10);
    if (Number.isFinite(n) && n >= 1 && n <= totalPages) {
      setPage(n - 1);
    }
    setJumpInput('');
  }

  return (
    <section className="detail-section">
      <div className="flex items-center justify-between mb-1">
        <h3 className="detail-heading mb-0">相关事件</h3>
        {total > 1 && (
          <button
            type="button"
            className="outline-button text-xs px-1.5 py-0.5"
            onClick={() => { setAscending((v) => !v); setPage(0); }}
          >
            {ascending ? '正序 ↑' : '倒序 ↓'}
          </button>
        )}
      </div>

      {/* pagination controls */}
      {total > EVENTS_PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs mb-2 flex-wrap gap-y-1">
          <span className="status-note">
            第 {start + 1}–{Math.min(start + EVENTS_PAGE_SIZE, total)} 条 / 共 {total} 条
          </span>
          <div className="flex items-center gap-1">
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" disabled={safePage === 0} onClick={() => setPage(0)}>
              首页
            </button>
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
              上一页
            </button>
            <button
              type="button"
              className="outline-button text-xs px-1.5 py-0.5"
              disabled={safePage >= totalPages - 1}
              onClick={() => setPage(safePage + 1)}
            >
              下一页
            </button>
            <button
              type="button"
              className="outline-button text-xs px-1.5 py-0.5"
              disabled={safePage >= totalPages - 1}
              onClick={() => setPage(totalPages - 1)}
            >
              末页
            </button>
            <span className="text-[var(--text-muted)] mx-0.5">|</span>
            <input
              type="text"
              inputMode="numeric"
              className="w-10 text-center text-xs rounded border border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-primary)] px-1 py-0.5"
              placeholder={`${safePage + 1}`}
              value={jumpInput}
              onChange={(e) => setJumpInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleJump(); }}
            />
            <span className="text-[var(--text-muted)]">/ {totalPages}</span>
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" onClick={handleJump}>
              跳转
            </button>
          </div>
        </div>
      )}

      <div className="info-list max-h-56 overflow-y-auto pr-1">
        {pageEvents.map((event) => (
          <button
            key={event.id}
            type="button"
            className="detail-card text-left hover:border-[var(--accent-deep)]"
            onClick={() => onEventClick?.(event)}
          >
            <div className="font-semibold text-[var(--text-primary)]">{event.name}</div>
            <div className="status-note mt-2">{formatEventContextLabel(event, chapterIndex)}</div>
          </button>
        ))}
      </div>
    </section>
  );
}

function ModalShell(props: {
  title: string;
  subtitle?: string | null;
  wide?: boolean;
  onClose: () => void;
  onBack?: () => void;
  children: ReactNode;
}) {
  const { title, subtitle, wide, onBack, onClose, children } = props;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal-panel ${wide ? 'modal-panel--wide' : ''}`} onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div className="flex flex-wrap items-start gap-3">
            {onBack ? (
              <button type="button" className="outline-button" onClick={onBack}>
                返回上一层
              </button>
            ) : null}
            <div>
              <h2 className="modal-title">{title}</h2>
              {subtitle ? <p className="detail-text mt-2">{subtitle}</p> : null}
            </div>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function renderRoleChip(opts: {
  name: string;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
  onClick: (name: string) => void;
}) {
  const { name, kb, availableRoleIds, onClick } = opts;
  const unitLabel = kb?.unit_label ?? '章节';
  const roleId = resolveRoleId(kb, name);
  const available = roleId ? availableRoleIds.has(roleId) : false;
  const units = roleId
    ? kb?.roles?.[roleId]?.units_appeared ?? kb?.roles?.[roleId]?.juans_appeared
    : undefined;
  const unitSpan = formatUnitSpan(units, unitLabel);

  if (available) {
    return (
      <button key={name} type="button" className="pill-chip hover:underline" onClick={() => onClick(name)}>
        {name}
      </button>
    );
  }

  return (
    <span key={name} className="pill-chip pill-chip--muted" title={`当前范围不可用，出现于：${unitSpan}`}>
      {name}
      <span className="text-[10px]">({unitSpan})</span>
    </span>
  );
}

function renderJumpLink(target: ChapterJumpTarget, className = 'outline-button') {
  return (
    <a
      key={`${target.unitIndex}-${target.anchor ?? 'chapter'}`}
      href={target.href}
      className={className}
      title={target.title}
      target="_blank"
    >
      {target.label}
    </a>
  );
}

function renderJumpSection(title: string, targets: ChapterJumpTarget[], extraText?: string | null) {
  if (!targets.length && !extraText) return null;
  return (
    <section className="detail-section">
      <h3 className="detail-heading">{title}</h3>
      {targets.length > 0 ? <div className="chip-wrap">{targets.map((target) => renderJumpLink(target))}</div> : null}
      {extraText ? <p className="status-note mt-3">{extraText}</p> : null}
    </section>
  );
}

interface EventDetailProps {
  event: TimelineEventUnified | null;
  onClose: () => void;
  onBack?: () => void;
  onEntityClick?: (entityName: string) => void;
  onLocationClick?: (locationName: string) => void;
  chapterIndex: ChapterIndex | null;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function EventDetail({ event, onClose, onBack, onEntityClick, onLocationClick, chapterIndex, kb, availableRoleIds }: EventDetailProps) {
  if (!event) return null;

  const progressLabel = kb?.progress_label ?? '叙事进度';
  const unitLabel = kb?.unit_label ?? '章节';
  const chapterTarget = getPrimaryJumpTarget(chapterIndex, {
    unitIndex: event.unitIndex,
    progressIndex: event.progressStart,
    fallbackLabel: '查看对应原文',
  });

  return (
    <ModalShell title={event.name} onClose={onClose} onBack={onBack}>
      {(event.progressLabel || event.progressStart !== null) && (
        <section className="detail-section">
          <h3 className="detail-heading">{progressLabel}</h3>
          <p className="detail-text">{formatEventContextLabel(event, chapterIndex)}</p>
        </section>
      )}

      {event.timeText && (
        <section className="detail-section">
          <h3 className="detail-heading">原文时间</h3>
          <p className="detail-text">{event.timeText}</p>
        </section>
      )}

      {event.location && (
        <section className="detail-section">
          <h3 className="detail-heading">地点</h3>
          {onLocationClick ? (
            <button type="button" className="card-action" onClick={() => onLocationClick(event.location!)}>
              {event.location}
            </button>
          ) : (
            <p className="detail-text">{event.location}</p>
          )}
        </section>
      )}

      <section className="detail-section">
        <h3 className="detail-heading">参与人物</h3>
        {event.participants.length > 0 ? (
          <div className="chip-wrap">
            {event.participants.map((name) =>
              renderRoleChip({
                name,
                kb,
                availableRoleIds,
                onClick: (roleName) => {
                  onEntityClick?.(roleName);
                },
              })
            )}
          </div>
        ) : (
          <p className="status-note">当前事件未记录明确参与人物。</p>
        )}
      </section>

      <section className="detail-section">
        <h3 className="detail-heading">描述</h3>
        <p className="detail-text">{event.description}</p>
      </section>

      {event.background && (
        <section className="detail-section">
          <h3 className="detail-heading">背景</h3>
          <p className="detail-text">{event.background}</p>
        </section>
      )}

      {event.significance && (
        <section className="detail-section">
          <h3 className="detail-heading">剧情意义</h3>
          <p className="detail-text">{event.significance}</p>
        </section>
      )}

      {renderJumpSection('原文定位', chapterTarget ? [chapterTarget] : [], chapterTarget ? `定位到${unitLabel}${chapterTarget.unitIndex}的对应段落。` : null)}

      <section className="detail-section divider-line">
        <p className="status-note">
          来源：{unitLabel}
          {event.unitIndex}
        </p>
      </section>
    </ModalShell>
  );
}

interface RoleDetailProps {
  role: RoleNodeUnified | null;
  onClose: () => void;
  onBack?: () => void;
  onEntityClick?: (entityName: string) => void;
  onEventClick?: (event: TimelineEventUnified) => void;
  relatedRoleNames?: string[];
  relatedEvents?: TimelineEventUnified[];
  chapterIndex: ChapterIndex | null;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function RoleDetail({
  role,
  onClose,
  onBack,
  onEntityClick,
  onEventClick,
  relatedRoleNames,
  relatedEvents,
  chapterIndex,
  kb,
  availableRoleIds,
}: RoleDetailProps) {
  if (!role) return null;

  const unitLabel = kb?.unit_label ?? '章节';
  const sourceChapterTargets = getJumpTargetsByUnits(chapterIndex, role.units, 10);
  const visibleRelatedRoleNames =
    relatedRoleNames && relatedRoleNames.length > 0 ? relatedRoleNames : role.relatedEntities;

  return (
    <ModalShell title={role.name} onClose={onClose} onBack={onBack}>
      {role.aliases.length > 0 && (
        <section className="detail-section">
          <h3 className="detail-heading">别名</h3>
          <div className="chip-wrap">
            {role.aliases.map((alias) => (
              <span key={alias} className="pill-chip">
                {alias}
              </span>
            ))}
          </div>
        </section>
      )}

      {role.power && (
        <section className="detail-section">
          <h3 className="detail-heading">阵营</h3>
          <div className="chip-wrap">
            <span className="pill-chip pill-chip--strong">{role.power}</span>
          </div>
        </section>
      )}

      <section className="detail-section">
        <h3 className="detail-heading">简介</h3>
        <p className="detail-text">{role.description || '暂无描述。'}</p>
      </section>

      {visibleRelatedRoleNames.length > 0 && (
        <section className="detail-section">
          <h3 className="detail-heading">相关人物</h3>
          <div className="chip-wrap">
            {visibleRelatedRoleNames.slice(0, 15).map((name) =>
              renderRoleChip({
                name,
                kb,
                availableRoleIds,
                onClick: (roleName) => {
                  onEntityClick?.(roleName);
                },
              })
            )}
            {visibleRelatedRoleNames.length > 15 && (
              <span className="pill-chip pill-chip--muted">+{visibleRelatedRoleNames.length - 15}</span>
            )}
          </div>
        </section>
      )}

      {relatedEvents && relatedEvents.length > 0 && (
        <RelatedEventsSection events={relatedEvents} chapterIndex={chapterIndex} onEventClick={onEventClick} />
      )}

      {renderJumpSection(
        '原文定位',
        sourceChapterTargets,
        sourceChapterTargets.length > 0 ? `可直接跳到该人物在当前范围内出现过的${unitLabel}。` : null
      )}

      <section className="detail-section divider-line">
        <div className="info-list">
          <div className="info-row">
            <span>出现次数</span>
            <strong>{role.appearances} 次</strong>
          </div>
          <div className="detail-section">
            <h3 className="detail-heading">出现{unitLabel}</h3>
            <div className="chip-wrap">
              {role.units.map((unit) => (
                <span key={unit} className="pill-chip">
                  {unitLabel}
                  {unit}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>
    </ModalShell>
  );
}

interface LocationListProps {
  locations: UnifiedLocation[];
  onLocationClick?: (location: UnifiedLocation) => void;
}

export function LocationList({ locations, onLocationClick }: LocationListProps) {
  return (
    <div className="view-shell">
      <div className="view-header">
        <div>
          <h3 className="view-title">地点列表</h3>
          <p className="view-copy">从这里快速进入地点详情。</p>
        </div>
      </div>
      <div className="info-list max-h-96 overflow-y-auto pr-1">
        {locations.map((location) => (
          <button
            key={location.id}
            type="button"
            className="detail-card text-left hover:border-[var(--accent-deep)]"
            onClick={() => onLocationClick?.(location)}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="font-semibold text-[var(--accent-deep)]">{location.canonical_name}</div>
              {location.location_type ? <span className="pill-chip pill-chip--strong">{location.location_type}</span> : null}
            </div>
            {location.modern_name ? <p className="status-note mt-2">现代地名：{location.modern_name}</p> : null}
            {location.description ? <p className="detail-text mt-2">{location.description}</p> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

interface LocationDetailProps {
  location: UnifiedLocation | null;
  relatedEvents: TimelineEventUnified[];
  relatedRoles: string[];
  relatedActions: UnifiedRelation[];
  onClose: () => void;
  onBack?: () => void;
  onEntityClick?: (entityName: string) => void;
  onEventClick?: (event: TimelineEventUnified) => void;
  chapterIndex: ChapterIndex | null;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function LocationDetail({
  location,
  relatedEvents,
  relatedRoles,
  relatedActions,
  onClose,
  onBack,
  onEntityClick,
  onEventClick,
  chapterIndex,
  kb,
  availableRoleIds,
}: LocationDetailProps) {
  if (!location) return null;

  const unitLabel = kb?.unit_label ?? '章节';
  const units = location.units_appeared ?? location.juans_appeared ?? [];
  const sourceChapterTargets = getJumpTargetsByUnits(chapterIndex, units, 8);

  return (
    <ModalShell
      title={location.canonical_name}
      subtitle={location.modern_name ? `现代地名：${location.modern_name}` : undefined}
      onClose={onClose}
      onBack={onBack}
      wide
    >
      {location.location_type && (
        <section className="detail-section">
          <h3 className="detail-heading">类型</h3>
          <div className="chip-wrap">
            <span className="pill-chip pill-chip--strong">{location.location_type}</span>
          </div>
        </section>
      )}

      {location.description && (
        <section className="detail-section">
          <h3 className="detail-heading">描述</h3>
          <p className="detail-text">{location.description}</p>
        </section>
      )}

      {relatedRoles.length > 0 && (
        <section className="detail-section">
          <h3 className="detail-heading">相关人物</h3>
          <div className="chip-wrap">
            {relatedRoles.map((name) =>
              renderRoleChip({
                name,
                kb,
                availableRoleIds,
                onClick: (roleName) => {
                  onEntityClick?.(roleName);
                },
              })
            )}
          </div>
        </section>
      )}

      {relatedEvents.length > 0 && (
        <RelatedEventsSection events={relatedEvents} chapterIndex={chapterIndex} onEventClick={onEventClick} />
      )}

      {renderJumpSection('原文定位', sourceChapterTargets, sourceChapterTargets.length > 0 ? `可跳到该地点在原文中出现的相关${unitLabel}。` : null)}

      {relatedActions.length > 0 && (
        <section className="detail-section">
          <h3 className="detail-heading">关联关系</h3>
          <div className="info-list">
            {relatedActions.map((action) => (
              <div key={action.id} className="detail-card detail-text">
                {action.from_entity} → {action.to_entity} · {action.primary_action}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="detail-section divider-line">
        <h3 className="detail-heading">出现{unitLabel}</h3>
        <div className="chip-wrap">
          {units.map((unit) => (
            <span key={unit} className="pill-chip">
              {unitLabel}
              {unit}
            </span>
          ))}
        </div>
      </section>
    </ModalShell>
  );
}

interface RelationDetailProps {
  relations: RoleLinkUnified[];
  sourceName: string;
  targetName: string;
  onClose: () => void;
  onBack?: () => void;
  onEntityClick?: (entityName: string) => void;
  onEventClick?: (event: TimelineEventUnified) => void;
  relatedRoleNames?: string[];
  relatedEvents?: TimelineEventUnified[];
  chapterIndex: ChapterIndex | null;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function RelationDetail({
  relations,
  sourceName,
  targetName,
  onClose,
  onBack,
  onEntityClick,
  onEventClick,
  relatedEvents,
  chapterIndex,
  kb,
  availableRoleIds,
}: RelationDetailProps) {
  const unitLabel = kb?.unit_label ?? '章节';
  const sourceId = resolveRoleId(kb, sourceName);
  const targetId = resolveRoleId(kb, targetName);
  const sourceAvailable = sourceId ? availableRoleIds.has(sourceId) : false;
  const targetAvailable = targetId ? availableRoleIds.has(targetId) : false;
  const allUnits = [...new Set(relations.flatMap((relation) => relation.sourceUnits || []))].sort((a, b) => a - b);
  const totalWeight = relations.reduce((sum, relation) => sum + relation.weight, 0);
  const earliestProgress = relations
    .map((relation) => relation.progressStart)
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b)[0];
  const primaryJumpTarget = getPrimaryJumpTarget(chapterIndex, {
    unitIndex: allUnits[0] ?? null,
    progressIndex: earliestProgress ?? null,
    fallbackLabel: '查看最早原文位置',
  });
  const sourceChapterTargets = getJumpTargetsByUnits(chapterIndex, allUnits, 8);

  return (
    <ModalShell title="人物关系详情" subtitle={`${sourceName} 与 ${targetName}`} onClose={onClose} onBack={onBack} wide>
      <section className="detail-section">
        <div className="chip-wrap">
          <button
            type="button"
            className={sourceAvailable ? 'card-action' : 'pill-chip pill-chip--muted'}
            onClick={() => {
              if (!sourceAvailable) return;
              onEntityClick?.(sourceName);
            }}
            disabled={!sourceAvailable}
          >
            {sourceName}
          </button>
          <span className="pill-chip pill-chip--muted">↔</span>
          <button
            type="button"
            className={targetAvailable ? 'card-action' : 'pill-chip pill-chip--muted'}
            onClick={() => {
              if (!targetAvailable) return;
              onEntityClick?.(targetName);
            }}
            disabled={!targetAvailable}
          >
            {targetName}
          </button>
        </div>
      </section>

      <section className="detail-section">
        <div className="info-list">
          <div className="info-row">
            <span>关系记录</span>
            <strong>{relations.length} 条</strong>
          </div>
          <div className="info-row">
            <span>总互动次数</span>
            <strong>{totalWeight} 次</strong>
          </div>
          {earliestProgress !== undefined && (
            <div className="info-row">
              <span>最早进度</span>
              <strong>{earliestProgress}</strong>
            </div>
          )}
        </div>
      </section>

      {renderJumpSection(
        '原文定位',
        primaryJumpTarget ? [primaryJumpTarget, ...sourceChapterTargets.filter((item) => item.unitIndex !== primaryJumpTarget.unitIndex)] : sourceChapterTargets,
        sourceChapterTargets.length > 0 ? `可跳到这组关系涉及的相关${unitLabel}。` : null
      )}

      <section className="detail-section">
        <h3 className="detail-heading">关系记录</h3>
        <div className="info-list">
          {relations.map((relation, index) => (
            <div key={`${relation.source}-${relation.target}-${index}`} className="detail-card">
              <div className="flex flex-wrap items-center gap-2">
                <span className="pill-chip pill-chip--strong">关系 {index + 1}</span>
                <span className="pill-chip">{relation.action}</span>
                {relation.progressLabel ? <span className="pill-chip">{relation.progressLabel}</span> : null}
                {relation.timeText ? <span className="pill-chip">{relation.timeText}</span> : null}
              </div>
              {relation.actionTypes.length > 0 && (
                <div className="chip-wrap mt-3">
                  {relation.actionTypes.map((type) => (
                    <span key={type} className="pill-chip">
                      {type}
                    </span>
                  ))}
                </div>
              )}
              {relation.contexts.length > 0 && (
                <div className="info-list mt-3">
                  {relation.contexts.map((context, contextIndex) => (
                    <div key={contextIndex} className="subtle-card detail-text">
                      {context}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {relatedEvents && relatedEvents.length > 0 && (
        <RelatedEventsSection events={relatedEvents} chapterIndex={chapterIndex} onEventClick={onEventClick} />
      )}

      {allUnits.length > 0 && (
        <section className="detail-section divider-line">
          <h3 className="detail-heading">出现{unitLabel}</h3>
          <div className="chip-wrap">
            {allUnits.map((unit) => (
              <span key={unit} className="pill-chip">
                {unitLabel}
                {unit}
              </span>
            ))}
          </div>
        </section>
      )}
    </ModalShell>
  );
}

interface NetworkRoleRelationGroup {
  counterpartId: string;
  counterpartName: string;
  relations: RoleLinkUnified[];
  totalWeight: number;
  actionTypes: string[];
  sourceUnits: number[];
  earliestProgress: number | null;
}

interface NetworkRoleRelationsDetailProps {
  role: RoleNodeUnified | null;
  relationGroups: NetworkRoleRelationGroup[];
  onClose: () => void;
  onBack?: () => void;
  onRelationClick?: (sourceId: string, targetId: string) => void;
  onEntityClick?: (entityName: string) => void;
  kb: UnifiedKnowledgeBase | null;
}

export function NetworkRoleRelationsDetail({
  role,
  relationGroups,
  onClose,
  onBack,
  onRelationClick,
  onEntityClick,
  kb,
}: NetworkRoleRelationsDetailProps) {
  if (!role) return null;

  const unitLabel = kb?.unit_label ?? '章节';

  return (
    <ModalShell
      title={`${role.name}的人物关系`}
      subtitle={`当前范围内共识别到 ${relationGroups.length} 个直接关系对象。`}
      onClose={onClose}
      onBack={onBack}
      wide
    >
      {relationGroups.length > 0 ? (
        <div className="info-list">
          {relationGroups.map((group) => (
            <div key={`${role.id}-${group.counterpartId}`} className="detail-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <button
                    type="button"
                    className="text-left text-lg font-semibold text-[var(--accent-deep)] hover:underline"
                    onClick={() => onRelationClick?.(role.id, group.counterpartId)}
                  >
                    {role.name} 与 {group.counterpartName}
                  </button>
                  <div className="chip-wrap mt-3">
                    <span className="pill-chip pill-chip--strong">关系记录 {group.relations.length}</span>
                    <span className="pill-chip">互动权重 {group.totalWeight}</span>
                    {group.earliestProgress !== null ? <span className="pill-chip">最早进度 {group.earliestProgress}</span> : null}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <button
                    type="button"
                    className="ink-button"
                    onClick={() => onRelationClick?.(role.id, group.counterpartId)}
                  >
                    查看关系详情
                  </button>
                  <button
                    type="button"
                    className="outline-button"
                    onClick={() => {
                      onEntityClick?.(group.counterpartName);
                    }}
                  >
                    在图中聚焦
                  </button>
                </div>
              </div>

              {group.actionTypes.length > 0 && (
                <div className="chip-wrap mt-3">
                  {group.actionTypes.map((type) => (
                    <span key={`${group.counterpartId}-${type}`} className="pill-chip">
                      {type}
                    </span>
                  ))}
                </div>
              )}

              {group.sourceUnits.length > 0 && (
                <p className="status-note mt-3">
                  出现{unitLabel}：{formatUnitSpan(group.sourceUnits, unitLabel)}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">当前范围内，这个人物还没有形成可展示的关系边。</div>
      )}
    </ModalShell>
  );
}

/* ------------------------------------------------------------------ */
/*  Role list modal – used by stat rows & faction bar clicks          */
/* ------------------------------------------------------------------ */

const ROLE_LIST_PAGE_SIZE = 20;

interface RoleListModalProps {
  title: string;
  subtitle?: string | null;
  roles: RoleNodeUnified[];
  onClose: () => void;
  onRoleClick: (roleName: string) => void;
}

export function RoleListModal({ title, subtitle, roles, onClose, onRoleClick }: RoleListModalProps) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!search.trim()) return roles;
    const q = search.trim().toLowerCase();
    return roles.filter(
      (role) =>
        role.name.toLowerCase().includes(q) ||
        role.aliases.some((alias) => alias.toLowerCase().includes(q)) ||
        (role.power ?? '').toLowerCase().includes(q)
    );
  }, [roles, search]);

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / ROLE_LIST_PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * ROLE_LIST_PAGE_SIZE;
  const pageRoles = filtered.slice(start, start + ROLE_LIST_PAGE_SIZE);

  return (
    <ModalShell title={title} subtitle={subtitle} onClose={onClose} wide>
      {/* search + counter */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <input
          type="text"
          className="flex-1 min-w-[10rem] rounded border border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-primary)] text-sm px-3 py-1.5"
          placeholder="搜索人物名 / 别名 / 阵营…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
        />
        <span className="status-note whitespace-nowrap">
          共 {total} 人{search.trim() ? ` (全部 ${roles.length})` : ''}
        </span>
      </div>

      {/* pagination */}
      {total > ROLE_LIST_PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs mb-3 flex-wrap gap-y-1">
          <span className="status-note">
            第 {start + 1}–{Math.min(start + ROLE_LIST_PAGE_SIZE, total)} / 共 {total} 人
          </span>
          <div className="flex gap-1">
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" disabled={safePage === 0} onClick={() => setPage(0)}>
              首页
            </button>
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
              上一页
            </button>
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" disabled={safePage >= totalPages - 1} onClick={() => setPage(safePage + 1)}>
              下一页
            </button>
            <button type="button" className="outline-button text-xs px-1.5 py-0.5" disabled={safePage >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>
              末页
            </button>
          </div>
        </div>
      )}

      {/* role grid */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 max-h-[60vh] overflow-y-auto pr-1">
        {pageRoles.map((role) => (
          <button
            key={role.id}
            type="button"
            className="detail-card text-left hover:border-[var(--accent-deep)]"
            onClick={() => onRoleClick(role.name)}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold text-[var(--accent-deep)]">{role.name}</span>
              {role.power && <span className="pill-chip pill-chip--strong text-[10px] shrink-0">{role.power}</span>}
            </div>
            {role.aliases.length > 0 && (
              <p className="status-note mt-1 truncate" title={role.aliases.join('、')}>
                别名：{role.aliases.join('、')}
              </p>
            )}
            <p className="status-note mt-1">出现 {role.appearances} 次</p>
          </button>
        ))}
      </div>

      {total === 0 && <div className="empty-state">没有匹配的人物。</div>}
    </ModalShell>
  );
}
