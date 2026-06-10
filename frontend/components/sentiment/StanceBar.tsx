import type { Stance } from '@/types';
import { formatPct } from '@/lib/format';

interface StanceBarProps {
  stance: Record<Stance, number>; // percentages, ~sum 100
}

const SEGMENTS: { key: Stance; label: string; className: string }[] = [
  { key: 'support', label: 'Support', className: 'bg-ok' },
  { key: 'critical', label: 'Critical', className: 'bg-alert' },
  { key: 'neutral', label: 'Neutral', className: 'bg-muted' },
];

/** A single rounded horizontal bar split by stance percentages, with legend. */
export function StanceBar({ stance }: StanceBarProps) {
  return (
    <div className="space-y-3">
      <div
        className="flex h-3 w-full overflow-hidden rounded-full bg-surface-2"
        role="img"
        aria-label={`Stance: ${SEGMENTS.map((s) => `${s.label} ${formatPct(stance[s.key])}`).join(', ')}`}
      >
        {SEGMENTS.map((seg) => (
          <span
            key={seg.key}
            className={seg.className}
            style={{ width: `${stance[seg.key]}%` }}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
        {SEGMENTS.map((seg) => (
          <li key={seg.key} className="flex items-center gap-2">
            <span
              className={`inline-block h-2 w-2 rounded-full ${seg.className}`}
              aria-hidden="true"
            />
            <span className="text-sm text-ink-soft">{seg.label}</span>
            <span className="font-mono text-sm text-ink">
              {formatPct(stance[seg.key])}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
