import type { TopicReport } from '@/types';
import { VolumeCard } from '@/components/rail/VolumeCard';
import { TopAccountsCard } from '@/components/rail/TopAccountsCard';

interface RightRailProps {
  report: TopicReport;
}

/** Right column: volume summary + top-accounts leaderboard. */
export function RightRail({ report }: RightRailProps) {
  const peak = report.volume.reduce(
    (best, p, i) => (p.value > report.volume[best].value ? i : best),
    0,
  );
  const peakLabel = `Peak around day ${peak + 1} of ${report.timeframeDays}`;

  return (
    <aside className="flex flex-col gap-3">
      <VolumeCard
        postCount={report.metrics.postsFound}
        peakLabel={peakLabel}
        points={report.volume}
      />
      <TopAccountsCard accounts={report.topAccounts} />
    </aside>
  );
}
