import { useMemo, useState } from 'react';
import type { BookConfig, ChapterIndex } from '../types/pipelineArtifacts';
import type { TimelineEventUnified } from '../types/unified';
import { getPrimaryJumpTarget } from '../utils/sourceText';

interface TimelineProps {
  bookConfig: BookConfig | null;
  chapterIndex: ChapterIndex | null;
  events: TimelineEventUnified[];
  onEventClick?: (event: TimelineEventUnified) => void;
}

interface ProgressPoint {
  progress: number;
  label: string;
  events: TimelineEventUnified[];
}

export function Timeline({ bookConfig, chapterIndex, events, onEventClick }: TimelineProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPoint, setSelectedPoint] = useState<ProgressPoint | null>(null);
  const progressLabel = bookConfig?.progress_label ?? '叙事进度';

  const filteredEvents = useMemo(() => {
    if (!searchQuery) return events;
    const query = searchQuery.toLowerCase();
    return events.filter(
      (event) =>
        event.name.toLowerCase().includes(query) ||
        event.description.toLowerCase().includes(query) ||
        event.participants.some((participant) => participant.toLowerCase().includes(query)) ||
        (event.location?.toLowerCase().includes(query) ?? false)
    );
  }, [events, searchQuery]);

  const progressPoints = useMemo((): ProgressPoint[] => {
    const byProgress = new Map<number, TimelineEventUnified[]>();

    for (const event of filteredEvents) {
      if (event.progressStart === null) continue;
      const progress = event.progressStart;
      if (!byProgress.has(progress)) {
        byProgress.set(progress, []);
      }
      byProgress.get(progress)!.push(event);
    }

    return Array.from(byProgress.entries())
      .map(([progress, grouped]) => ({
        progress,
        label: grouped[0].progressLabel ?? `${progressLabel} ${progress}`,
        events: grouped,
      }))
      .sort((a, b) => a.progress - b.progress);
  }, [filteredEvents, progressLabel]);

  const eventsWithoutProgress = useMemo(
    () => filteredEvents.filter((event) => event.progressStart === null),
    [filteredEvents]
  );

  return (
    <div className="view-shell">
      <div className="view-header">
        <div>
          <h3 className="view-title">时间轴</h3>
          <p className="view-copy">按叙事进度把事件压成可扫读的节点列，方便先看整体节奏，再点入右侧事件组查看细节。</p>
        </div>
        <div className="view-toolbar">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索事件、人物或地点…"
            className="search-input md:w-72"
          />
          {searchQuery && (
            <button type="button" className="ghost-button" onClick={() => setSearchQuery('')}>
              清除
            </button>
          )}
          <div className="float-stat">
            {filteredEvents.length} / {events.length} 条事件
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]" style={{ minHeight: '520px' }}>
        <div className="detail-card overflow-y-auto max-h-[620px] pr-2">
          {progressPoints.length === 0 && eventsWithoutProgress.length === 0 ? (
            <div className="empty-state">{searchQuery ? '没有匹配的事件。' : '当前范围暂时没有可显示的事件。'}</div>
          ) : (
            <div className="relative">
              <div className="absolute left-[96px] top-0 bottom-0 w-px bg-[var(--line-strong)]" />

              <div className="space-y-3">
                {progressPoints.map((point) => (
                  <button
                    key={point.progress}
                    type="button"
                    className={`relative flex w-full items-start gap-4 rounded-[22px] px-3 py-3 text-left transition-colors ${
                      selectedPoint?.progress === point.progress ? 'bg-[rgba(230,194,139,0.18)]' : 'hover:bg-[rgba(255,252,247,0.8)]'
                    }`}
                    onClick={() => setSelectedPoint(selectedPoint?.progress === point.progress ? null : point)}
                  >
                    <div className="w-[82px] shrink-0 text-right text-sm font-semibold text-[var(--text-secondary)]">
                      {point.progress}
                    </div>
                    <div
                      className={`relative z-10 mt-1 h-4 w-4 shrink-0 rounded-full transition-transform ${
                        selectedPoint?.progress === point.progress ? 'scale-110 bg-[var(--accent-deep)]' : 'bg-[var(--accent-cinnabar)]'
                      }`}
                    >
                      {point.events.length > 1 && (
                        <span className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent-deep)] text-[10px] text-white">
                          {point.events.length}
                        </span>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold text-[var(--text-primary)]">{point.label}</div>
                      <div className="mt-1 truncate text-sm text-[var(--text-muted)]">
                        {point.events.length === 1 ? point.events[0].name : `${point.events[0].name} 等 ${point.events.length} 条事件`}
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {eventsWithoutProgress.length > 0 && (
                <div className="divider-line mt-6">
                  <div className="mb-3 text-sm text-[var(--text-muted)]">
                    未标明{progressLabel}的事件（{eventsWithoutProgress.length}）
                  </div>
                  <div className="space-y-2">
                    {eventsWithoutProgress.map((event) => (
                      <button
                        key={event.id}
                        type="button"
                        className="detail-card w-full text-left hover:border-[rgba(182,120,42,0.28)]"
                        onClick={() => onEventClick?.(event)}
                      >
                        <div className="font-semibold text-[var(--text-primary)]">{event.name}</div>
                        {event.location && <div className="mt-1 text-sm text-[var(--text-muted)]">{event.location}</div>}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="detail-card flex flex-col">
          {selectedPoint ? (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h4 className="view-title text-[1.15rem]">{selectedPoint.label}</h4>
                  <p className="view-copy">{selectedPoint.events.length} 条事件聚集在这一叙事节点。</p>
                </div>
                <button type="button" className="modal-close" onClick={() => setSelectedPoint(null)}>
                  ×
                </button>
              </div>
              <div className="mt-4 grid gap-3 max-h-[520px] overflow-y-auto pr-1">
                {selectedPoint.events.map((event) => (
                  (() => {
                    const jumpTarget = getPrimaryJumpTarget(chapterIndex, {
                      unitIndex: event.unitIndex,
                      progressIndex: event.progressStart,
                    });
                    return (
                      <button
                        key={event.id}
                        type="button"
                        className="detail-card text-left hover:border-[rgba(182,120,42,0.3)]"
                        onClick={() => onEventClick?.(event)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-semibold text-[var(--text-primary)]">{event.name}</div>
                            {event.location && <div className="mt-1 text-sm text-[var(--text-muted)]">{event.location}</div>}
                          </div>
                          <span className="tag-pill">{event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`}</span>
                        </div>
                        {event.participants.length > 0 && (
                          <div className="mt-3 chip-wrap">
                            {event.participants.slice(0, 4).map((participant) => (
                              <span key={`${event.id}-${participant}`} className="pill-chip">
                                {participant}
                              </span>
                            ))}
                          </div>
                        )}
                        {event.description && <p className="detail-text mt-3">{event.description}</p>}
                        {jumpTarget && (
                          <div className="mt-3">
                            <a
                              href={jumpTarget.href}
                              className="outline-button inline-flex"
                              target="_blank"
                              onClick={(clickEvent) => clickEvent.stopPropagation()}
                            >
                              查看原文章节
                            </a>
                          </div>
                        )}
                      </button>
                    );
                  })()
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state h-full flex items-center justify-center">点击左侧节点，查看该叙事阶段下的事件集合。</div>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-3 text-sm text-[var(--text-muted)]">
        <span className="float-stat">{progressPoints.length} 个{progressLabel}节点</span>
        <span className="float-stat">{filteredEvents.filter((event) => event.progressStart !== null).length} 条已标注进度事件</span>
        {eventsWithoutProgress.length > 0 && <span className="float-stat">{eventsWithoutProgress.length} 条进度未明事件</span>}
      </div>
    </div>
  );
}
