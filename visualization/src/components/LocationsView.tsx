import { useMemo, useState } from 'react';
import type { UnifiedLocation } from '../types/unified';

interface LocationsViewProps {
  locations: UnifiedLocation[];
  onLocationClick?: (location: UnifiedLocation) => void;
}

export function LocationsView({ locations, onLocationClick }: LocationsViewProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const { withCoords, withoutCoords } = useMemo(() => {
    const withCoords: UnifiedLocation[] = [];
    const withoutCoords: UnifiedLocation[] = [];
    for (const loc of locations) {
      if (loc.coordinates) withCoords.push(loc);
      else withoutCoords.push(loc);
    }
    return { withCoords, withoutCoords };
  }, [locations]);

  const filteredLocations = useMemo(() => {
    if (!searchQuery.trim()) return locations;
    const query = searchQuery.trim().toLowerCase();
    return locations.filter((loc) => {
      if (loc.canonical_name.toLowerCase().includes(query)) return true;
      if (loc.modern_name?.toLowerCase().includes(query)) return true;
      if (loc.all_names?.some((name) => name.toLowerCase().includes(query))) return true;
      if (loc.description?.toLowerCase().includes(query)) return true;
      if (loc.original_descriptions?.some((d) => d.toLowerCase().includes(query))) return true;
      return false;
    });
  }, [locations, searchQuery]);

  return (
    <div className="view-shell">
      <div className="view-header">
        <div>
          <h3 className="view-title">地点</h3>
          <p className="view-copy">按叙事承载能力优先排列地点，先抓高频场域，再进入人物、事件和地点详情。</p>
        </div>
        <div className="view-toolbar">
          <input
            type="text"
            placeholder="搜索地点"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="search-input md:w-72"
          />
          <div className="float-stat">
            {withCoords.length} 个有坐标地点 / {withoutCoords.length} 个无坐标地点
          </div>
        </div>
      </div>

      <div className="view-grid max-h-[620px] overflow-y-auto pr-1">
        {filteredLocations.map((loc) => (
          <button
            key={loc.id}
            type="button"
            className="detail-card text-left hover:border-[var(--accent-deep)]"
            onClick={() => onLocationClick?.(loc)}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-[var(--accent-deep)]">{loc.canonical_name}</div>
                {loc.modern_name && (
                  <div className="mt-1 text-sm text-[var(--text-muted)]">现代地名：{loc.modern_name}</div>
                )}
              </div>
              <div className="chip-wrap">
                {loc.location_type && <span className="pill-chip pill-chip--strong">{loc.location_type}</span>}
              </div>
            </div>

            {loc.description && <p className="detail-text mt-3">{loc.description}</p>}

            <div className="dashboard-meta-row mt-4">
              <span className="dashboard-pill">关联人物 {loc.associated_entities?.length ?? 0}</span>
              <span className="dashboard-pill">关联事件 {loc.associated_events?.length ?? 0}</span>
              <span className="dashboard-pill">总提及 {loc.total_mentions}</span>
            </div>

            {(loc.associated_entities?.length ?? 0) > 0 && (
              <div className="chip-wrap mt-4">
                {loc.associated_entities.slice(0, 5).map((name) => (
                  <span key={`${loc.id}-${name}`} className="pill-chip">
                    {name}
                  </span>
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
