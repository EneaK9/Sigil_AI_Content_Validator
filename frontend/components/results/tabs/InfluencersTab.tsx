import type { Influencer, SourceFilter } from '@/types';
import { filterBySource } from '@/lib/filter';
import { EmptyState } from '@/components/results/EmptyState';
import { Avatar } from '@/components/ui/Avatar';
import { PlatformTag } from '@/components/ui/PlatformTag';
import { StanceChip } from '@/components/ui/StanceChip';
import { EngagementRow } from '@/components/results/EngagementRow';
import { platformLabel } from '@/lib/platforms';

interface InfluencersTabProps {
  influencers: Influencer[];
  activeSource: SourceFilter;
}

/** Influential voices on the topic, filtered by the active source. */
export function InfluencersTab({
  influencers,
  activeSource,
}: InfluencersTabProps) {
  const filtered = filterBySource(influencers, activeSource);

  if (filtered.length === 0 && activeSource !== 'all') {
    return (
      <EmptyState
        title={`No influential voices from ${platformLabel(activeSource)}`}
        hint="No high-reach account drove this topic on this source."
      />
    );
  }

  return (
    <div className="space-y-3">
      {filtered.map((inf) => (
        <article
          key={inf.id}
          className="rounded-[var(--r)] border border-line bg-surface p-4 shadow-card"
        >
          <div className="flex items-center gap-3">
            <Avatar initials={inf.author.initials} color={inf.author.avatarColor} />
            <div className="flex min-w-0 flex-col">
              <span className="truncate font-mono text-sm text-ink">
                {inf.author.handle}
              </span>
              <span className="font-mono text-xs text-muted">
                {inf.reachLabel}
              </span>
            </div>
            <PlatformTag platform={inf.platform} />
            <span className="ml-auto">
              <StanceChip stance={inf.stance} />
            </span>
          </div>

          <blockquote className="mt-3 border-l-2 border-line pl-3 text-sm leading-relaxed text-ink-soft">
            {inf.quote}
          </blockquote>

          <div className="mt-3">
            <EngagementRow engagement={inf.engagement} />
          </div>
        </article>
      ))}
    </div>
  );
}
