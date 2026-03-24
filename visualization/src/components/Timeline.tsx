import { useMemo, useState } from 'react';
import type { BookConfig } from '../types/pipelineArtifacts';
import type { TimelineEventUnified } from '../types/unified';

interface TimelineProps {
  bookConfig: BookConfig | null;
  events: TimelineEventUnified[];
  onEventClick?: (event: TimelineEventUnified) => void;
}

interface ProgressPoint {
  progress: number;
  label: string;
  events: TimelineEventUnified[];
}

export function Timeline({ bookConfig, events, onEventClick }: TimelineProps) {
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
    <div className="w-full bg-white rounded-lg shadow-md p-4">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex-1 relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索事件、人物、地点..."
            className="w-full px-4 py-2 pl-10 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513] focus:border-transparent"
          />
          <span className="absolute left-3 top-2.5 text-gray-400">搜索</span>
        </div>
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="px-3 py-2 text-sm text-[#8b4513] hover:bg-[#faf8f5] rounded-lg transition-colors"
          >
            清除
          </button>
        )}
        <div className="text-sm text-gray-500">
          {filteredEvents.length} / {events.length} 事件
        </div>
      </div>

      <div className="flex gap-4" style={{ minHeight: '500px' }}>
        <div className="flex-1 overflow-y-auto max-h-[600px] pr-2">
          {progressPoints.length === 0 && eventsWithoutProgress.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              {searchQuery ? '没有匹配的事件' : '暂无事件数据'}
            </div>
          ) : (
            <div className="relative">
              <div className="absolute left-[90px] top-0 bottom-0 w-0.5 bg-[#d4c5b5]" />

              {progressPoints.map((point) => (
                <div
                  key={point.progress}
                  className={`relative flex items-start mb-3 cursor-pointer group ${
                    selectedPoint?.progress === point.progress ? 'bg-[#faf8f5] rounded-lg -mx-2 px-2 py-1' : ''
                  }`}
                  onClick={() => setSelectedPoint(selectedPoint?.progress === point.progress ? null : point)}
                >
                  <div className="w-[85px] flex-shrink-0 text-right pr-3">
                    <span
                      className={`text-sm font-medium ${
                        selectedPoint?.progress === point.progress ? 'text-[#8b4513]' : 'text-gray-600'
                      }`}
                    >
                      {point.progress}
                    </span>
                  </div>

                  <div
                    className={`relative z-10 w-4 h-4 rounded-full flex-shrink-0 mt-0.5 transition-all ${
                      selectedPoint?.progress === point.progress
                        ? 'bg-[#8b4513] scale-125'
                        : 'bg-[#c41e3a] group-hover:scale-110'
                    }`}
                  >
                    {point.events.length > 1 && (
                      <span className="absolute -top-1 -right-1 bg-[#8b4513] text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center font-bold">
                        {point.events.length}
                      </span>
                    )}
                  </div>

                  <div className="ml-4 flex-1 min-w-0">
                    <div
                      className={`text-sm font-medium truncate ${
                        selectedPoint?.progress === point.progress ? 'text-[#8b4513]' : 'text-[#2c1810]'
                      }`}
                    >
                      {point.label}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {point.events.length === 1 ? point.events[0].name : `${point.events[0].name} 等 ${point.events.length} 个事件`}
                    </div>
                  </div>

                  <div
                    className={`text-gray-400 transition-transform ${
                      selectedPoint?.progress === point.progress ? 'rotate-90' : ''
                    }`}
                  >
                    ›
                  </div>
                </div>
              ))}

              {eventsWithoutProgress.length > 0 && (
                <div className="mt-6 pt-4 border-t border-[#d4c5b5]">
                  <div className="text-sm text-gray-500 mb-2">{progressLabel}不详的事件 ({eventsWithoutProgress.length})</div>
                  {eventsWithoutProgress.map((event) => (
                    <div
                      key={event.id}
                      className="ml-[105px] mb-2 p-2 bg-gray-50 rounded cursor-pointer hover:bg-[#faf8f5] transition-colors"
                      onClick={() => onEventClick?.(event)}
                    >
                      <div className="text-sm font-medium text-[#2c1810]">{event.name}</div>
                      {event.location && <div className="text-xs text-gray-500">地点：{event.location}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="w-80 flex-shrink-0 border-l border-[#d4c5b5] pl-4">
          {selectedPoint ? (
            <div className="h-full flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-bold text-[#8b4513]">{selectedPoint.label}</h3>
                <button onClick={() => setSelectedPoint(null)} className="text-gray-400 hover:text-gray-600">
                  ×
                </button>
              </div>
              <div className="text-sm text-gray-500 mb-3">{selectedPoint.events.length} 个事件</div>
              <div className="flex-1 overflow-y-auto space-y-3 max-h-[520px] pr-1">
                {selectedPoint.events.map((event) => (
                  <div
                    key={event.id}
                    className="p-3 bg-[#faf8f5] border border-[#d4c5b5] rounded-lg cursor-pointer hover:border-[#8b4513] transition-colors"
                    onClick={() => onEventClick?.(event)}
                  >
                    <div className="font-medium text-[#2c1810] mb-1">{event.name}</div>
                    {event.location && <div className="text-xs text-gray-600 mb-1">地点：{event.location}</div>}
                    {event.participants.length > 0 && (
                      <div className="text-xs text-gray-500 mb-2">
                        参与者：{event.participants.slice(0, 3).join('、')}
                        {event.participants.length > 3 && ` 等${event.participants.length}人`}
                      </div>
                    )}
                    {event.description && <p className="text-sm text-gray-600 line-clamp-2">{event.description}</p>}
                    <div className="mt-2 text-xs text-[#8b4513]">点击查看详情 →</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-gray-500 text-sm bg-[#faf8f5] rounded-lg border border-[#d4c5b5]">
              点击左侧进度点查看事件
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-[#d4c5b5] flex items-center gap-6 text-sm text-gray-500">
        <div>
          <span className="font-medium text-[#2c1810]">{progressPoints.length}</span> 个{progressLabel}点
        </div>
        <div>
          <span className="font-medium text-[#2c1810]">{filteredEvents.filter((event) => event.progressStart !== null).length}</span> 个有进度事件
        </div>
        {eventsWithoutProgress.length > 0 && (
          <div>
            <span className="font-medium text-gray-600">{eventsWithoutProgress.length}</span> 个进度不详
          </div>
        )}
      </div>
    </div>
  );
}
