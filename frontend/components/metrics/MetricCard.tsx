import clsx from 'clsx';

interface MetricCardProps {
  eyebrow: string;
  value: string;
  /** Optional small line under the value (e.g. delta or context). */
  delta?: string;
  /** Tint the big number (used for "Flagged for review"). */
  tone?: 'default' | 'amber';
}

/** Presentational metric tile: eyebrow label + big mono number + optional delta. */
export function MetricCard({
  eyebrow,
  value,
  delta,
  tone = 'default',
}: MetricCardProps) {
  return (
    <div className="rounded-[var(--r)] border border-line bg-surface p-4 shadow-card">
      <p className="eyebrow">{eyebrow}</p>
      <p
        className={clsx(
          'mt-2 font-mono text-2xl font-medium tracking-tight',
          tone === 'amber' ? 'text-amber' : 'text-ink',
        )}
      >
        {value}
      </p>
      {delta && <p className="mt-1 text-xs text-muted">{delta}</p>}
    </div>
  );
}
