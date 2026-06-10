'use client';

import { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
import type { SourceCount, SourceFilter as SourceFilterValue } from '@/types';
import { SourceFilter } from '@/components/query/SourceFilter';

interface QueryBarProps {
  initialQuery: string;
  initialDays: number;
  sources: SourceCount[];
  activeSource: SourceFilterValue;
  onSourceChange: (source: SourceFilterValue) => void;
  onProbe: (query: string, days: number) => void;
  loading?: boolean;
}

const TIMEFRAMES = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
];

/**
 * Search field + timeframe + Probe button, with the source filter below a
 * hairline. Sits in its own stacking context so nothing overlaps it.
 */
export function QueryBar({
  initialQuery,
  initialDays,
  sources,
  activeSource,
  onSourceChange,
  onProbe,
  loading = false,
}: QueryBarProps) {
  const [query, setQuery] = useState(initialQuery);
  const [days, setDays] = useState(initialDays);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    onProbe(trimmed, days);
  }

  return (
    <section className="relative z-50 rounded-[var(--r)] border border-line bg-surface shadow-card">
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center"
      >
        <label className="flex flex-1 items-center gap-2.5 rounded-[var(--r)] border border-line bg-surface px-3.5 py-2.5 focus-within:border-petrol">
          <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
          <span className="sr-only">Topic</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter a topic, e.g. Protests in Albania"
            className="w-full bg-transparent text-sm text-ink placeholder:text-muted focus:outline-none"
          />
        </label>

        <label className="flex items-center gap-2">
          <span className="sr-only">Timeframe</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-[var(--r)] border border-line bg-surface px-3 py-2.5 text-sm text-ink-soft focus:border-petrol focus:outline-none"
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf.value} value={tf.value}>
                {tf.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-[var(--r)] bg-petrol px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-petrol-deep disabled:cursor-not-allowed disabled:opacity-70"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : null}
          {loading ? 'Probing' : 'Probe'}
        </button>
      </form>

      <div className="border-t border-line-soft px-4 py-3">
        <SourceFilter
          sources={sources}
          active={activeSource}
          onChange={onSourceChange}
        />
      </div>
    </section>
  );
}
