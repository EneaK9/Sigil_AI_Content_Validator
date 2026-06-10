import type { Account } from '@/types';
import { Avatar } from '@/components/ui/Avatar';
import { formatCompact } from '@/lib/format';
import { platformLabel } from '@/lib/platforms';

interface AccountRowProps {
  account: Account;
}

/** A single leaderboard row: avatar, handle, source · posts, reach in mono. */
export function AccountRow({ account }: AccountRowProps) {
  return (
    <li className="flex items-center gap-3 py-2.5">
      <Avatar
        initials={account.initials}
        color={account.avatarColor}
        size="sm"
      />
      <div className="flex min-w-0 flex-col">
        <span className="truncate font-mono text-sm text-ink">
          {account.handle}
        </span>
        <span className="font-mono text-xs text-muted">
          {platformLabel(account.platform)} · {account.postsOnTopic} posts on
          topic
        </span>
      </div>
      <div className="ml-auto flex flex-col items-end">
        <span className="font-mono text-sm text-ink">
          {formatCompact(account.reach)}
        </span>
        <span className="eyebrow !text-muted">{account.reachUnit}</span>
      </div>
    </li>
  );
}
