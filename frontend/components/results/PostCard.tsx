import clsx from 'clsx';
import { ShieldCheck } from 'lucide-react';
import type { Post } from '@/types';
import { PostHeader } from '@/components/results/PostHeader';
import { EngagementRow } from '@/components/results/EngagementRow';
import { FlagBadge } from '@/components/results/FlagBadge';
import { ConfidenceMeter } from '@/components/results/ConfidenceMeter';
import { ReviewButton } from '@/components/results/ReviewButton';

interface PostCardProps {
  post: Post;
}

/** A single post: header + snippet + engagement, with an optional flag block. */
export function PostCard({ post }: PostCardProps) {
  const { flag } = post;

  return (
    <article className="rounded-[var(--r)] border border-line bg-surface p-4 shadow-card">
      <PostHeader
        author={post.author}
        platform={post.platform}
        timestamp={post.timestamp}
      />

      <p
        className={clsx(
          'mt-3 text-sm leading-relaxed',
          post.redacted ? 'italic text-muted' : 'text-ink-soft',
        )}
      >
        {post.snippet}
      </p>

      <div className="mt-3">
        <EngagementRow engagement={post.engagement} />
      </div>

      {flag ? (
        <div className="mt-4 space-y-3 rounded-[var(--r)] border border-line-soft bg-surface-2 p-3">
          <FlagBadge policy={flag.policy} severity={flag.severity} />
          <p className="text-xs leading-relaxed text-ink-soft">
            <span className="font-semibold text-ink">
              {flag.citedRule.split('—')[0].trim()}
            </span>
            {flag.citedRule.includes('—')
              ? ` — ${flag.citedRule.split('—').slice(1).join('—').trim()}`
              : ''}
          </p>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ConfidenceMeter
              confidence={flag.confidence}
              severity={flag.severity}
            />
            <ReviewButton />
          </div>
        </div>
      ) : (
        <p className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-ok">
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          No policy match
        </p>
      )}
    </article>
  );
}
