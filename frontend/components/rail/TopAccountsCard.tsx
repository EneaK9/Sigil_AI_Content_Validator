import type { Account } from '@/types';
import { AccountRow } from '@/components/rail/AccountRow';

interface TopAccountsCardProps {
  accounts: Account[];
}

/** Right-rail leaderboard of the most influential accounts on the topic. */
export function TopAccountsCard({ accounts }: TopAccountsCardProps) {
  return (
    <section className="rounded-[var(--r)] border border-line bg-surface p-4 shadow-card">
      <p className="eyebrow">Top accounts</p>
      <ul className="mt-1 divide-y divide-line-soft">
        {accounts.map((account) => (
          <AccountRow key={account.id} account={account} />
        ))}
      </ul>
    </section>
  );
}
