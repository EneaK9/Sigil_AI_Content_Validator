import type { Platform } from '@/types';
import { PLATFORM_META } from '@/lib/platforms';

interface PlatformTagProps {
  platform: Platform;
}

/** Small mono platform label used on cards and rows. */
export function PlatformTag({ platform }: PlatformTagProps) {
  return (
    <span className="rounded border border-line-soft bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-muted">
      {PLATFORM_META[platform].label}
    </span>
  );
}
