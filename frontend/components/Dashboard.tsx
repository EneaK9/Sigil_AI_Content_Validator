'use client';

import { useState } from 'react';
import type { SourceFilter, TabId, TopicReport } from '@/types';
import { useTopicReport } from '@/hooks/useTopicReport';
import { Header } from '@/components/layout/Header';
import { QueryBar } from '@/components/query/QueryBar';
import { MetricStrip } from '@/components/metrics/MetricStrip';
import { ResultsPanel } from '@/components/results/ResultsPanel';
import { RightRail } from '@/components/rail/RightRail';

interface DashboardProps {
  initialReport: TopicReport;
}

/**
 * Client container. Owns interaction state (activeTab + activeSource) and the
 * report lifecycle. Source filtering is pure client-side over fetched arrays.
 */
export function Dashboard({ initialReport }: DashboardProps) {
  const { report, status, error, probe } = useTopicReport(initialReport);
  const [activeTab, setActiveTab] = useState<TabId>('flags');
  const [activeSource, setActiveSource] = useState<SourceFilter>('all');

  function handleProbe(query: string, days: number) {
    setActiveSource('all');
    probe(query, days);
  }

  function handleRetry() {
    probe(report.query, report.timeframeDays);
  }

  return (
    <div className="mx-auto w-full max-w-shell px-4 pb-16 sm:px-6">
      <Header />

      <QueryBar
        initialQuery={report.query}
        initialDays={report.timeframeDays}
        sources={report.sources}
        activeSource={activeSource}
        onSourceChange={setActiveSource}
        onProbe={handleProbe}
        loading={status === 'loading'}
      />

      <div className="mt-4">
        <MetricStrip metrics={report.metrics} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 min-[880px]:grid-cols-[1fr_332px]">
        <ResultsPanel
          report={report}
          activeTab={activeTab}
          activeSource={activeSource}
          onTabChange={setActiveTab}
          status={status}
          error={error}
          onRetry={handleRetry}
        />
        <RightRail report={report} />
      </div>

      <footer className="mt-8 border-t border-line-soft pt-4">
        <p className="max-w-3xl text-xs leading-relaxed text-muted">
          <span className="font-medium text-ink-soft">How to read flags:</span>{' '}
          Flags are AI-suggested candidates mapped to a published platform
          policy, each with a confidence score and the exact cited rule — they
          are not verdicts and not automated reports. The only action is{' '}
          <span className="font-medium text-ink-soft">Review</span>. Sensitive
          posts show a neutral AI summary, never the original content.
          Conversation interest is a relative index, not a headcount, and
          sentiment is a model estimate.
        </p>
      </footer>
    </div>
  );
}
