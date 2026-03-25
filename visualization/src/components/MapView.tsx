import { useMemo } from 'react';
import type { BookConfig } from '../types/pipelineArtifacts';
import type { RoleNodeUnified, TimelineEventUnified, UnifiedLocation } from '../types/unified';

interface MapViewProps {
  bookConfig: BookConfig | null;
  locations: UnifiedLocation[];
  eventsInRange: TimelineEventUnified[];
  selectedRole: RoleNodeUnified | null;
  selectedEvent: TimelineEventUnified | null;
  focusLocationId?: string | null;
  onLocationClick?: (location: UnifiedLocation) => void;
}

export function MapView({
  bookConfig,
  locations,
  eventsInRange,
  selectedRole,
  selectedEvent,
  focusLocationId,
  onLocationClick,
}: MapViewProps) {
  const locationMap = useMemo(() => {
    const map = new Map<string, UnifiedLocation>();
    for (const location of locations) {
      map.set(location.canonical_name, location);
    }
    return map;
  }, [locations]);

  const focusedLocation = useMemo(
    () => locations.find((location) => location.id === focusLocationId) ?? null,
    [focusLocationId, locations]
  );

  const trajectory = useMemo(() => {
    if (selectedEvent?.location) {
      return eventsInRange
        .filter((event) => event.id === selectedEvent.id && event.location)
        .map((event) => ({ ...event, locationObj: locationMap.get(event.location!) ?? null }));
    }

    if (!selectedRole) return [];

    return eventsInRange
      .filter((event) => event.participants.includes(selectedRole.name) && event.location)
      .sort((a, b) => (a.progressStart ?? 0) - (b.progressStart ?? 0))
      .map((event) => ({ ...event, locationObj: locationMap.get(event.location!) ?? null }));
  }, [eventsInRange, locationMap, selectedEvent, selectedRole]);

  const topLocations = useMemo(() => {
    return locations
      .map((location) => {
        const relatedEvents = eventsInRange.filter((event) => event.location === location.canonical_name).length;
        return { location, relatedEvents };
      })
      .sort((a, b) => b.relatedEvents - a.relatedEvents || b.location.total_mentions - a.location.total_mentions)
      .slice(0, 20);
  }, [eventsInRange, locations]);

  return (
    <div className="view-shell">
      <div className="view-header">
        <div>
          <h3 className="view-title">地点关系 / 迁移视图</h3>
          <p className="view-copy">
            {bookConfig?.has_geo_coordinates
              ? '当前书籍支持真实坐标，这里会优先显示迁移路径与高频地点。'
              : '这一版不依赖真实地图坐标，而是按叙事进度梳理地点流转与场域上下文。'}
          </p>
        </div>
        <div className="float-stat">{locations.length} 个地点</div>
      </div>

      {(selectedRole || selectedEvent || focusedLocation) && (
        <section className="insight-card mb-4">
          <p className="section-kicker">当前路径</p>
          <h4 className="view-title text-[1.15rem]">
            {selectedRole
              ? `${selectedRole.name} 的地点轨迹`
              : selectedEvent
                ? `${selectedEvent.name} 的地点上下文`
                : `${focusedLocation?.canonical_name} 的场域摘要`}
          </h4>

          {trajectory.length > 0 ? (
            <div className="view-grid mt-4">
              {trajectory.map((event, index) => (
                <button
                  key={`${event.id}-${index}`}
                  type="button"
                  className="detail-card text-left hover:border-[rgba(182,120,42,0.28)]"
                  onClick={() => event.locationObj && onLocationClick?.(event.locationObj)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-[var(--text-primary)]">{event.location}</div>
                      <div className="mt-1 text-sm text-[var(--text-muted)]">
                        {event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`}
                      </div>
                    </div>
                    <span className="tag-pill">{event.name}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : focusedLocation ? (
            <div className="detail-card mt-4">
              <div className="font-semibold text-[var(--text-primary)]">{focusedLocation.canonical_name}</div>
              {focusedLocation.description && <p className="detail-text mt-3">{focusedLocation.description}</p>}
              <div className="chip-wrap mt-4">
                {(focusedLocation.associated_entities ?? []).slice(0, 6).map((entity) => (
                  <span key={`${focusedLocation.id}-${entity}`} className="pill-chip">
                    {entity}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-state mt-4">当前选择没有可用的地点轨迹。</div>
          )}
        </section>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="detail-card">
          <div className="view-header">
            <div>
              <h4 className="view-title text-[1.15rem]">高频地点</h4>
              <p className="view-copy">优先挑出事件密度高、剧情承载重的场域。</p>
            </div>
          </div>
          <div className="view-grid max-h-[430px] overflow-y-auto pr-1">
            {topLocations.map(({ location, relatedEvents }) => (
              <button
                key={location.id}
                type="button"
                className={`detail-card text-left ${
                  focusLocationId === location.id ? 'border-[rgba(182,120,42,0.34)] bg-[rgba(230,194,139,0.16)]' : 'hover:border-[rgba(182,120,42,0.28)]'
                }`}
                onClick={() => onLocationClick?.(location)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-[var(--text-primary)]">{location.canonical_name}</div>
                    <div className="mt-1 text-sm text-[var(--text-muted)]">{location.location_type || '地点'}</div>
                  </div>
                  <span className="dashboard-pill">{relatedEvents} 事件</span>
                </div>
                {location.description && <p className="detail-text mt-3">{location.description}</p>}
              </button>
            ))}
          </div>
        </section>

        <section className="detail-card">
          <div className="view-header">
            <div>
              <h4 className="view-title text-[1.15rem]">使用说明</h4>
              <p className="view-copy">这一页仍然服务剧情分析，而不是地理学意义上的地图工具。</p>
            </div>
          </div>
          <div className="view-grid">
            <div className="subtle-card">
              <p className="detail-heading">角色轨迹</p>
              <p className="detail-text">当你选中某个人物后，这里会按叙事进度列出该人物涉及事件所在的地点。</p>
            </div>
            <div className="subtle-card">
              <p className="detail-heading">事件上下文</p>
              <p className="detail-text">当你选中某个事件后，这里会强化该事件地点的上下文位置，帮助你判断戏落在哪里。</p>
            </div>
            <div className="subtle-card">
              <p className="detail-heading">地点回跳</p>
              <p className="detail-text">点击左侧地点卡，可以继续进入地点详情；再从详情中跳到相关人物、事件和关系。</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
