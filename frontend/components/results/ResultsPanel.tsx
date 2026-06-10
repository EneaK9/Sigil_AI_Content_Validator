'use client';

import { Loader2, TriangleAlert } from 'lucide-react';
import type { SourceFilter, TabId, TopicReport } from '@/types';
import type { ReportStatus } from '@/hooks/useTopicReport';
import { filterBySource } from '@/lib/filter';
import { TabBar } from '@/components/results/TabBar';
import { ContextBar } from '@/components/results/ContextBar';
import { PolicyFlagsTab } from '@/components/results/tabs/PolicyFlagsTab';
import { SentimentTab } from '@/components/results/tabs/SentimentTab';
import { InfluencersTab } from '@/components/results/tabs/InfluencersTab';
import { MostViralTab } from '@/components/results/tabs/MostViralTab';

interface ResultsPanelProps {
  report: TopicReport;
  activeTab: TabId;
  activeSource: SourceFilter;
  onTabChange: (tab: TabId) => void;
  status: ReportStatus;
  error: string | null;
  onRetry: () => void;
}

/** Left column: tabs → context bar → active tab body (or loading/error). */
export function ResultsPanel({
  report,
  activeTab,
  activeSource,
  onTabChange,
  status,
  error,
  onRetry,
}: ResultsPanelProps) {
  const tabs = [
    { id: 'flags' as const, label: 'Policy flags', count: report.flags.length },
    { id: 'sentiment' as const, label: 'Sentiment' },
    {
      id: 'influencers' as const,
      label: 'Influencers',
      count: report.influencers.length,
    },
    { id: 'viral' as const, label: 'Most viral', count: report.viral.length },
  ];

  // Filtered count drives the context bar (sentiment is exempt from filtering).
  const contextCount =
    activeTab === 'flags'
      ? filterBySource(report.flags, activeSource).length
      : activeTab === 'influencers'
        ? filterBySource(report.influencers, activeSource).length
        : activeTab === 'viral'
          ? filterBySource(report.viral, activeSource).length
          : 0;

  return (
    <div className="overflow-hidden rounded-[var(--r)] border border-line bg-surface shadow-card">
      <div className="px-4 pt-2">
        <TabBar tabs={tabs} active={activeTab} onChange={onTabChange} />
      </div>

      <ContextBar tab={activeTab} source={activeSource} count={contextCount} />

      <div
        id={`panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`tab-${activeTab}`}
        className="p-4"
      >
        {status === 'loading' ? (
          <div className="flex items-center justify-center gap-2 py-16 text-muted">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span className="text-sm">Probing the topic…</span>
          </div>
        ) : status === 'error' ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <TriangleAlert className="h-6 w-6 text-alert" aria-hidden="true" />
            <p className="text-sm font-medium text-ink">
              {error ?? 'Probe failed'}
            </p>
            <button
              type="button"
              onClick={onRetry}
              className="rounded-[var(--r)] border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-petrol hover:text-petrol"
            >
              Try again
            </button>
          </div>
        ) : (
          <div className="rise-in">
            {activeTab === 'flags' && (
              <PolicyFlagsTab posts={report.flags} activeSource={activeSource} />
            )}
            {activeTab === 'sentiment' && (
              <SentimentTab sentiment={report.sentiment} />
            )}
            {activeTab === 'influencers' && (
              <InfluencersTab
                influencers={report.influencers}
                activeSource={activeSource}
              />
            )}
            {activeTab === 'viral' && (
              <MostViralTab posts={report.viral} activeSource={activeSource} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
