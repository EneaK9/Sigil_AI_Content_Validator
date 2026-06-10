import type { Metrics } from '@/types';
import { MetricCard } from '@/components/metrics/MetricCard';
import { formatCompact, formatThousands, formatPct } from '@/lib/format';
import { platformLabel } from '@/lib/platforms';

interface MetricStripProps {
  metrics: Metrics;
}

/** The four headline metrics across the top of the dashboard. */
export function MetricStrip({ metrics }: MetricStripProps) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard
        eyebrow="Posts found"
        value={formatThousands(metrics.postsFound)}
        delta="across all sources"
      />
      <MetricCard
        eyebrow="Estimated reach"
        value={formatCompact(metrics.estimatedReach)}
        delta="unique impressions, modeled"
      />
      <MetricCard
        eyebrow="Flagged for review"
        value={formatThousands(metrics.flaggedForReview)}
        delta={`${formatPct(metrics.flaggedPct)} of posts found`}
        tone="amber"
      />
      <MetricCard
        eyebrow="Loudest source"
        value={platformLabel(metrics.loudestSource)}
        delta={`${formatPct(metrics.loudestSharePct)} of volume`}
      />
    </div>
  );
}
