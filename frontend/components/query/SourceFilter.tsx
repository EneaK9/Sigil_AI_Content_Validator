import type { SourceCount, SourceFilter as SourceFilterValue } from '@/types';
import { Pill } from '@/components/ui/Pill';
import { PLATFORM_META } from '@/lib/platforms';
import { formatCompact } from '@/lib/format';

interface SourceFilterProps {
  sources: SourceCount[];
  active: SourceFilterValue;
  onChange: (source: SourceFilterValue) => void;
}

/**
 * Filter results by platform. This is a filter, not an on/off switch —
 * selecting a platform shows what that platform pulled.
 */
export function SourceFilter({ sources, active, onChange }: SourceFilterProps) {
  const total = sources.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Pill active={active === 'all'} onClick={() => onChange('all')}>
        <span>All</span>
        <span className="h-3 w-px bg-current opacity-25" aria-hidden="true" />
        <span className="font-mono text-xs opacity-80">
          {formatCompact(total)}
        </span>
      </Pill>

      {sources.map((source) => (
        <Pill
          key={source.platform}
          active={active === source.platform}
          onClick={() => onChange(source.platform)}
        >
          {source.live && (
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-ok"
              aria-label="live"
            />
          )}
          <span>{PLATFORM_META[source.platform].label}</span>
          <span className="h-3 w-px bg-current opacity-25" aria-hidden="true" />
          <span className="font-mono text-xs opacity-80">
            {formatCompact(source.count)}
          </span>
        </Pill>
      ))}
    </div>
  );
}
