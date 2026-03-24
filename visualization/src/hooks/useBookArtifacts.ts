import { useEffect, useState } from 'react';
import type { BookConfig, UnitProgressIndex } from '../types/pipelineArtifacts';

export function useUnitProgressIndex() {
  const [unitProgressIndex, setUnitProgressIndex] = useState<UnitProgressIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch('/data/unit_progress_index.json');
        if (!response.ok) {
          throw new Error(`Failed to load unit progress index: ${response.status}`);
        }
        const data = (await response.json()) as UnitProgressIndex;
        setUnitProgressIndex(data);
      } catch (err) {
        console.error('Error loading unit progress index:', err);
        setError(err instanceof Error ? err.message : 'Unknown error loading unit progress index');
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
          throw new Error(`Failed to load book config: ${response.status}`);
        }
        const data = (await response.json()) as BookConfig;
        setBookConfig(data);
      } catch (err) {
        console.error('Error loading book config:', err);
        setError(err instanceof Error ? err.message : 'Unknown error loading book config');
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  return { bookConfig, loading, error };
}
