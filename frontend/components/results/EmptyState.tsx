import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  hint?: string;
}

/** Shown when a source filter yields no items for the active tab. */
export function EmptyState({ title, hint }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-[var(--r)] border border-dashed border-line bg-surface px-6 py-12 text-center">
      <Inbox className="h-6 w-6 text-muted" aria-hidden="true" />
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-xs text-xs text-muted">{hint}</p>}
    </div>
  );
}
