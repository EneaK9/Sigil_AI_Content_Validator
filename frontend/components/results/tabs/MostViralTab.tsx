import type { Post, SourceFilter } from '@/types';
import { filterBySource } from '@/lib/filter';
import { PostCard } from '@/components/results/PostCard';
import { EmptyState } from '@/components/results/EmptyState';
import { platformLabel } from '@/lib/platforms';

interface MostViralTabProps {
  posts: Post[];
  activeSource: SourceFilter;
}

/** Highest-reach posts on the topic, filtered by the active source. */
export function MostViralTab({ posts, activeSource }: MostViralTabProps) {
  const filtered = filterBySource(posts, activeSource);

  if (filtered.length === 0 && activeSource !== 'all') {
    return (
      <EmptyState
        title={`No viral posts from ${platformLabel(activeSource)}`}
        hint="This source did not surface a high-reach post in this timeframe."
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
