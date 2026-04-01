import { useMemo, useState } from 'react';
import type { NarrativeUnit } from '../types/pipelineArtifacts';

interface NarrativeTimelineProps {
  units: NarrativeUnit[];
  unitRange: [number, number];
  onRoleClick?: (roleName: string) => void;
  onEventClick?: (eventId: string) => void;
}

export function NarrativeTimeline({ units, unitRange, onRoleClick, onEventClick }: NarrativeTimelineProps) {
  const [selectedUnit, setSelectedUnit] = useState<NarrativeUnit | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredUnits = useMemo(() => {
    const [minUnit, maxUnit] = unitRange;
    const inRange = units.filter(
      (u) =>
        u.start_unit_index <= maxUnit && u.end_unit_index >= minUnit,
    );
    if (!searchQuery) return inRange;
    const query = searchQuery.toLowerCase();
    return inRange.filter(
      (u) =>
        (u.title ?? '').toLowerCase().includes(query) ||
        (u.display_summary ?? '').toLowerCase().includes(query) ||
        u.main_roles.some((r) => r.toLowerCase().includes(query)) ||
        u.main_locations.some((l) => l.toLowerCase().includes(query)) ||
        u.season_name.toLowerCase().includes(query),
    );
  }, [units, unitRange, searchQuery]);

  // Group by season
  const bySeason = useMemo(() => {
    const map = new Map<string, NarrativeUnit[]>();
    for (const u of filteredUnits) {
      const sn = u.season_name || '未分季';
      if (!map.has(sn)) map.set(sn, []);
      map.get(sn)!.push(u);
    }
    return Array.from(map.entries()).map(([season, seasonUnits]) => ({
      season,
      units: seasonUnits.sort((a, b) => a.unit_index - b.unit_index),
    }));
  }, [filteredUnits]);

  const hasDossiers = units.some((u) => u.title);

  return (
    <div className="view-shell">
      <div className="view-header">
        <div>
          <h3 className="view-title">剧情单元时间轴</h3>
          <p className="view-copy">
            按剧情结构把章节分组，每个单元代表一段有完整起承转合的叙事。
            {!hasDossiers && (
              <span className="ml-2 text-[var(--text-muted)]">（剧情单元档案尚未生成，显示结构信息）</span>
            )}
          </p>
        </div>
        <div className="view-toolbar">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索单元标题、人物或地点…"
            className="search-input md:w-72"
          />
          {searchQuery && (
            <button type="button" className="ghost-button" onClick={() => setSearchQuery('')}>
              清除
            </button>
          )}
          <div className="float-stat">
            {filteredUnits.length} / {units.length} 个单元
          </div>
        </div>
      </div>

      {filteredUnits.length === 0 ? (
        <div className="empty-state">
          {searchQuery ? '没有匹配的剧情单元。' : '当前范围暂时没有可显示的剧情单元。'}
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]" style={{ minHeight: '520px' }}>
          {/* List column */}
          <div className="detail-card overflow-y-auto max-h-[640px] pr-2">
            <div className="space-y-6">
              {bySeason.map(({ season, units: seasonUnits }) => (
                <div key={season}>
                  <div className="mb-3 text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
                    {season}
                  </div>
                  <div className="relative">
                    <div className="absolute left-[28px] top-0 bottom-0 w-px bg-[var(--line-strong)]" />
                    <div className="space-y-2">
                      {seasonUnits.map((unit) => {
                        const isSelected = selectedUnit?.unit_id === unit.unit_id;
                        const chapterRange =
                          unit.start_unit_index === unit.end_unit_index
                            ? `第 ${unit.start_unit_index} 章`
                            : `第 ${unit.start_unit_index}–${unit.end_unit_index} 章`;
                        return (
                          <button
                            key={unit.unit_id}
                            type="button"
                            className={`relative flex w-full items-start gap-4 rounded-[22px] px-3 py-3 text-left transition-colors ${
                              isSelected
                                ? 'bg-[rgba(230,194,139,0.18)]'
                                : 'hover:bg-[rgba(255,252,247,0.8)]'
                            }`}
                            onClick={() => setSelectedUnit(isSelected ? null : unit)}
                          >
                            <div
                              className={`relative z-10 mt-1 h-4 w-4 shrink-0 rounded-full transition-transform ${
                                isSelected
                                  ? 'scale-110 bg-[var(--accent-deep)]'
                                  : 'bg-[var(--accent-cinnabar)]'
                              }`}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-semibold text-[var(--text-primary)]">
                                  {unit.title || chapterRange}
                                </span>
                                <span className="tag-pill text-xs">{chapterRange}</span>
                              </div>
                              {unit.display_summary ? (
                                <p className="mt-1 text-sm text-[var(--text-muted)] line-clamp-2">
                                  {unit.display_summary}
                                </p>
                              ) : (
                                <p className="mt-1 text-sm text-[var(--text-muted)]">
                                  {unit.main_roles.slice(0, 4).join('、')}
                                  {unit.main_roles.length > 4 ? ` 等 ${unit.main_roles.length} 人` : ''}
                                </p>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Detail column */}
          <div className="detail-card flex flex-col overflow-y-auto max-h-[640px]">
            {selectedUnit ? (
              <NarrativeUnitDetail
                unit={selectedUnit}
                onClose={() => setSelectedUnit(null)}
                onRoleClick={onRoleClick}
                onEventClick={onEventClick}
              />
            ) : (
              <div className="empty-state flex-1 flex items-center justify-center">
                点击左侧剧情单元查看详情
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

interface NarrativeUnitDetailProps {
  unit: NarrativeUnit;
  onClose: () => void;
  onRoleClick?: (roleName: string) => void;
  onEventClick?: (eventId: string) => void;
}

function NarrativeUnitDetail({ unit, onClose, onRoleClick, onEventClick }: NarrativeUnitDetailProps) {
  const chapterRange =
    unit.start_unit_index === unit.end_unit_index
      ? `第 ${unit.start_unit_index} 章`
      : `第 ${unit.start_unit_index}–${unit.end_unit_index} 章`;

  return (
    <div className="flex flex-col gap-4 p-1">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="view-title text-[1.15rem]">{unit.title || chapterRange}</h4>
            <span className="tag-pill">{unit.season_name}</span>
            <span className="tag-pill">{chapterRange}</span>
          </div>
          {unit.dramatic_function && (
            <p className="view-copy mt-1 text-[var(--accent-deep)] font-medium">{unit.dramatic_function}</p>
          )}
        </div>
        <button type="button" className="modal-close shrink-0" onClick={onClose}>
          ×
        </button>
      </div>

      {unit.display_summary && (
        <div>
          <p className="section-kicker">概要</p>
          <p className="detail-text">{unit.display_summary}</p>
        </div>
      )}

      {unit.long_summary && (
        <div>
          <p className="section-kicker">详细评述</p>
          <p className="detail-text whitespace-pre-line">{unit.long_summary}</p>
        </div>
      )}

      {unit.what_changes && (
        <div>
          <p className="section-kicker">经此段后发生的变化</p>
          <p className="detail-text">{unit.what_changes}</p>
        </div>
      )}

      {unit.stakes && (
        <div>
          <p className="section-kicker">关键赌注</p>
          <p className="detail-text italic">{unit.stakes}</p>
        </div>
      )}

      {unit.main_roles.length > 0 && (
        <div>
          <p className="section-kicker">主要角色</p>
          <div className="chip-wrap mt-2">
            {unit.main_roles.map((role) => (
              <button
                key={role}
                type="button"
                className="pill-chip hover:bg-[rgba(182,120,42,0.18)]"
                onClick={() => onRoleClick?.(role)}
              >
                {role}
              </button>
            ))}
          </div>
        </div>
      )}

      {unit.main_locations.length > 0 && (
        <div>
          <p className="section-kicker">主要地点</p>
          <div className="chip-wrap mt-2">
            {unit.main_locations.map((loc) => (
              <span key={loc} className="pill-chip">
                {loc}
              </span>
            ))}
          </div>
        </div>
      )}

      {unit.source_event_ids && unit.source_event_ids.length > 0 && (
        <div>
          <p className="section-kicker">关键事件（{unit.source_event_ids.length}）</p>
          <div className="mt-2 space-y-1 max-h-[180px] overflow-y-auto pr-1">
            {unit.source_event_ids.slice(0, 20).map((eid) => (
              <button
                key={eid}
                type="button"
                className="w-full text-left text-sm text-[var(--accent-deep)] hover:underline truncate"
                onClick={() => onEventClick?.(eid)}
              >
                {eid}
              </button>
            ))}
            {unit.source_event_ids.length > 20 && (
              <p className="text-xs text-[var(--text-muted)]">…共 {unit.source_event_ids.length} 条</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
