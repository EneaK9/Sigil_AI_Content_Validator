import type { SourceFilter, TabId } from '@/types';
import { platformLabel } from '@/lib/platforms';

interface ContextBarProps {
  tab: TabId;
  source: SourceFilter;
  /** Filtered count for the current list (ignored on the sentiment tab). */
  count: number;
}

const NOUN: Record<Exclude<TabId, 'sentiment'>, string> = {
  flags: 'flags',
  influencers: 'influential voices',
  viral: 'viral posts',
};

/** Inset strip describing the current view; reacts to tab + source. */
export function ContextBar({ tab, source, count }: ContextBarProps) {
  let message: string;

  if (tab === 'sentiment') {
    message = 'Sentiment & interest, aggregated across all sources';
  } else {
    const noun = NOUN[tab];
    message =
      source === 'all'
        ? `Showing ${noun} across all sources`
        : `Showing ${count} ${noun} pulled from ${platformLabel(source)}`;
  }

  return (
    <div className="border-b border-line bg-surface-2 px-4 py-2.5">
      <p className="font-mono text-xs text-muted">{message}</p>
    </div>
  );
}
