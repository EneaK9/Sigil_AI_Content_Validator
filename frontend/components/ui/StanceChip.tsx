import clsx from 'clsx';
import type { Stance } from '@/types';

interface StanceChipProps {
  stance: Stance;
  /** Render only the colored dot (no label). */
  dotOnly?: boolean;
}

const STANCE_LABEL: Record<Stance, string> = {
  support: 'Support',
  critical: 'Critical',
  neutral: 'Neutral',
};

const STANCE_DOT: Record<Stance, string> = {
  support: 'bg-ok',
  critical: 'bg-alert',
  neutral: 'bg-muted',
};

/** Stance indicator: a colored dot with an optional label. */
export function StanceChip({ stance, dotOnly = false }: StanceChipProps) {
  const dot = (
    <span
      className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', STANCE_DOT[stance])}
      aria-hidden="true"
    />
  );

  if (dotOnly) return dot;

  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
      {dot}
      {STANCE_LABEL[stance]}
    </span>
  );
}
