import { useEffect, useState } from 'react';
import type {
  BookConfig,
  ChapterIndex,
  ChapterSynopsesPayload,
  ChapterSynopsis,
  KeyEventsChapter,
  KeyEventsIndexPayload,
  NarrativeUnit,
  NarrativeUnitsPayload,
  UnitProgressIndex,
  CharacterVisualProfile,
  CharacterVisualProfilesPayload,
  HighValueRoleRoster,
} from '../types/pipelineArtifacts';

export function useUnitProgressIndex() {
  const [unitProgressIndex, setUnitProgressIndex] = useState<UnitProgressIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/unit_progress_index.json`);
        if (!response.ok) {
          throw new Error(`读取章节进度索引失败：${response.status}`);
        }
        const data = (await response.json()) as UnitProgressIndex;
        setUnitProgressIndex(data);
      } catch (err) {
        console.error('Error loading unit progress index:', err);
        setError(err instanceof Error ? err.message : '读取章节进度索引时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { unitProgressIndex, loading, error };
}

export function useBookConfig() {
  const [bookConfig, setBookConfig] = useState<BookConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/book_config.json`);
        if (!response.ok) {
          throw new Error(`读取图书配置失败：${response.status}`);
        }
        const data = (await response.json()) as BookConfig;
        setBookConfig(data);
      } catch (err) {
        console.error('Error loading book config:', err);
        setError(err instanceof Error ? err.message : '读取图书配置时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { bookConfig, loading, error };
}

export function useChapterIndex() {
  const [chapterIndex, setChapterIndex] = useState<ChapterIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/chapter_index.json`);
        if (!response.ok) {
          throw new Error(`读取原文章节索引失败：${response.status}`);
        }
        const data = (await response.json()) as ChapterIndex;
        setChapterIndex(data);
      } catch (err) {
        console.error('Error loading chapter index:', err);
        setError(err instanceof Error ? err.message : '读取原文章节索引时发生未知错误。');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { chapterIndex, loading, error };
}

export function useChapterSynopses() {
  const [synopsesMap, setSynopsesMap] = useState<Map<number, ChapterSynopsis>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/chapter_synopses.json`);
        if (!response.ok) {
          throw new Error(`读取章节概要失败：${response.status}`);
        }
        const data = (await response.json()) as ChapterSynopsesPayload;
        const map = new Map<number, ChapterSynopsis>();
        for (const chapter of data.chapters) {
          map.set(chapter.unit_index, chapter);
        }
        setSynopsesMap(map);
      } catch (err) {
        console.error('Error loading chapter synopses:', err);
        setError(err instanceof Error ? err.message : '读取章节概要时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { synopsesMap, loading, error };
}

export function useKeyEventsIndex() {
  const [keyEventsMap, setKeyEventsMap] = useState<Map<number, KeyEventsChapter>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/key_events_index.json`);
        if (!response.ok) {
          throw new Error(`读取关键事件索引失败：${response.status}`);
        }
        const data = (await response.json()) as KeyEventsIndexPayload;
        const map = new Map<number, KeyEventsChapter>();
        for (const chapter of data.chapters) {
          map.set(chapter.unit_index, chapter);
        }
        setKeyEventsMap(map);
      } catch (err) {
        console.error('Error loading key events index:', err);
        setError(err instanceof Error ? err.message : '读取关键事件索引时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { keyEventsMap, loading, error };
}

export function useNarrativeUnits() {
  const [narrativeUnits, setNarrativeUnits] = useState<NarrativeUnit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/narrative_units.json`);
        if (!response.ok) {
          // Not yet generated – treat as empty, not an error
          setNarrativeUnits([]);
          setError(null);
          return;
        }
        const data = (await response.json()) as NarrativeUnitsPayload;
        setNarrativeUnits(data.units ?? []);
        setError(null);
      } catch (err) {
        console.error('Error loading narrative units:', err);
        setNarrativeUnits([]);
        setError(err instanceof Error ? err.message : '读取剧情单元时发生未知错误');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { narrativeUnits, loading, error };
}

export function useCharacterVisualProfiles() {
  const [profiles, setProfiles] = useState<CharacterVisualProfile[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/character_visual_profiles.json`);
        if (!response.ok) {
          setProfiles([]);
          return;
        }
        const data = (await response.json()) as CharacterVisualProfilesPayload;
        setProfiles(data.profiles ?? []);
      } catch {
        setProfiles([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return { visualProfiles: profiles, loading };
}

export function useHighValueRoster() {
  const [roster, setRoster] = useState<HighValueRoleRoster | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/high_value_role_roster.json`);
        if (!response.ok) {
          setRoster(null);
          return;
        }
        const data = (await response.json()) as HighValueRoleRoster;
        setRoster(data);
      } catch {
        setRoster(null);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return { roster, loading };
}
