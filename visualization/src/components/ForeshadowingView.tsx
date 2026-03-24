import { useMemo, useState } from 'react';
import type { WriterForeshadowingThread } from '../types/writerInsights';

interface ForeshadowingViewProps {
  threads: WriterForeshadowingThread[];
  onRoleClick?: (roleName: string) => void;
  onEventClick?: (eventId: string) => void;
}

export function ForeshadowingView({ threads, onRoleClick, onEventClick }: ForeshadowingViewProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredThreads = useMemo(() => {
    if (!searchQuery.trim()) return threads;
    const query = searchQuery.trim().toLowerCase();
    return threads.filter((thread) => {
      if (thread.label.toLowerCase().includes(query)) return true;
      if (thread.focus_roles.some((role) => role.toLowerCase().includes(query))) return true;
      if (thread.motif_keywords.some((keyword) => keyword.toLowerCase().includes(query))) return true;
      return false;
    });
  }, [searchQuery, threads]);

  return (
    <div className="bg-white rounded-lg shadow-md p-4 flex flex-col gap-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-[#2c1810]">伏笔回收</h3>
          <p className="text-sm text-gray-500">轻量梳理前三季里“前段埋线，后段兑现”的显式结构。</p>
        </div>
        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="搜索伏笔主题或角色..."
          className="w-full md:w-72 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
        />
      </div>

      <div className="space-y-4">
        {filteredThreads.map((thread) => (
          <article key={thread.id} className="rounded-2xl border border-[#eadfd2] bg-[#fffdfb] p-4">
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
              <div>
                <h4 className="text-lg font-bold text-[#8b4513]">{thread.label}</h4>
                <p className="mt-2 text-sm text-gray-700">{thread.summary}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {thread.focus_roles.map((role) => (
                    <button
                      key={role}
                      onClick={() => onRoleClick?.(role)}
                      className="px-2 py-1 rounded-full bg-[#8b4513] text-white text-sm hover:bg-[#6e360f]"
                    >
                      {role}
                    </button>
                  ))}
                </div>
              </div>
              <div className="text-right text-xs text-gray-500">
                <div>
                  章节 {thread.unit_span[0] ?? '—'} - {thread.unit_span[1] ?? '—'}
                </div>
                <div>
                  进度 {thread.progress_span[0] ?? '—'} - {thread.progress_span[1] ?? '—'}
                </div>
                <div className="mt-2 flex flex-wrap justify-end gap-2">
                  {thread.motif_keywords.map((keyword) => (
                    <span key={keyword} className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
              <section className="rounded-xl bg-[#faf8f5] p-3">
                <div className="text-sm font-semibold text-[#2c1810] mb-3">前段埋线</div>
                <div className="space-y-2">
                  {thread.clue_events.map((event) => (
                    <button
                      key={event.event_id}
                      onClick={() => onEventClick?.(event.event_id)}
                      className="w-full text-left rounded-xl border border-[#eadfd2] bg-white p-3 hover:bg-[#fff7ed] hover:border-[#c18a59] transition-colors"
                    >
                      <div className="font-medium text-[#5d2e0c]">{event.name}</div>
                      <div className="mt-1 text-xs text-gray-500">
                        {event.season_name ?? '当前范围'} · 章节 {event.unit_index ?? '—'}
                        {event.location ? ` · ${event.location}` : ''}
                      </div>
                      <p className="mt-1 text-sm text-gray-600 line-clamp-2">{event.significance || event.description}</p>
                    </button>
                  ))}
                </div>
              </section>

              <section className="rounded-xl bg-[#faf8f5] p-3">
                <div className="text-sm font-semibold text-[#2c1810] mb-3">后段兑现</div>
                <div className="space-y-2">
                  {thread.payoff_events.map((event) => (
                    <button
                      key={event.event_id}
                      onClick={() => onEventClick?.(event.event_id)}
                      className="w-full text-left rounded-xl border border-[#eadfd2] bg-white p-3 hover:bg-[#fff7ed] hover:border-[#c18a59] transition-colors"
                    >
                      <div className="font-medium text-[#5d2e0c]">{event.name}</div>
                      <div className="mt-1 text-xs text-gray-500">
                        {event.season_name ?? '当前范围'} · 章节 {event.unit_index ?? '—'}
                        {event.location ? ` · ${event.location}` : ''}
                      </div>
                      <p className="mt-1 text-sm text-gray-600 line-clamp-2">{event.significance || event.description}</p>
                    </button>
                  ))}
                </div>
              </section>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
