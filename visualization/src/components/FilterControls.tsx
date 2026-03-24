import type { KeyboardEvent } from 'react';
import type { BookConfig } from '../types/pipelineArtifacts';

interface FilterControlsProps {
  bookConfig: BookConfig | null;
  unitRange: [number, number];
  onUnitRangeChange: (range: [number, number]) => void;
  onUnitRangeCommit: (range: [number, number]) => void;
  maxUnit: number;
  progressRange: [number | null, number | null];
  onProgressRangeChange: (range: [number | null, number | null]) => void;
  onProgressRangeCommit: (range: [number | null, number | null]) => void;
  syncUnitProgress: boolean;
  syncAvailable: boolean;
  onSyncUnitProgressChange: (enabled: boolean) => void;
}

export function FilterControls({
  bookConfig,
  unitRange,
  onUnitRangeChange,
  onUnitRangeCommit,
  maxUnit,
  progressRange,
  onProgressRangeChange,
  onProgressRangeCommit,
  syncUnitProgress,
  syncAvailable,
  onSyncUnitProgressChange,
}: FilterControlsProps) {
  const unitLabel = bookConfig?.unit_label ?? '章节';
  const progressLabel = bookConfig?.progress_label ?? '叙事进度';

  const commitUnitOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      onUnitRangeCommit(unitRange);
    }
  };

  const commitProgressOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      onProgressRangeCommit(progressRange);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      <h3 className="text-lg font-bold text-[#2c1810] mb-4">筛选控制</h3>

      <div className="mb-6">
        <label className="flex items-center gap-2 text-sm text-[#2c1810]">
          <input
            type="checkbox"
            checked={syncUnitProgress}
            disabled={!syncAvailable}
            onChange={(e) => onSyncUnitProgressChange(e.target.checked)}
            className="accent-[#8b4513]"
          />
          <span className={!syncAvailable ? 'text-gray-400' : undefined}>
            {unitLabel}↔{progressLabel}联动
          </span>
        </label>
        {!syncAvailable && (
          <p className="text-xs text-gray-400 mt-1">缺少 /data/unit_progress_index.json，联动不可用</p>
        )}
      </div>

      <div className="mb-6">
        <label className="block text-sm font-semibold text-[#8b4513] mb-2">{unitLabel}范围</label>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="text-xs text-gray-500">起始{unitLabel}</label>
            <input
              type="number"
              min={1}
              max={maxUnit}
              value={unitRange[0]}
              onChange={(e) => onUnitRangeChange([parseInt(e.target.value) || 1, unitRange[1]])}
              onBlur={() => onUnitRangeCommit(unitRange)}
              onKeyDown={commitUnitOnEnter}
              className="w-full mt-1 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
            />
          </div>
          <span className="text-gray-400 mt-6">—</span>
          <div className="flex-1">
            <label className="text-xs text-gray-500">结束{unitLabel}</label>
            <input
              type="number"
              min={1}
              max={maxUnit}
              value={unitRange[1]}
              onChange={(e) => onUnitRangeChange([unitRange[0], parseInt(e.target.value) || maxUnit])}
              onBlur={() => onUnitRangeCommit(unitRange)}
              onKeyDown={commitUnitOnEnter}
              className="w-full mt-1 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
            />
          </div>
        </div>
        <input
          type="range"
          min={1}
          max={maxUnit}
          value={unitRange[1]}
          onChange={(e) => onUnitRangeChange([unitRange[0], parseInt(e.target.value)])}
          onMouseUp={() => onUnitRangeCommit(unitRange)}
          onTouchEnd={() => onUnitRangeCommit(unitRange)}
          className="w-full mt-2 accent-[#8b4513]"
        />
      </div>

      <div>
        <label className="block text-sm font-semibold text-[#8b4513] mb-2">{progressLabel}范围</label>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="text-xs text-gray-500">起始{progressLabel}</label>
            <input
              type="number"
              placeholder="不限"
              value={progressRange[0] !== null ? progressRange[0] : ''}
              onChange={(e) => {
                const val = e.target.value ? parseInt(e.target.value) : null;
                onProgressRangeChange([val, progressRange[1]]);
              }}
              onBlur={() => onProgressRangeCommit(progressRange)}
              onKeyDown={commitProgressOnEnter}
              className="w-full mt-1 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
            />
          </div>
          <span className="text-gray-400 mt-6">—</span>
          <div className="flex-1">
            <label className="text-xs text-gray-500">结束{progressLabel}</label>
            <input
              type="number"
              placeholder="不限"
              value={progressRange[1] !== null ? progressRange[1] : ''}
              onChange={(e) => {
                const val = e.target.value ? parseInt(e.target.value) : null;
                onProgressRangeChange([progressRange[0], val]);
              }}
              onBlur={() => onProgressRangeCommit(progressRange)}
              onKeyDown={commitProgressOnEnter}
              className="w-full mt-1 px-3 py-2 border border-[#d4c5b5] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#8b4513]"
            />
          </div>
        </div>
      </div>

      <div className="mt-4">
        <label className="block text-sm font-semibold text-[#8b4513] mb-2">快速筛选</label>
        <div className="flex flex-wrap gap-2">
          {bookConfig?.quick_filters.map((filter) => (
            <button
              key={filter.label}
              onClick={() => {
                onUnitRangeChange(filter.unit_range);
                onProgressRangeChange(filter.progress_range);
                onUnitRangeCommit(filter.unit_range);
                onProgressRangeCommit(filter.progress_range);
              }}
              className="px-3 py-1 text-sm border border-[#8b4513] text-[#8b4513] rounded-full hover:bg-[#8b4513] hover:text-white transition-colors"
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
