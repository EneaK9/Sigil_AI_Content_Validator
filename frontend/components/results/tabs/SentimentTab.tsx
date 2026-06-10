import type { SentimentSummary } from '@/types';
import { StanceBar } from '@/components/sentiment/StanceBar';
import { CommentSamples } from '@/components/sentiment/CommentSamples';
import { AreaChart } from '@/components/charts/AreaChart';

interface SentimentTabProps {
  sentiment: SentimentSummary;
}

interface BlockProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

function Block({ title, subtitle, children }: BlockProps) {
  return (
    <section className="rounded-[var(--r)] border border-line bg-surface p-4 shadow-card">
      <h3 className="font-display text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-0.5 text-xs text-muted">{subtitle}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/**
 * Sentiment is aggregate — it ignores the source filter. Three stacked blocks:
 * stance, conversation/search interest, and representative comments.
 */
export function SentimentTab({ sentiment }: SentimentTabProps) {
  return (
    <div className="space-y-3">
      <Block
        title="Stance"
        subtitle="Model estimate of how the conversation breaks down — for human spot-check, not a verdict."
      >
        <StanceBar stance={sentiment.stance} />
      </Block>

      <Block
        title="Conversation & search interest"
        subtitle="Relative interest over 30 days — index, not a headcount."
      >
        <AreaChart points={sentiment.interest} height={120} />
      </Block>

      <Block
        title="What people are saying"
        subtitle="Representative comments grouped by estimated stance."
      >
        <CommentSamples comments={sentiment.sampleComments} />
      </Block>
    </div>
  );
}
