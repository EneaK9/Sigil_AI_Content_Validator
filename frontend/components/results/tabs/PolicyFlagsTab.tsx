import type { Post, SourceFilter } from '@/types';
import { filterBySource } from '@/lib/filter';
import { PostCard } from '@/components/results/PostCard';
import { EmptyState } from '@/components/results/EmptyState';
import { platformLabel } from '@/lib/platforms';

interface PolicyFlagsTabProps {
  posts: Post[];
  activeSource: SourceFilter;
}

/** AI-suggested policy flags, filtered by the active source. */
export function PolicyFlagsTab({ posts, activeSource }: PolicyFlagsTabProps) {
  const filtered = filterBySource(posts, activeSource);

  if (filtered.length === 0 && activeSource !== 'all') {
    return (
      <EmptyState
        title={`No flags from ${platformLabel(activeSource)}`}
        hint="Nothing this source pulled matched a published policy in this timeframe."
      />
    );
  }

  return (
    <div className="space-y-3">
      {filtered.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}
    </div>
  );
}
