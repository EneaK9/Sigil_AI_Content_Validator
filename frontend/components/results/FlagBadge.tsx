import clsx from 'clsx';
import { AlertTriangle } from 'lucide-react';
import type { Severity } from '@/types';

interface FlagBadgeProps {
  policy: string;
  severity: Severity;
}

/** Policy-name badge with a warning icon; alert tone for high severity. */
export function FlagBadge({ policy, severity }: FlagBadgeProps) {
  const high = severity === 'high';
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        high ? 'bg-alert-tint text-alert' : 'bg-amber-tint text-amber',
      )}
    >
      <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
      {policy}
    </span>
  );
}
