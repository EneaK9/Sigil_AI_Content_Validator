import type { VolumePoint } from '@/types';
import { AreaChart } from '@/components/charts/AreaChart';
import { formatThousands } from '@/lib/format';

interface VolumeCardProps {
  postCount: number;
  peakLabel: string;
  points: VolumePoint[];
}

/** Right-rail volume summary: mono headline + peak line + area chart. */
export function VolumeCard({ postCount, peakLabel, points }: VolumeCardProps) {
  return (
    <section className="rounded-[var(--r)] border border-line bg-surface p-4 shadow-card">
      <p className="eyebrow">Volume</p>
      <p className="mt-2 font-mono text-2xl font-medium tracking-tight text-ink">
        {formatThousands(postCount)}
        <span className="ml-1.5 text-sm font-normal text-muted">posts</span>
      </p>
      <p className="mt-0.5 text-xs text-muted">{peakLabel}</p>
      <div className="mt-3">
        <AreaChart points={points} height={72} />
      </div>
    </section>
  );
}
