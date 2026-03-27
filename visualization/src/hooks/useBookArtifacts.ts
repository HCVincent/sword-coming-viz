import { useEffect, useState } from 'react';
import type { BookConfig, ChapterIndex, UnitProgressIndex } from '../types/pipelineArtifacts';

export function useUnitProgressIndex() {
  const [unitProgressIndex, setUnitProgressIndex] = useState<UnitProgressIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch('/data/unit_progress_index.json');
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
        const response = await fetch('/data/book_config.json');
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
        const response = await fetch('/data/chapter_index.json');
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
