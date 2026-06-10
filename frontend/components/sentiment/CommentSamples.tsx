import type { SampleComment } from '@/types';
import { StanceChip } from '@/components/ui/StanceChip';
import { PlatformTag } from '@/components/ui/PlatformTag';

interface CommentSamplesProps {
  comments: SampleComment[];
}

/** Representative comments grouped visually by stance dot. */
export function CommentSamples({ comments }: CommentSamplesProps) {
  return (
    <ul className="space-y-3">
      {comments.map((comment, i) => (
        <li
          key={i}
          className="flex items-start gap-3 rounded-lg border border-line-soft bg-surface-2 px-3 py-2.5"
        >
          <span className="mt-1.5">
            <StanceChip stance={comment.stance} dotOnly />
          </span>
          <div className="min-w-0 space-y-1.5">
            <p className="text-sm leading-snug text-ink">{comment.text}</p>
            <PlatformTag platform={comment.platform} />
          </div>
        </li>
      ))}
    </ul>
  );
}
