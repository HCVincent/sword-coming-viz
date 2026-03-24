import { useMemo } from 'react';
import type { BookConfig } from '../types/pipelineArtifacts';
import type { TimelineEventUnified, RoleNodeUnified, UnifiedLocation } from '../types/unified';

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
    <div className="bg-white rounded-lg shadow-md p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-[#2c1810]">地点关系 / 迁移视图</h3>
          <p className="text-sm text-gray-500">
            {bookConfig?.has_geo_coordinates ? '当前书籍支持真实坐标。' : '当前首版不依赖真实地图坐标，按叙事进度展示地点流转。'}
          </p>
        </div>
        <div className="text-sm text-gray-500">{locations.length} 个地点</div>
      </div>

      {(selectedRole || selectedEvent || focusedLocation) && (
        <div className="rounded-lg border border-[#d4c5b5] bg-[#faf8f5] p-4">
          <div className="text-sm font-semibold text-[#8b4513] mb-2">
            {selectedRole
              ? `${selectedRole.name} 的地点轨迹`
              : selectedEvent
                ? `${selectedEvent.name} 的地点上下文`
                : `${focusedLocation?.canonical_name} 的地点详情`}
          </div>

          {trajectory.length > 0 ? (
            <div className="space-y-3">
              {trajectory.map((event, index) => (
                <button
                  key={`${event.id}-${index}`}
                  onClick={() => event.locationObj && onLocationClick?.(event.locationObj)}
                  className="w-full text-left rounded-lg border border-[#d4c5b5] bg-white p-3 hover:border-[#8b4513] transition-colors"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-[#2c1810]">{event.location}</div>
                      <div className="text-sm text-gray-500">{event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`}</div>
                    </div>
                    <div className="text-xs text-[#8b4513]">{event.name}</div>
                  </div>
                </button>
              ))}
            </div>
          ) : focusedLocation ? (
            <div className="text-sm text-gray-700">
              <div className="font-medium text-[#2c1810]">{focusedLocation.canonical_name}</div>
              {focusedLocation.description && <p className="mt-2">{focusedLocation.description}</p>}
              <p className="mt-2 text-gray-500">相关实体：{focusedLocation.associated_entities?.join('、') || '暂无'}</p>
            </div>
          ) : (
            <div className="text-sm text-gray-500">当前选择没有可用的地点轨迹。</div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="rounded-lg border border-[#d4c5b5] p-4">
          <h4 className="font-semibold text-[#8b4513] mb-3">高频地点</h4>
          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {topLocations.map(({ location, relatedEvents }) => (
              <button
                key={location.id}
                onClick={() => onLocationClick?.(location)}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  focusLocationId === location.id
                    ? 'border-[#8b4513] bg-[#faf8f5]'
                    : 'border-[#d4c5b5] hover:border-[#8b4513]'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-[#2c1810]">{location.canonical_name}</div>
                    <div className="text-xs text-gray-500 mt-1">{location.location_type || '地点'}</div>
                    {location.description && <p className="text-sm text-gray-600 mt-2 line-clamp-2">{location.description}</p>}
                  </div>
                  <div className="text-xs text-[#8b4513] whitespace-nowrap">{relatedEvents} 事件</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-[#d4c5b5] p-4">
          <h4 className="font-semibold text-[#8b4513] mb-3">地点迁移提示</h4>
          <div className="space-y-3 text-sm text-gray-700">
            <p>选中人物后，这里会按叙事进度列出其相关事件所在地点。</p>
            <p>选中事件后，这里会强调该事件的地点和相邻地点上下文。</p>
            <p>首版先服务剧情分析，不使用 OpenStreetMap 或真实经纬度。</p>
          </div>
        </div>
      </div>
    </div>
  );
}
