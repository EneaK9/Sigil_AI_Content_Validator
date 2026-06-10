import type { Author, Platform } from '@/types';
import { Avatar } from '@/components/ui/Avatar';
import { PlatformTag } from '@/components/ui/PlatformTag';

interface PostHeaderProps {
  author: Author;
  platform: Platform;
  timestamp: string;
}

/** Avatar + handle + platform tag, with a right-aligned timestamp. */
export function PostHeader({ author, platform, timestamp }: PostHeaderProps) {
  return (
    <div className="flex items-center gap-3">
      <Avatar initials={author.initials} color={author.avatarColor} />
      <div className="flex min-w-0 flex-col">
        <span className="truncate font-mono text-sm text-ink">
          {author.handle}
        </span>
        {author.displayName && (
          <span className="truncate text-xs text-muted">
            {author.displayName}
          </span>
        )}
      </div>
      <PlatformTag platform={platform} />
      <span className="ml-auto shrink-0 font-mono text-xs text-muted">
        {timestamp}
      </span>
    </div>
  );
}
