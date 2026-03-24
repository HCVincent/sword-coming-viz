import { useMemo, useState } from 'react';
import type { WriterConflictChain, WriterCuratedRelationship } from '../types/writerInsights';

interface ConflictChainsViewProps {
  curatedRelationships: WriterCuratedRelationship[];
  chains: WriterConflictChain[];
  spotlightRoleName?: string | null;
  onRoleClick?: (roleName: string) => void;
  onEventClick?: (eventId: string) => void;
  onRelationClick?: (sourceId: string, targetId: string) => void;
}

export function ConflictChainsView({
  curatedRelationships,
  chains,
  spotlightRoleName,
  onRoleClick,
  onEventClick,
  onRelationClick,
}: ConflictChainsViewProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [spotlightOnly, setSpotlightOnly] = useState(Boolean(spotlightRoleName));
  const visibleCuratedRelationships = useMemo(() => {
    return curatedRelationships.filter((relationship) => {
      if (
        spotlightOnly &&
        spotlightRoleName &&
        relationship.source_role_name !== spotlightRoleName &&
        relationship.target_role_name !== spotlightRoleName &&
        !relationship.spotlight
      ) {
        return false;
      }
      return true;
    });
  }, [curatedRelationships, spotlightOnly, spotlightRoleName]);

  const filteredChains = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return chains.filter((chain) => {
      if (
        spotlightOnly &&
        spotlightRoleName &&
        chain.source_role_name !== spotlightRoleName &&
        chain.target_role_name !== spotlightRoleName &&
        !chain.spotlight
      ) {
        return false;
      }
      if (!query) return true;
      if (chain.title.toLowerCase().includes(query)) return true;
      if (chain.source_role_name.toLowerCase().includes(query)) return true;
      if (chain.target_role_name.toLowerCase().includes(query)) return true;
      if (chain.locations.some((location) => location.toLowerCase().includes(query))) return true;
      return false;
    });
  }, [chains, searchQuery, spotlightOnly, spotlightRoleName]);

  return (
    <div className="bg-white rounded-lg shadow-md p-4 flex flex-col gap-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-[#2c1810]">冲突链</h3>
          <p className="text-sm text-gray-500">把关系变化拆成可改编的阶段节拍，便于判断戏剧张力和转折位置。</p>
        </div>
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="搜索角色、地点或冲突..."
          className="w-full md:w-72 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
        />
      </div>

      {spotlightRoleName && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setSpotlightOnly(true)}
            className={`px-3 py-2 rounded-full text-sm transition-colors ${
              spotlightOnly ? 'bg-[#8b4513] text-white' : 'bg-[#f4ede4] text-[#8b4513]'
            }`}
          >
            仅看{spotlightRoleName}相关
          </button>
          <button
            onClick={() => setSpotlightOnly(false)}
            className={`px-3 py-2 rounded-full text-sm transition-colors ${
              !spotlightOnly ? 'bg-[#8b4513] text-white' : 'bg-[#f4ede4] text-[#8b4513]'
            }`}
          >
            查看全部冲突链
          </button>
        </div>
      )}

      {visibleCuratedRelationships.length > 0 && (
        <section className="rounded-2xl border border-[#eadfd2] bg-[#fffdfb] p-4">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h4 className="text-lg font-bold text-[#2c1810]">人工校订主线</h4>
              <p className="text-sm text-gray-500">优先把最值得改编强化的关系线单独摘出来，再回头看下面的原始冲突链细节。</p>
            </div>
            <div className="text-xs text-gray-500">当前显示 {visibleCuratedRelationships.length} 条校订关系</div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {visibleCuratedRelationships.map((relationship) => (
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
                      <span className="text-gray-400">vs</span>
                      <button
                        onClick={() => onRoleClick?.(relationship.target_role_name)}
                        className="text-[#5d2e0c] hover:underline"
                      >
                        {relationship.target_role_name}
                      </button>
                      <span className="px-2 py-1 rounded-full bg-[#8b4513] text-white text-xs">{relationship.kind}</span>
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
                    <span key={`${relationship.id}-${phase}`} className="px-2 py-1 rounded-full bg-[#d4a574] text-white text-xs">
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
                            {beat.location && <span className="text-xs text-gray-500">{beat.location}</span>}
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
                      <p className="mt-1 text-sm text-gray-600 line-clamp-2">{event.significance || event.description}</p>
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <div className="space-y-4">
        {filteredChains.map((chain) => (
          <article key={chain.id} className="rounded-2xl border border-[#eadfd2] bg-[#fffdfb] p-4">
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
              <div>
                <h4 className="text-lg font-bold text-[#8b4513]">{chain.title}</h4>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button onClick={() => onRoleClick?.(chain.source_role_name)} className="text-sm hover:underline text-[#5d2e0c]">
                    {chain.source_role_name}
                  </button>
                  <span className="text-gray-400">vs</span>
                  <button onClick={() => onRoleClick?.(chain.target_role_name)} className="text-sm hover:underline text-[#5d2e0c]">
                    {chain.target_role_name}
                  </button>
                  <span className="px-2 py-1 rounded-full bg-[#8b4513] text-white text-xs">{chain.conflict_type}</span>
                  <span className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513] text-xs">张力 {chain.tension_score}/10</span>
                </div>
                <p className="mt-3 text-sm text-gray-700">{chain.summary}</p>
              </div>

              <div className="text-right text-xs text-gray-500">
                <div>
                  章节 {chain.unit_span[0] ?? '—'} - {chain.unit_span[1] ?? '—'}
                </div>
                <div>
                  进度 {chain.progress_span[0] ?? '—'} - {chain.progress_span[1] ?? '—'}
                </div>
                <div className="mt-2 flex flex-wrap justify-end gap-2">
                  {chain.season_names.map((season) => (
                    <span key={season} className="px-2 py-1 rounded-full bg-[#faf1e4] text-[#8b4513]">
                      {season}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {chain.locations.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {chain.locations.map((location) => (
                  <span key={location} className="px-2 py-1 rounded-full border border-[#d4c5b5] text-sm text-[#5d2e0c]">
                    {location}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-3">
              {chain.beats.map((beat) => (
                <button
                  key={`${chain.id}-${beat.event_id}-${beat.phase_label}`}
                  onClick={() => onEventClick?.(beat.event_id)}
                  className="text-left rounded-xl border border-[#eadfd2] bg-[#faf8f5] p-3 hover:bg-[#fff7ed] hover:border-[#c18a59] transition-colors"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-[#5d2e0c]">{beat.event_name}</span>
                    <span className="px-2 py-1 rounded-full bg-[#d4a574] text-white text-xs">{beat.phase_label}</span>
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    {beat.season_name ?? '当前范围'} · 章节 {beat.unit_index ?? '—'}
                    {beat.location ? ` · ${beat.location}` : ''}
                  </div>
                  <p className="mt-1 text-sm text-gray-600 line-clamp-2">{beat.summary}</p>
                </button>
              ))}
            </div>

            <div className="mt-4 flex justify-end">
              <button
                onClick={() => onRelationClick?.(chain.source_role_id, chain.target_role_id)}
                className="px-3 py-2 rounded-lg bg-[#8b4513] text-white text-sm hover:bg-[#6e360f] transition-colors"
              >
                在关系网中查看
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
