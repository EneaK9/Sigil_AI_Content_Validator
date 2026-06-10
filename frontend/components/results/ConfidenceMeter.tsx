import clsx from 'clsx';
import type { Severity } from '@/types';

interface ConfidenceMeterProps {
  confidence: number; // 0..100
  severity: Severity;
}

const SEGMENTS = 5;

/** Five-segment meter; fill = round(confidence/20). Color follows severity. */
export function ConfidenceMeter({ confidence, severity }: ConfidenceMeterProps) {
  const filled = Math.max(0, Math.min(SEGMENTS, Math.round(confidence / 20)));
  const fillClass = severity === 'high' ? 'bg-alert' : 'bg-amber';

  return (
    <div className="flex items-center gap-2">
      <span className="eyebrow !text-muted">Confidence</span>
      <div
        className="flex items-center gap-1"
        role="meter"
        aria-valuenow={confidence}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Model confidence"
      >
        {Array.from({ length: SEGMENTS }).map((_, i) => (
          <span
            key={i}
            className={clsx(
              'h-1.5 w-5 rounded-full',
              i < filled ? fillClass : 'bg-line',
            )}
          />
        ))}
      </div>
      <span className="font-mono text-xs text-ink">{Math.round(confidence)}%</span>
    </div>
  );
}
