import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useBookConfig, useChapterIndex, useChapterSynopses, useKeyEventsIndex } from './hooks/useBookArtifacts';
import type { ChapterIndexUnit, ChapterSynopsis, KeyEventsChapter } from './types/pipelineArtifacts';

interface ReaderSegment {
  anchor: string;
  heading: string;
  progressLabel: string | null;
  body: string;
  preview: string;
}

interface ReaderPreferences {
  fontSize: 'small' | 'default' | 'large' | 'xlarge';
  lineWidth: 'compact' | 'comfortable' | 'wide';
  lineHeight: 'compact' | 'relaxed';
  paragraphSpacing: 'compact' | 'relaxed';
  navCollapsed: boolean;
}

interface ReaderRecentPosition {
  unitIndex: number;
  anchor: string | null;
  updatedAt: string;
}

const READER_PREFERENCES_KEY = 'swordcoming-reader-prefs-v1';
const READER_RECENT_KEY = 'swordcoming-reader-recent-v1';

const DEFAULT_PREFERENCES: ReaderPreferences = {
  fontSize: 'default',
  lineWidth: 'comfortable',
  lineHeight: 'relaxed',
  paragraphSpacing: 'relaxed',
  navCollapsed: false,
};

const FONT_SIZE_MAP: Record<ReaderPreferences['fontSize'], string> = {
  small: '16px',
  default: '18px',
  large: '20px',
  xlarge: '22px',
};

const LINE_WIDTH_MAP: Record<ReaderPreferences['lineWidth'], string> = {
  compact: '46rem',
  comfortable: '54rem',
  wide: '62rem',
};

const LINE_HEIGHT_MAP: Record<ReaderPreferences['lineHeight'], string> = {
  compact: '2.0',
  relaxed: '2.32',
};

const PARAGRAPH_GAP_MAP: Record<ReaderPreferences['paragraphSpacing'], string> = {
  compact: '0.9rem',
  relaxed: '1.4rem',
};

function readStoredJson<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw) as T;
    if (
      fallback &&
      typeof fallback === 'object' &&
      !Array.isArray(fallback) &&
      parsed &&
      typeof parsed === 'object' &&
      !Array.isArray(parsed)
    ) {
      return { ...(fallback as Record<string, unknown>), ...(parsed as Record<string, unknown>) } as T;
    }
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

function extractBody(markdown: string) {
  const normalized = markdown.replace(/\r\n?/g, '\n');
  const marker = '\n## 正文';
  const markerIndex = normalized.indexOf(marker);
  if (markerIndex === -1) {
    return normalized.trim();
  }
  return normalized.slice(markerIndex + marker.length).trim();
}

function buildPreview(body: string) {
  const compact = body.replace(/\s+/g, ' ').trim();
  if (!compact) return '当前段暂无正文。';
  return compact.length > 40 ? `${compact.slice(0, 40)}…` : compact;
}

function parseBodyParagraphs(body: string) {
  return body
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function buildReaderHref(unitIndex: number, anchor?: string | null, fromHref?: string | null) {
  const params = new URLSearchParams();
  if (anchor) {
    params.set('anchor', anchor);
  }
  if (fromHref) {
    params.set('from', fromHref);
  }
  const query = params.toString();
  return `/reader/${unitIndex}${query ? `?${query}` : ''}`;
}

function parseChapterSegments(markdown: string, unit: ChapterIndexUnit | null): ReaderSegment[] {
  const content = extractBody(markdown);
  const pattern =
    /<a id="(seg-\d+)"><\/a>\n###\s*(.+)\n(?:- 段落标签：([^\n]+)\n)?\n([\s\S]*?)(?=\n<a id="seg-\d+"><\/a>|\s*$)/g;
  const parsed: ReaderSegment[] = [];
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(content)) !== null) {
    const [, anchor, heading, progressLabel, body] = match;
    const normalizedBody = body.trim();
    parsed.push({
      anchor,
      heading: heading.trim(),
      progressLabel: progressLabel?.trim() ?? null,
      body: normalizedBody,
      preview: buildPreview(normalizedBody),
    });
  }

  if (parsed.length > 0) {
    return parsed;
  }

  return (
    unit?.segments.map((segment) => ({
      anchor: segment.anchor,
      heading: `段 ${segment.segment_index} · 进度 ${segment.progress_index}`,
      progressLabel: segment.progress_label || null,
      body: '',
      preview: segment.progress_label || `段 ${segment.segment_index}`,
    })) ?? []
  );
}

async function fetchChapterMarkdown(relativePath: string) {
  const response = await fetch(encodeURI(`${import.meta.env.BASE_URL}chapters/${relativePath}`));
  if (!response.ok) {
    throw new Error(`读取章节原文失败：${response.status}`);
  }
  const buffer = await response.arrayBuffer();
  return new TextDecoder('utf-8').decode(buffer);
}

function chapterButtonLabel(unit: ChapterIndexUnit) {
  return `${unit.unit_index}. ${unit.chapter_title}`;
}

export default function ChapterReaderPage() {
  const navigate = useNavigate();
  const { unitIndex: unitIndexParam } = useParams();
  const [searchParams] = useSearchParams();
  const { chapterIndex, loading: chapterIndexLoading, error: chapterIndexError } = useChapterIndex();
  const { bookConfig } = useBookConfig();
  const { synopsesMap } = useChapterSynopses();
  const { keyEventsMap } = useKeyEventsIndex();
  const [synopsisOpen, setSynopsisOpen] = useState(false);
  const [keyEventsOpen, setKeyEventsOpen] = useState(true);
  const [markdown, setMarkdown] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<ReaderPreferences>(() =>
    readStoredJson(READER_PREFERENCES_KEY, DEFAULT_PREFERENCES)
  );
  const [recentReading, setRecentReading] = useState<ReaderRecentPosition | null>(() =>
    readStoredJson<ReaderRecentPosition | null>(READER_RECENT_KEY, null)
  );
  const [entryAnchor, setEntryAnchor] = useState<string | null>(searchParams.get('anchor'));
  const [selectedAnchor, setSelectedAnchor] = useState<string | null>(searchParams.get('anchor'));
  const [visibleAnchor, setVisibleAnchor] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const settingsRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  const unitIndex = Number(unitIndexParam ?? '');
  const routeAnchor = searchParams.get('anchor');
  const returnHref = searchParams.get('from');
  const allUnits = useMemo(
    () => [...(chapterIndex?.units ?? [])].sort((left, right) => left.unit_index - right.unit_index),
    [chapterIndex]
  );
  const unit = useMemo(
    () => allUnits.find((item) => item.unit_index === unitIndex) ?? null,
    [allUnits, unitIndex]
  );
  const segments = useMemo(() => parseChapterSegments(markdown, unit), [markdown, unit]);
  const currentAnchor = visibleAnchor ?? selectedAnchor ?? entryAnchor ?? segments[0]?.anchor ?? null;
  const entrySegment = useMemo(
    () => segments.find((segment) => segment.anchor === entryAnchor) ?? null,
    [entryAnchor, segments]
  );
  const currentSegment = useMemo(
    () => segments.find((segment) => segment.anchor === currentAnchor) ?? null,
    [currentAnchor, segments]
  );
  const prevUnit = useMemo(() => {
    const currentIndex = allUnits.findIndex((item) => item.unit_index === unitIndex);
    if (currentIndex <= 0) return null;
    return allUnits[currentIndex - 1] ?? null;
  }, [allUnits, unitIndex]);
  const nextUnit = useMemo(() => {
    const currentIndex = allUnits.findIndex((item) => item.unit_index === unitIndex);
    if (currentIndex === -1 || currentIndex >= allUnits.length - 1) return null;
    return allUnits[currentIndex + 1] ?? null;
  }, [allUnits, unitIndex]);
  const currentVolumeUnits = useMemo(() => {
    if (!unit) return [];
    return allUnits.filter(
      (item) => item.season_index === unit.season_index && item.volume_index === unit.volume_index
    );
  }, [allUnits, unit]);
  const seasonLeads = useMemo(() => {
    const mapped = new Map<number, ChapterIndexUnit>();
    allUnits.forEach((item) => {
      if (!mapped.has(item.season_index)) {
        mapped.set(item.season_index, item);
      }
    });
    return [...mapped.values()].sort((left, right) => left.season_index - right.season_index);
  }, [allUnits]);
  const synopsis: ChapterSynopsis | null = useMemo(
    () => (unit ? synopsesMap.get(unit.unit_index) ?? null : null),
    [synopsesMap, unit]
  );
  const keyEventsChapter: KeyEventsChapter | null = useMemo(
    () => (unit ? keyEventsMap.get(unit.unit_index) ?? null : null),
    [keyEventsMap, unit]
  );
  const showResumeCard =
    !routeAnchor &&
    recentReading &&
    recentReading.unitIndex !== unitIndex &&
    allUnits.some((item) => item.unit_index === recentReading.unitIndex);

  const readerStyle = useMemo(
    () =>
      ({
        '--reader-font-size': FONT_SIZE_MAP[preferences.fontSize],
        '--reader-column-width': LINE_WIDTH_MAP[preferences.lineWidth],
        '--reader-line-height': LINE_HEIGHT_MAP[preferences.lineHeight],
        '--reader-paragraph-gap': PARAGRAPH_GAP_MAP[preferences.paragraphSpacing],
      }) as CSSProperties,
    [preferences.fontSize, preferences.lineWidth, preferences.lineHeight, preferences.paragraphSpacing]
  );

  const readerLayoutStyle = useMemo<CSSProperties | undefined>(() => {
    if (!preferences.navCollapsed) return undefined;
    return { gridTemplateColumns: 'minmax(0, 1fr)' };
  }, [preferences.navCollapsed]);

  const readerContentShellStyle = useMemo<CSSProperties | undefined>(() => {
    if (!preferences.navCollapsed) return undefined;
    return {
      width: '100%',
      maxWidth: '1120px',
      margin: '0 auto',
    };
  }, [preferences.navCollapsed]);

  const readerArticleStyle = useMemo<CSSProperties | undefined>(() => {
    if (!preferences.navCollapsed) return undefined;
    return { width: '100%' };
  }, [preferences.navCollapsed]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    window.localStorage.setItem(READER_PREFERENCES_KEY, JSON.stringify(preferences));
  }, [preferences]);

  useEffect(() => {
    if (!unit) {
      setMarkdown('');
      setLoading(false);
      return;
    }

    const targetUnit = unit;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const content = await fetchChapterMarkdown(targetUnit.relative_path);
        if (!cancelled) {
          setMarkdown(content);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '读取章节原文时发生未知错误。');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [unit]);

  useEffect(() => {
    setEntryAnchor(routeAnchor);
    setSelectedAnchor(routeAnchor ?? (recentReading?.unitIndex === unitIndex ? recentReading.anchor : null));
    setVisibleAnchor(null);
    setSettingsOpen(false);
    setMobileNavOpen(false);
    setSynopsisOpen(false);
    setKeyEventsOpen(true);
  }, [routeAnchor, unitIndex]);

  useEffect(() => {
    if (!segments.length) {
      return;
    }
    if (!selectedAnchor || !segments.some((segment) => segment.anchor === selectedAnchor)) {
      setSelectedAnchor(segments[0].anchor);
    }
  }, [segments, selectedAnchor]);

  useEffect(() => {
    if (!unit) return;
    document.title = `${unit.chapter_title} · ${bookConfig?.title ?? '剑来'} 阅读`;
  }, [bookConfig?.title, unit]);

  useEffect(() => {
    if (!settingsOpen) return;

    function handlePointerDown(event: MouseEvent) {
      if (!settingsRef.current?.contains(event.target as Node)) {
        setSettingsOpen(false);
      }
    }

    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [settingsOpen]);

  useEffect(() => {
    const targetAnchor = selectedAnchor ?? entryAnchor ?? null;
    if (!targetAnchor || loading) return;
    const node = document.getElementById(targetAnchor);
    if (!node) return;

    const raf = requestAnimationFrame(() => {
      node.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    return () => cancelAnimationFrame(raf);
  }, [entryAnchor, loading, selectedAnchor]);

  useEffect(() => {
    if (!segments.length || loading) {
      return;
    }
    const container = contentRef.current;
    if (!container) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];

        if (visible) {
          const anchor = visible.target.getAttribute('data-reader-anchor');
          if (anchor) {
            setVisibleAnchor(anchor);
          }
        }
      },
      {
        root: null,
        rootMargin: '-16% 0px -58% 0px',
        threshold: [0.15, 0.35, 0.6],
      }
    );

    const nodes = Array.from(container.querySelectorAll<HTMLElement>('[data-reader-anchor]'));
    nodes.forEach((node) => observer.observe(node));

    return () => observer.disconnect();
  }, [loading, segments]);

  useEffect(() => {
    if (typeof window === 'undefined' || !unit || !segments.length) {
      return;
    }

    const anchor = visibleAnchor ?? selectedAnchor ?? entryAnchor ?? segments[0]?.anchor ?? null;
    if (!anchor) {
      return;
    }

    const nextRecent: ReaderRecentPosition = {
      unitIndex: unit.unit_index,
      anchor,
      updatedAt: new Date().toISOString(),
    };
    setRecentReading(nextRecent);
    window.localStorage.setItem(READER_RECENT_KEY, JSON.stringify(nextRecent));
  }, [entryAnchor, selectedAnchor, segments, unit, visibleAnchor]);

  function handleBack() {
    if (returnHref) {
      try {
        // returnHref is a hash-route path like "/" or "/?tab=foo", navigate within HashRouter
        const base = import.meta.env.BASE_URL ?? '/';
        const fullUrl = `${window.location.origin}${base}#${returnHref}`;
        if (window.opener && !window.opener.closed) {
          window.opener.focus();
          window.close();
          window.opener.location.assign(fullUrl);
          return;
        }
        window.location.assign(fullUrl);
        return;
      } catch {
        // Ignore malformed return targets.
      }
    }

    if (document.referrer) {
      try {
        const referrer = new URL(document.referrer);
        if (referrer.origin === window.location.origin) {
          window.location.assign(referrer.toString());
          return;
        }
      } catch {
        // Ignore malformed referrers.
      }
    }

    if (window.opener && !window.opener.closed) {
      window.opener.focus();
      window.close();
      return;
    }

    if (window.history.length > 1) {
      navigate(-1);
      return;
    }

    navigate('/');
  }

  function handleSegmentSelect(anchor: string) {
    setSelectedAnchor(anchor);
    setMobileNavOpen(false);
  }

  function handleChapterChange(targetUnitIndex: number, anchor?: string | null) {
    navigate(buildReaderHref(targetUnitIndex, anchor, returnHref));
  }

  function handleSettingChange<K extends keyof ReaderPreferences>(key: K, value: ReaderPreferences[K]) {
    setPreferences((current) => ({ ...current, [key]: value }));
  }

  function handleResumeReading() {
    if (!recentReading) return;
    navigate(buildReaderHref(recentReading.unitIndex, recentReading.anchor, returnHref));
  }

  if (chapterIndexLoading) {
    return (
      <div className="reader-page">
        <div className="reader-loading-shell">正在准备阅读目录…</div>
      </div>
    );
  }

  if (chapterIndexError) {
    return (
      <div className="reader-page">
        <div className="reader-loading-shell">
          <h1 className="reader-error-title">无法打开原文章节</h1>
          <p className="reader-error-copy">{chapterIndexError}</p>
        </div>
      </div>
    );
  }

  if (!unit || Number.isNaN(unitIndex)) {
    return (
      <div className="reader-page">
        <div className="reader-loading-shell">
          <h1 className="reader-error-title">没有找到对应章节</h1>
          <p className="reader-error-copy">请返回分析页后重新打开原文定位。</p>
          <button type="button" className="ink-button" onClick={handleBack}>
            返回分析页
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="reader-page">
      <div className="reader-frame" style={readerStyle}>
        <header className="reader-header">
          <div className="reader-header-copy">
            <p className="reader-kicker">原文阅读</p>
            <h1 className="reader-title">{unit.chapter_title}</h1>
            <p className="reader-subtitle">
              {bookConfig?.title ?? '剑来'} · {unit.season_name} · {unit.volume_title} · 全书第 {unit.unit_index}{' '}
              {bookConfig?.unit_label ?? '章'}
            </p>
            <div className="reader-meta-row">
              <span className="pill-chip">{unit.source_document}</span>
              <span className="pill-chip">叙事进度 {unit.progress_start} - {unit.progress_end}</span>
              <span className="pill-chip">本章共 {segments.length} 段</span>
              {currentSegment ? <span className="pill-chip pill-chip--strong">当前阅读 {currentSegment.heading}</span> : null}
            </div>
          </div>

          {showResumeCard && recentReading ? (
            <div className="reader-resume-card">
              <p className="reader-resume-kicker">继续上次阅读</p>
              <p className="reader-resume-copy">
                你上次停在第 {recentReading.unitIndex} 章
                {recentReading.anchor ? ` · ${recentReading.anchor}` : ''}。
              </p>
              <button type="button" className="outline-button" onClick={handleResumeReading}>
                回到上次位置
              </button>
            </div>
          ) : null}
        </header>

        <div className="reader-toolbar-shell" ref={settingsRef}>
          <div className="reader-toolbar">
            <div className="reader-toolbar-main">
              <button type="button" className="outline-button" onClick={handleBack}>
                返回分析页
              </button>
              <button
                type="button"
                className="ghost-button reader-mobile-toggle"
                onClick={() => setMobileNavOpen(true)}
              >
                查看目录
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => handleSettingChange('navCollapsed', !preferences.navCollapsed)}
              >
                {preferences.navCollapsed ? '展开目录' : '收起目录'}
              </button>
            </div>

            <div className="reader-toolbar-actions">
              <button
                type="button"
                className="outline-button"
                onClick={() => prevUnit && handleChapterChange(prevUnit.unit_index)}
                disabled={!prevUnit}
              >
                上一章
              </button>
              <button
                type="button"
                className="outline-button"
                onClick={() => nextUnit && handleChapterChange(nextUnit.unit_index)}
                disabled={!nextUnit}
              >
                下一章
              </button>
              {entryAnchor ? (
                <button type="button" className="outline-button" onClick={() => handleSegmentSelect(entryAnchor)}>
                  回到命中段
                </button>
              ) : null}
              <button
                type="button"
                className={`ink-button ${settingsOpen ? 'reader-settings-button--open' : ''}`}
                onClick={() => setSettingsOpen((current) => !current)}
              >
                阅读设置
              </button>
            </div>
          </div>

          {settingsOpen ? (
            <div className="reader-settings-panel">
              <div className="reader-settings-group">
                <h2>字号</h2>
                <div className="reader-settings-options">
                  {[
                    ['small', '小'],
                    ['default', '默认'],
                    ['large', '大'],
                    ['xlarge', '特大'],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className="reader-option-button"
                      data-active={preferences.fontSize === value}
                      onClick={() => handleSettingChange('fontSize', value as ReaderPreferences['fontSize'])}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="reader-settings-group">
                <h2>行宽</h2>
                <div className="reader-settings-options">
                  {[
                    ['compact', '紧凑'],
                    ['comfortable', '舒适'],
                    ['wide', '宽'],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className="reader-option-button"
                      data-active={preferences.lineWidth === value}
                      onClick={() => handleSettingChange('lineWidth', value as ReaderPreferences['lineWidth'])}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="reader-settings-group">
                <h2>行距</h2>
                <div className="reader-settings-options">
                  {[
                    ['compact', '紧凑'],
                    ['relaxed', '舒展'],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className="reader-option-button"
                      data-active={preferences.lineHeight === value}
                      onClick={() => handleSettingChange('lineHeight', value as ReaderPreferences['lineHeight'])}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="reader-settings-group">
                <h2>段落间距</h2>
                <div className="reader-settings-options">
                  {[
                    ['compact', '紧凑'],
                    ['relaxed', '舒展'],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className="reader-option-button"
                      data-active={preferences.paragraphSpacing === value}
                      onClick={() =>
                        handleSettingChange('paragraphSpacing', value as ReaderPreferences['paragraphSpacing'])
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {entrySegment ? (
          <div className="reader-anchor-note">
            <div>
              <p className="reader-anchor-kicker">当前定位</p>
              <p className="reader-anchor-copy">
                你是从分析结果跳进来的，目前命中 <strong>{entrySegment.heading}</strong>
                {entrySegment.progressLabel ? ` · ${entrySegment.progressLabel}` : ''}。
              </p>
            </div>
            <button type="button" className="outline-button" onClick={() => handleSegmentSelect(entrySegment.anchor)}>
              回到命中段
            </button>
          </div>
        ) : null}

        <div
          className={`reader-layout ${preferences.navCollapsed ? 'reader-layout--collapsed' : ''}`}
          style={readerLayoutStyle}
        >
          {!preferences.navCollapsed ? (
            <aside className="reader-sidebar">
              <div className="reader-sidebar-sticky">
                <section className="reader-nav-section">
                  <div className="reader-nav-header">
                    <p className="reader-nav-kicker">季别切换</p>
                    <h2>按季浏览</h2>
                  </div>
                  <div className="reader-chip-row">
                    {seasonLeads.map((season) => (
                      <button
                        key={season.season_index}
                        type="button"
                        className="chip-button"
                        data-active={season.season_index === unit.season_index}
                        onClick={() => handleChapterChange(season.unit_index)}
                      >
                        {season.season_name}
                      </button>
                    ))}
                  </div>
                </section>

                <section className="reader-nav-section">
                  <div className="reader-nav-header">
                    <p className="reader-nav-kicker">本卷章节</p>
                    <h2>{unit.volume_title}</h2>
                  </div>
                  <div className="reader-nav-list">
                    {currentVolumeUnits.map((volumeUnit) => (
                      <button
                        key={volumeUnit.unit_index}
                        type="button"
                        className="reader-nav-button"
                        data-active={volumeUnit.unit_index === unit.unit_index}
                        onClick={() => handleChapterChange(volumeUnit.unit_index)}
                      >
                        <span className="reader-nav-title">{chapterButtonLabel(volumeUnit)}</span>
                        <span className="reader-nav-meta">
                          进度 {volumeUnit.progress_start} - {volumeUnit.progress_end}
                        </span>
                      </button>
                    ))}
                  </div>
                </section>

                <section className="reader-nav-section">
                  <div className="reader-nav-header">
                    <p className="reader-nav-kicker">本章段落</p>
                    <h2>快速定位</h2>
                  </div>
                  <div className="reader-nav-list">
                    {segments.map((segment) => (
                      <button
                        key={segment.anchor}
                        type="button"
                        className="reader-nav-button"
                        data-active={segment.anchor === currentAnchor}
                        onClick={() => handleSegmentSelect(segment.anchor)}
                      >
                        <span className="reader-nav-title">{segment.heading}</span>
                        {segment.progressLabel ? (
                          <span className="reader-nav-meta">{segment.progressLabel}</span>
                        ) : null}
                        <span className="reader-nav-preview">{segment.preview}</span>
                      </button>
                    ))}
                  </div>
                </section>
              </div>
            </aside>
          ) : null}
          <main className="reader-content-shell" style={readerContentShellStyle}>
            {loading ? (
              <div className="reader-loading-shell reader-loading-shell--inline">正在载入章节正文…</div>
            ) : error ? (
              <div className="reader-loading-shell reader-loading-shell--inline">
                <h2 className="reader-error-title">章节正文读取失败</h2>
                <p className="reader-error-copy">{error}</p>
              </div>
            ) : (
              <article className="reader-article" style={readerArticleStyle}>
                <header className="reader-article-header">
                  <p className="reader-article-volume">{unit.volume_title}</p>
                  <h2 className="reader-article-title">{unit.chapter_title}</h2>
                  <p className="reader-article-copy">
                    当前阅读 {unit.season_name} · 全书第 {unit.unit_index} {bookConfig?.unit_label ?? '章'} · 共{' '}
                    {segments.length} 段
                  </p>
                </header>

                {synopsis ? (
                  <section className="reader-synopsis">
                    <button
                      type="button"
                      className="reader-synopsis-toggle"
                      aria-expanded={synopsisOpen}
                      onClick={() => setSynopsisOpen((prev) => !prev)}
                    >
                      <span className="reader-synopsis-toggle-label">本章概要</span>
                      <span className="reader-synopsis-badge">{synopsis.narrative_function}</span>
                      <span className="reader-synopsis-chevron" data-open={synopsisOpen}>
                        ▾
                      </span>
                    </button>
                    {synopsisOpen ? (
                      <div className="reader-synopsis-body">
                        <p className="reader-synopsis-text">{synopsis.synopsis}</p>

                        {(synopsis.key_development_events ?? synopsis.key_developments).length > 0 ? (
                          <div className="reader-synopsis-group">
                            <h4 className="reader-synopsis-group-title">关键进展</h4>
                            <ul className="reader-synopsis-list">
                              {synopsis.key_development_events
                                ? synopsis.key_development_events.map((kd, index) => (
                                    <li key={kd.event_id || index}>
                                      {kd.display_text}
                                      {kd.evidence_excerpt && !kd.display_text?.includes(kd.evidence_excerpt) ? (
                                        <span className="reader-synopsis-evidence"> — {kd.evidence_excerpt}</span>
                                      ) : null}
                                    </li>
                                  ))
                                : synopsis.key_developments.map((item, index) => (
                                    <li key={index}>{item}</li>
                                  ))}
                            </ul>
                          </div>
                        ) : null}

                        {synopsis.active_characters.length > 0 ? (
                          <div className="reader-synopsis-group">
                            <h4 className="reader-synopsis-group-title">出场角色</h4>
                            <div className="reader-synopsis-chips">
                              {synopsis.active_characters.map((name) => (
                                <span key={name} className="reader-synopsis-chip">
                                  {name}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {synopsis.locations.length > 0 ? (
                          <div className="reader-synopsis-group">
                            <h4 className="reader-synopsis-group-title">涉及地点</h4>
                            <div className="reader-synopsis-chips">
                              {synopsis.locations.map((name) => (
                                <span key={name} className="reader-synopsis-chip">
                                  {name}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </section>
                ) : null}

                {/* ── 本章关键事件 ── */}
                <section className="reader-keyevents">
                  <button
                    type="button"
                    className="reader-keyevents-toggle"
                    onClick={() => setKeyEventsOpen((prev) => !prev)}
                  >
                    <span className={`reader-keyevents-chevron ${keyEventsOpen ? 'reader-keyevents-chevron--open' : ''}`}>▶</span>
                    <span>本章关键事件</span>
                    {keyEventsChapter && keyEventsChapter.key_events.length > 0 ? (
                      <span className="reader-keyevents-badge">{keyEventsChapter.key_events.length}</span>
                    ) : null}
                  </button>

                  {keyEventsOpen ? (
                    <div className="reader-keyevents-body">
                      {keyEventsChapter && keyEventsChapter.key_events.length > 0 ? (
                        keyEventsChapter.key_events.map((evt) => (
                          <div key={evt.event_id} className="reader-keyevents-card">
                            <div className="reader-keyevents-card-header">
                              <span className="reader-keyevents-name">{evt.name}</span>
                              <span className={`reader-keyevents-tier reader-keyevents-tier--${evt.importance}`}>
                                {evt.importance === 'critical' ? '核心' : evt.importance === 'major' ? '重要' : '关注'}
                              </span>
                            </div>
                            <div className="reader-keyevents-meta">
                              {evt.event_type ? <span className="reader-keyevents-chip">{evt.event_type}</span> : null}
                              {evt.location ? <span className="reader-keyevents-chip">{evt.location}</span> : null}
                              {evt.is_first_occurrence ? <span className="reader-keyevents-chip reader-keyevents-chip--first">首次</span> : null}
                            </div>
                            {evt.participants.length > 0 ? (
                              <div className="reader-keyevents-participants">
                                {evt.participants.map((p) => (
                                  <span key={p} className="reader-keyevents-participant">{p}</span>
                                ))}
                              </div>
                            ) : null}
                            <p className="reader-keyevents-desc">
                              {evt.display_summary || evt.description}
                            </p>
                            {evt.evidence_excerpt && !(evt.display_summary || evt.description)?.includes(evt.evidence_excerpt) ? (
                              <p className="reader-keyevents-evidence">{evt.evidence_excerpt}</p>
                            ) : null}
                            {evt.selection_reason ? (
                              <p className="reader-keyevents-provenance">{evt.selection_reason}</p>
                            ) : null}
                          </div>
                        ))
                      ) : (
                        <p className="reader-keyevents-empty">本章暂无已整理的关键事件</p>
                      )}
                    </div>
                  ) : null}
                </section>

                <div className="reader-article-body" ref={contentRef}>
                  {segments.map((segment) => {
                    const isActive = segment.anchor === currentAnchor;
                    const paragraphs = parseBodyParagraphs(segment.body);

                    return (
                      <section
                        key={segment.anchor}
                        id={segment.anchor}
                        data-reader-anchor={segment.anchor}
                        className={`reader-segment ${isActive ? 'reader-segment--active' : ''}`}
                      >
                        <div className="reader-segment-header">
                          <div>
                            <h3>{segment.heading}</h3>
                            {segment.progressLabel ? <p>{segment.progressLabel}</p> : null}
                          </div>
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() => handleSegmentSelect(segment.anchor)}
                          >
                            定位到这里
                          </button>
                        </div>
                        <div className="reader-segment-body">
                          {paragraphs.length > 0 ? (
                            paragraphs.map((paragraph, index) => (
                              <p key={`${segment.anchor}-${index}`} className="reader-paragraph">
                                {paragraph}
                              </p>
                            ))
                          ) : (
                            <p className="reader-paragraph reader-paragraph--empty">当前段暂无正文。</p>
                          )}
                        </div>
                      </section>
                    );
                  })}
                </div>
              </article>
            )}
          </main>
        </div>
      </div>

      {mobileNavOpen ? (
        <>
          <button
            type="button"
            className="mobile-drawer-backdrop"
            aria-label="关闭目录"
            onClick={() => setMobileNavOpen(false)}
          />
          <div className="mobile-drawer reader-mobile-drawer">
            <div className="mobile-drawer-handle" />
            <div className="panel-inner">
              <div className="reader-mobile-header">
                <div>
                  <p className="reader-nav-kicker">章节导航</p>
                  <h2 className="reader-mobile-title">{unit.chapter_title}</h2>
                </div>
                <button type="button" className="outline-button" onClick={() => setMobileNavOpen(false)}>
                  收起目录
                </button>
              </div>

              <section className="reader-nav-section">
                <div className="reader-nav-header">
                  <p className="reader-nav-kicker">季别切换</p>
                  <h2>按季浏览</h2>
                </div>
                <div className="reader-chip-row">
                  {seasonLeads.map((season) => (
                    <button
                      key={season.season_index}
                      type="button"
                      className="chip-button"
                      data-active={season.season_index === unit.season_index}
                      onClick={() => handleChapterChange(season.unit_index)}
                    >
                      {season.season_name}
                    </button>
                  ))}
                </div>
              </section>

              <section className="reader-nav-section">
                <div className="reader-nav-header">
                  <p className="reader-nav-kicker">本卷章节</p>
                  <h2>{unit.volume_title}</h2>
                </div>
                <div className="reader-nav-list">
                  {currentVolumeUnits.map((volumeUnit) => (
                    <button
                      key={volumeUnit.unit_index}
                      type="button"
                      className="reader-nav-button"
                      data-active={volumeUnit.unit_index === unit.unit_index}
                      onClick={() => handleChapterChange(volumeUnit.unit_index)}
                    >
                      <span className="reader-nav-title">{chapterButtonLabel(volumeUnit)}</span>
                      <span className="reader-nav-meta">
                        进度 {volumeUnit.progress_start} - {volumeUnit.progress_end}
                      </span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="reader-nav-section">
                <div className="reader-nav-header">
                  <p className="reader-nav-kicker">本章段落</p>
                  <h2>快速定位</h2>
                </div>
                <div className="reader-nav-list">
                  {segments.map((segment) => (
                    <button
                      key={segment.anchor}
                      type="button"
                      className="reader-nav-button"
                      data-active={segment.anchor === currentAnchor}
                      onClick={() => handleSegmentSelect(segment.anchor)}
                    >
                      <span className="reader-nav-title">{segment.heading}</span>
                      {segment.progressLabel ? <span className="reader-nav-meta">{segment.progressLabel}</span> : null}
                    </button>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
