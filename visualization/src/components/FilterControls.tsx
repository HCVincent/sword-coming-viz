import type { CSSProperties, KeyboardEvent } from 'react';
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
  const unitRangeSpan = Math.max(maxUnit - 1, 1);
  const unitRangeTrackStyle = {
    '--range-start': `${((unitRange[0] - 1) / unitRangeSpan) * 100}%`,
    '--range-end': `${((unitRange[1] - 1) / unitRangeSpan) * 100}%`,
  } as CSSProperties;

  const commitUnitOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') onUnitRangeCommit(unitRange);
  };

  const commitProgressOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') onProgressRangeCommit(progressRange);
  };

  return (
    <section className="control-panel">
      <div className="control-panel-header">
        <div>
          <p className="section-kicker">筛选控制</p>
          <h2 className="control-panel-title">筛选条件</h2>
          <p className="control-panel-copy">这里保留原有联动逻辑，只把筛选方式整理得更清楚，方便你顺着章节往下看。</p>
        </div>
      </div>

      <div className="control-stack">
        <div className="control-group">
          <div className="control-label">
            <span>联动模式</span>
            <span className="tag-pill">{syncAvailable ? '可用' : '不可用'}</span>
          </div>
          <label className="toggle-row text-sm text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={syncUnitProgress}
              disabled={!syncAvailable}
              onChange={(e) => onSyncUnitProgressChange(e.target.checked)}
            />
            <span className={!syncAvailable ? 'text-[var(--text-muted)]' : ''}>
              {unitLabel}与{progressLabel}联动
            </span>
          </label>
          {!syncAvailable && <p className="control-help">缺少 `unit_progress_index.json`，因此当前不能做章节与进度联动。</p>}
        </div>

        <div className="control-group">
          <div className="control-label">
            <span>{unitLabel}范围</span>
            <span className="tag-pill">
              {unitRange[0]} - {unitRange[1]}
            </span>
          </div>
          <div className="control-grid control-grid--two">
            <div>
              <label className="field-label">起始{unitLabel}</label>
              <input
                type="number"
                min={1}
                max={maxUnit}
                value={unitRange[0]}
                onChange={(e) => onUnitRangeChange([parseInt(e.target.value, 10) || 1, unitRange[1]])}
                onBlur={() => onUnitRangeCommit(unitRange)}
                onKeyDown={commitUnitOnEnter}
                className="form-input"
              />
            </div>
            <div>
              <label className="field-label">结束{unitLabel}</label>
              <input
                type="number"
                min={1}
                max={maxUnit}
                value={unitRange[1]}
                onChange={(e) => onUnitRangeChange([unitRange[0], parseInt(e.target.value, 10) || maxUnit])}
                onBlur={() => onUnitRangeCommit(unitRange)}
                onKeyDown={commitUnitOnEnter}
                className="form-input"
              />
            </div>
          </div>
          <div className="range-dual" style={unitRangeTrackStyle}>
            <div className="range-dual-track" aria-hidden="true" />
            <input
              type="range"
              min={1}
              max={maxUnit}
              value={unitRange[0]}
              onChange={(e) => onUnitRangeChange([parseInt(e.target.value, 10), unitRange[1]])}
              onMouseUp={(e) => onUnitRangeCommit([parseInt(e.currentTarget.value, 10), unitRange[1]])}
              onTouchEnd={(e) => onUnitRangeCommit([parseInt(e.currentTarget.value, 10), unitRange[1]])}
              className="range-input range-input--start"
              aria-label={`起始${unitLabel}滑杆`}
            />
            <input
              type="range"
              min={1}
              max={maxUnit}
              value={unitRange[1]}
              onChange={(e) => onUnitRangeChange([unitRange[0], parseInt(e.target.value, 10)])}
              onMouseUp={(e) => onUnitRangeCommit([unitRange[0], parseInt(e.currentTarget.value, 10)])}
              onTouchEnd={(e) => onUnitRangeCommit([unitRange[0], parseInt(e.currentTarget.value, 10)])}
              className="range-input range-input--end"
              aria-label={`结束${unitLabel}滑杆`}
            />
          </div>
          <div className="range-dual-labels" aria-hidden="true">
            <span>起始</span>
            <span>结束</span>
          </div>
          <p className="control-help">起始和结束都可以拖动，数字输入仍然保持回车和失焦提交。</p>
        </div>

        <div className="control-group">
          <div className="control-label">
            <span>{progressLabel}范围</span>
            <span className="tag-pill">
              {progressRange[0] ?? '不限'} - {progressRange[1] ?? '不限'}
            </span>
          </div>
          <div className="control-grid control-grid--two">
            <div>
              <label className="field-label">起始{progressLabel}</label>
              <input
                type="number"
                placeholder="不限"
                value={progressRange[0] !== null ? progressRange[0] : ''}
                onChange={(e) => {
                  const value = e.target.value ? parseInt(e.target.value, 10) : null;
                  onProgressRangeChange([value, progressRange[1]]);
                }}
                onBlur={() => onProgressRangeCommit(progressRange)}
                onKeyDown={commitProgressOnEnter}
                className="form-input"
              />
            </div>
            <div>
              <label className="field-label">结束{progressLabel}</label>
              <input
                type="number"
                placeholder="不限"
                value={progressRange[1] !== null ? progressRange[1] : ''}
                onChange={(e) => {
                  const value = e.target.value ? parseInt(e.target.value, 10) : null;
                  onProgressRangeChange([progressRange[0], value]);
                }}
                onBlur={() => onProgressRangeCommit(progressRange)}
                onKeyDown={commitProgressOnEnter}
                className="form-input"
              />
            </div>
          </div>
        </div>

        <div className="control-group">
          <div className="control-label">
            <span>快速跳转</span>
            <span className="tag-pill">{bookConfig?.quick_filters.length ?? 0} 项</span>
          </div>
          <div className="quick-filter-grid">
            {bookConfig?.quick_filters.map((filter) => (
              <button
                key={filter.label}
                type="button"
                className="chip-button"
                data-active={unitRange[0] === filter.unit_range[0] && unitRange[1] === filter.unit_range[1]}
                onClick={() => {
                  onUnitRangeChange(filter.unit_range);
                  onProgressRangeChange(filter.progress_range);
                  onUnitRangeCommit(filter.unit_range);
                  onProgressRangeCommit(filter.progress_range);
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
