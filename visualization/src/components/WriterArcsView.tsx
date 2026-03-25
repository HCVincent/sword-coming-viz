import { useMemo, useState } from 'react';
import type {
  WriterCharacterArc,
  WriterCuratedRelationship,
  WriterInsightEventRef,
  WriterSeasonOverview,
} from '../types/writerInsights';

interface WriterArcsViewProps {
  seasonOverviews: WriterSeasonOverview[];
  arcs: WriterCharacterArc[];
  curatedRelationships: WriterCuratedRelationship[];
  selectedRoleId?: string | null;
  spotlightRoleName?: string | null;
  onRoleClick?: (roleName: string) => void;
  onEventClick?: (eventId: string) => void;
  onLocationClick?: (locationName: string) => void;
  onRelationClick?: (sourceId: string, targetId: string) => void;
}

function joinNames(items: string[], fallback = '待补充'): string {
  return items.length > 0 ? items.join('、') : fallback;
}

function renderEventMeta(event: WriterInsightEventRef): string {
  const parts = [event.season_name ?? '当前范围', `章节 ${event.unit_index ?? '—'}`];
  if (event.location) {
    parts.push(event.location);
  }
  return parts.join(' · ');
}

export function WriterArcsView({
  seasonOverviews,
  arcs,
  curatedRelationships,
  selectedRoleId,
  spotlightRoleName,
  onRoleClick,
  onEventClick,
  onLocationClick,
  onRelationClick,
}: WriterArcsViewProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const spotlightArc = useMemo(
    () => arcs.find((arc) => arc.spotlight || (spotlightRoleName ? arc.role_name === spotlightRoleName : false)) ?? null,
    [arcs, spotlightRoleName]
  );

  const spotlightRelationships = useMemo(() => {
    const spotlightName = spotlightArc?.role_name ?? spotlightRoleName ?? null;
    if (!spotlightName) {
      return curatedRelationships.slice(0, 6);
    }
    return curatedRelationships
      .filter(
        (relationship) =>
          relationship.source_role_name === spotlightName || relationship.target_role_name === spotlightName
      )
      .slice(0, 6);
  }, [curatedRelationships, spotlightArc?.role_name, spotlightRoleName]);

  const filteredArcs = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return arcs;
    }
    return arcs.filter((arc) => {
      if (arc.role_name.toLowerCase().includes(query)) return true;
      if (arc.summary.toLowerCase().includes(query)) return true;
      if (arc.key_locations.some((location) => location.toLowerCase().includes(query))) return true;
      if (arc.relationship_phases.some((phase) => phase.counterpart_name.toLowerCase().includes(query))) return true;
      return false;
    });
  }, [arcs, searchQuery]);

  return (
    <div className="bg-white rounded-lg shadow-md p-4 flex flex-col gap-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-[#2c1810]">角色弧光</h3>
          <p className="text-sm text-gray-500">按季整理角色出场、关系变化、关键事件与地点迁移。</p>
        </div>
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="搜索角色、地点或关系..."
          className="w-full md:w-72 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
        />
      </div>

      {spotlightArc && (
        <section className="rounded-2xl border border-[#c18a59] bg-gradient-to-br from-[#fff9ef] to-[#fff3e0] p-4">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div>
              <div className="text-xs font-semibold tracking-wide text-[#8b4513]">主角主线速览</div>
              <button
                onClick={() => onRoleClick?.(spotlightArc.role_name)}
                className="mt-1 text-2xl font-bold text-[#5d2e0c] hover:underline"
              >
                {spotlightArc.role_name}
              </button>
              <p className="mt-3 text-sm text-gray-700">{spotlightArc.summary}</p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm text-[#5d2e0c]">
              <div className="rounded-xl bg-white/80 p-3">
                <div className="text-xs text-gray-500">关键地点</div>
                <div className="mt-1 font-semibold">{joinNames(spotlightArc.key_locations.slice(0, 3))}</div>
              </div>
              <div className="rounded-xl bg-white/80 p-3">
                <div className="text-xs text-gray-500">关系重心</div>
                <div className="mt-1 font-semibold">
                  {joinNames(spotlightArc.relationship_phases.slice(0, 3).map((phase) => phase.counterpart_name))}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {seasonOverviews.length > 0 && (
        <section className="rounded-2xl border border-[#eadfd2] bg-[#fffdfb] p-4">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h4 className="text-lg font-bold text-[#2c1810]">分季总览</h4>
              <p className="text-sm text-gray-500">先看每一季该抓哪条线，再进入具体角色和关系卡。</p>
            </div>
            <div className="text-xs text-gray-500">当前命中 {seasonOverviews.length} 个季别卡片</div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            {seasonOverviews.map((overview) => (
              <article key={overview.season_name} className="rounded-2xl border border-[#eadfd2] bg-[#faf8f5] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h5 className="text-lg font-bold text-[#8b4513]">{overview.season_name}</h5>
                    <div className="mt-1 text-xs text-gray-500">
                      章节 {overview.unit_range[0]} - {overview.unit_range[1]} · 进度 {overview.progress_range[0]} -{' '}
                      {overview.progress_range[1]}
                    </div>
                  </div>
                  <span className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513] text-xs">主线总览</span>
                </div>

                <p className="mt-3 text-sm text-gray-700">{overview.summary}</p>
                {overview.spotlight_summary && (
                  <p className="mt-2 text-sm text-[#5d2e0c] bg-white rounded-xl p-3">{overview.spotlight_summary}</p>
                )}

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">三拍结构</div>
                  <div className="space-y-2">
                    {overview.story_beats.length > 0 ? (
                      overview.story_beats.map((beat) => (
                        <div
                          key={`${overview.season_name}-${beat.beat_type}`}
                          className="rounded-xl bg-white p-3 border border-[#eadfd2]"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="px-2 py-1 rounded-full bg-[#8b4513] text-white text-xs">
                              {beat.label}
                            </span>
                            {beat.event?.event_type && (
                              <span className="text-xs px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                                {beat.event.event_type}
                              </span>
                            )}
                          </div>
                          {beat.event ? (
                            <button
                              onClick={() => onEventClick?.(beat.event!.event_id)}
                              className="mt-2 text-left font-medium text-[#5d2e0c] hover:underline"
                            >
                              {beat.event.name}
                            </button>
                          ) : (
                            <div className="mt-2 font-medium text-gray-400">待补充季别锚点</div>
                          )}
                          {beat.event && <div className="mt-1 text-xs text-gray-500">{renderEventMeta(beat.event)}</div>}
                          <p className="mt-2 text-sm text-gray-700">{beat.summary}</p>
                        </div>
                      ))
                    ) : (
                      <div className="text-sm text-gray-400">当前范围暂无可用的三拍结构。</div>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">本季必保留戏</div>
                  <div className="space-y-2">
                    {overview.must_keep_scenes.length > 0 ? (
                      overview.must_keep_scenes.map((scene) => (
                        <div key={scene.scene_id} className="rounded-xl bg-white p-3 border border-[#eadfd2]">
                          <div className="flex items-center justify-between gap-3">
                            <span className="px-2 py-1 rounded-full bg-[#5d2e0c] text-white text-xs">
                              {scene.label}
                            </span>
                            {scene.event?.event_type && (
                              <span className="text-xs px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                                {scene.event.event_type}
                              </span>
                            )}
                          </div>
                          {scene.event ? (
                            <button
                              onClick={() => onEventClick?.(scene.event!.event_id)}
                              className="mt-2 text-left font-medium text-[#5d2e0c] hover:underline"
                            >
                              {scene.event.name}
                            </button>
                          ) : (
                            <div className="mt-2 font-medium text-gray-400">待补充场景锚点</div>
                          )}
                          {scene.focus_roles.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {scene.focus_roles.map((roleName) => (
                                <button
                                  key={`${scene.scene_id}-${roleName}`}
                                  onClick={() => onRoleClick?.(roleName)}
                                  className="px-2 py-1 rounded-full border border-[#d4c5b5] bg-[#faf8f5] text-xs text-[#5d2e0c] hover:bg-[#f3e7d8]"
                                >
                                  {roleName}
                                </button>
                              ))}
                            </div>
                          )}
                          {scene.related_relationship_titles.length > 0 && (
                            <div className="mt-2 text-xs text-[#8b4513]">
                              关联关系：{scene.related_relationship_titles.join('、')}
                            </div>
                          )}
                          <p className="mt-2 text-sm text-gray-700">{scene.adaptation_reason}</p>
                        </div>
                      ))
                    ) : (
                      <div className="text-sm text-gray-400">当前范围暂无整理好的必保留戏。</div>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">改编抓手</div>
                  <div className="space-y-2">
                    {overview.adaptation_hooks.map((hook, index) => (
                      <div
                        key={`${overview.season_name}-hook-${index}`}
                        className="rounded-xl bg-white p-3 border border-[#eadfd2]"
                      >
                        <p className="text-sm text-gray-700">{hook}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">角色出场密度</div>
                  <div className="space-y-2">
                    {overview.top_roles.slice(0, 4).map((role) => (
                      <div key={role.role_id} className="rounded-xl bg-white p-3 border border-[#eadfd2]">
                        <div className="flex items-center justify-between gap-3">
                          <button
                            onClick={() => onRoleClick?.(role.role_name)}
                            className="font-medium text-[#8b4513] hover:underline"
                          >
                            {role.role_name}
                          </button>
                          <span className="text-xs px-2 py-1 rounded-full bg-[#d4a574] text-white">
                            密度 {role.density_score}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          出场章节 {role.unit_appearance_count} · 事件 {role.event_count} · 关系 {role.relation_count}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">优先关系</div>
                  <div className="flex flex-wrap gap-2">
                    {overview.priority_relationships.length > 0 ? (
                      overview.priority_relationships.map((relationship) => (
                        <button
                          key={relationship.relationship_id}
                          onClick={() => {
                            const curated = curatedRelationships.find((item) => item.id === relationship.relationship_id);
                            if (curated) {
                              onRelationClick?.(curated.source_role_id, curated.target_role_id);
                            }
                          }}
                          className="px-2 py-1 rounded-full border border-[#d4c5b5] bg-white text-sm text-[#5d2e0c] hover:bg-[#f3e7d8]"
                        >
                          {relationship.title}
                        </button>
                      ))
                    ) : (
                      <span className="text-sm text-gray-400">当前范围暂无优先关系卡。</span>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">主要冲突</div>
                  <div className="flex flex-wrap gap-2">
                    {overview.main_conflicts.length > 0 ? (
                      overview.main_conflicts.map((conflict) => (
                        <button
                          key={conflict.chain_id}
                          onClick={() => {
                            const relationship = curatedRelationships.find(
                              (item) =>
                                (item.source_role_name === conflict.source_role_name &&
                                  item.target_role_name === conflict.target_role_name) ||
                                (item.source_role_name === conflict.target_role_name &&
                                  item.target_role_name === conflict.source_role_name)
                            );
                            if (relationship) {
                              onRelationClick?.(relationship.source_role_id, relationship.target_role_id);
                            }
                          }}
                          className="px-2 py-1 rounded-full border border-[#d4c5b5] bg-white text-sm text-[#5d2e0c] hover:bg-[#f3e7d8]"
                        >
                          {conflict.title}
                        </button>
                      ))
                    ) : (
                      <span className="text-sm text-gray-400">当前范围暂无明确主线冲突卡片。</span>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">锚点事件</div>
                  <div className="space-y-2">
                    {overview.anchor_events.length > 0 ? (
                      overview.anchor_events.slice(0, 3).map((event) => (
                        <div key={event.event_id} className="rounded-xl bg-white p-3 border border-[#eadfd2]">
                          <div className="flex items-center justify-between gap-3">
                            <button
                              onClick={() => onEventClick?.(event.event_id)}
                              className="text-left font-medium text-[#5d2e0c] hover:underline"
                            >
                              {event.name}
                            </button>
                            <span className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513] text-xs">
                              {event.event_type}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-gray-500">{renderEventMeta(event)}</div>
                          <p className="mt-2 text-sm text-gray-700">{event.significance || event.description}</p>
                        </div>
                      ))
                    ) : (
                      <div className="text-sm text-gray-400">当前范围暂无可用锚点事件。</div>
                    )}
                  </div>
                </div>

                <div className="mt-4">
                  <div className="text-sm font-semibold text-[#2c1810] mb-2">高频场域</div>
                  <div className="flex flex-wrap gap-2">
                    {overview.top_locations.length > 0 ? (
                      overview.top_locations.map((location) => (
                        <button
                          key={location.location_name}
                          onClick={() => onLocationClick?.(location.location_name)}
                          className="px-2 py-1 rounded-full border border-[#d4c5b5] bg-white text-sm text-[#5d2e0c] hover:bg-[#f3e7d8]"
                        >
                          {location.location_name} · {location.event_count}
                        </button>
                      ))
                    ) : (
                      <span className="text-sm text-gray-400">当前范围暂无高频地点。</span>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {spotlightRelationships.length > 0 && (
        <section className="rounded-2xl border border-[#eadfd2] bg-[#fffdfb] p-4">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h4 className="text-lg font-bold text-[#2c1810]">主线关系校订</h4>
              <p className="text-sm text-gray-500">
                把主角线优先整理成可直接参考的关系卡，减少在原始冲突链里来回翻找。
              </p>
            </div>
            <div className="text-xs text-gray-500">已校订 {spotlightRelationships.length} 条核心关系</div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {spotlightRelationships.map((relationship) => (
              <article key={relationship.id} className="rounded-2xl border border-[#eadfd2] bg-[#faf8f5] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h5 className="text-lg font-bold text-[#8b4513]">{relationship.title}</h5>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                      <button
                        onClick={() => onRoleClick?.(relationship.source_role_name)}
                        className="text-[#5d2e0c] hover:underline"
                      >
                        {relationship.source_role_name}
                      </button>
                      <span className="text-gray-400">×</span>
                      <button
                        onClick={() => onRoleClick?.(relationship.target_role_name)}
                        className="text-[#5d2e0c] hover:underline"
                      >
                        {relationship.target_role_name}
                      </button>
                      <span className="px-2 py-1 rounded-full bg-[#8b4513] text-white text-xs">
                        {relationship.kind}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => onRelationClick?.(relationship.source_role_id, relationship.target_role_id)}
                    className="px-3 py-2 rounded-lg bg-[#8b4513] text-white text-sm hover:bg-[#6e360f] transition-colors"
                  >
                    看关系网
                  </button>
                </div>

                <p className="mt-3 text-sm text-gray-700">{relationship.summary}</p>
                <p className="mt-2 text-sm text-[#5d2e0c] bg-white rounded-xl p-3">{relationship.adaptation_value}</p>

                <div className="mt-4 flex flex-wrap gap-2">
                  {relationship.phase_labels.map((phase) => (
                    <span
                      key={`${relationship.id}-${phase}`}
                      className="px-2 py-1 rounded-full bg-[#d4a574] text-white text-xs"
                    >
                      {phase}
                    </span>
                  ))}
                </div>

                {relationship.manual_beats.length > 0 && (
                  <div className="mt-4">
                    <div className="text-sm font-semibold text-[#2c1810] mb-2">人工节拍</div>
                    <div className="space-y-2">
                      {relationship.manual_beats.map((beat, index) => (
                        <div key={`${relationship.id}-beat-${index}`} className="rounded-xl border border-[#eadfd2] bg-white p-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513] text-xs">
                                {beat.season_name ?? '当前范围'}
                              </span>
                              <span className="px-2 py-1 rounded-full bg-[#d4a574] text-white text-xs">
                                {beat.phase_label}
                              </span>
                            </div>
                            {beat.location && (
                              <button
                                onClick={() => onLocationClick?.(beat.location!)}
                                className="text-xs text-[#8b4513] hover:underline"
                              >
                                {beat.location}
                              </button>
                            )}
                          </div>
                          <p className="mt-2 text-sm text-gray-700">{beat.summary}</p>
                          {beat.event_id && beat.event_name && (
                            <button
                              onClick={() => onEventClick?.(beat.event_id!)}
                              className="mt-2 text-sm text-[#8b4513] hover:underline"
                            >
                              回链事件：{beat.event_name}
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  {relationship.key_locations.map((location) => (
                    <button
                      key={`${relationship.id}-${location}`}
                      onClick={() => onLocationClick?.(location)}
                      className="px-2 py-1 rounded-full border border-[#d4c5b5] bg-white text-sm text-[#5d2e0c] hover:bg-[#f3e7d8]"
                    >
                      {location}
                    </button>
                  ))}
                </div>

                <div className="mt-4 space-y-2">
                  {relationship.key_events.slice(0, 3).map((event) => (
                    <button
                      key={event.event_id}
                      onClick={() => onEventClick?.(event.event_id)}
                      className="w-full text-left rounded-xl border border-[#eadfd2] bg-white p-3 hover:bg-[#fff7ed] hover:border-[#c18a59] transition-colors"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium text-[#5d2e0c]">{event.name}</span>
                        <span className="text-xs px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                          {event.season_name ?? '当前范围'}
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-gray-600 line-clamp-2">
                        {event.significance || event.description}
                      </p>
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {filteredArcs.map((arc) => (
          <article
            key={arc.role_id}
            className={`rounded-2xl border p-4 transition-colors ${
              selectedRoleId === arc.role_id ? 'border-[#8b4513] bg-[#fff9f2] shadow-lg' : 'border-[#eadfd2] bg-[#fffdfb]'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <button
                  onClick={() => onRoleClick?.(arc.role_name)}
                  className="text-left text-xl font-bold text-[#8b4513] hover:underline"
                >
                  {arc.role_name}
                </button>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {arc.primary_power && (
                    <span className="px-2 py-1 rounded-full bg-[#8b4513] text-white">{arc.primary_power}</span>
                  )}
                  {arc.season_names.map((season) => (
                    <span key={season} className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                      {season}
                    </span>
                  ))}
                </div>
              </div>
              <div className="text-right text-xs text-gray-500">
                <div>
                  章节 {arc.unit_span[0] ?? '—'} - {arc.unit_span[1] ?? '—'}
                </div>
                <div>
                  进度 {arc.progress_span[0] ?? '—'} - {arc.progress_span[1] ?? '—'}
                </div>
              </div>
            </div>

            <p className="mt-3 text-sm text-gray-700">{arc.summary}</p>

            <div className="mt-4">
              <div className="text-sm font-semibold text-[#2c1810] mb-2">关键地点</div>
              <div className="flex flex-wrap gap-2">
                {arc.key_locations.length > 0 ? (
                  arc.key_locations.map((location) => (
                    <button
                      key={location}
                      onClick={() => onLocationClick?.(location)}
                      className="px-2 py-1 rounded-full border border-[#d4c5b5] bg-[#faf8f5] text-sm text-[#5d2e0c] hover:bg-[#f3e7d8]"
                    >
                      {location}
                    </button>
                  ))
                ) : (
                  <span className="text-sm text-gray-400">当前范围暂无重点地点。</span>
                )}
              </div>
            </div>

            <div className="mt-4">
              <div className="text-sm font-semibold text-[#2c1810] mb-2">关键事件</div>
              <div className="space-y-2">
                {arc.key_events.slice(0, 6).map((event) => (
                  <button
                    key={event.event_id}
                    onClick={() => onEventClick?.(event.event_id)}
                    className="w-full text-left p-3 rounded-xl border border-[#eadfd2] hover:border-[#c18a59] hover:bg-[#fff8ef] transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-[#5d2e0c]">{event.name}</span>
                      <span className="text-xs px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                        {event.event_type}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">{renderEventMeta(event)}</div>
                    <p className="mt-1 text-sm text-gray-600 line-clamp-2">{event.significance || event.description}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-4">
              <div className="text-sm font-semibold text-[#2c1810] mb-2">关系变化</div>
              <div className="space-y-2">
                {arc.relationship_phases.slice(0, 6).map((phase) => (
                  <div
                    key={`${phase.relation_id}-${phase.phase_label}-${phase.unit_index}`}
                    className="rounded-xl bg-[#faf8f5] p-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <button
                        onClick={() => onRoleClick?.(phase.counterpart_name)}
                        className="font-medium text-[#8b4513] hover:underline"
                      >
                        {phase.counterpart_name}
                      </button>
                      <span className="text-xs px-2 py-1 rounded-full bg-[#d4a574] text-white">
                        {phase.phase_label}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      章节 {phase.unit_index ?? '—'}
                      {phase.location ? ` · ${phase.location}` : ''}
                    </div>
                    <p className="mt-1 text-sm text-gray-600">{phase.summary}</p>
                  </div>
                ))}
                {arc.relationship_phases.length === 0 && (
                  <div className="text-sm text-gray-400">当前范围暂无可解释的阶段性关系变化。</div>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
