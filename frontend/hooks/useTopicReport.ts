'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { TopicReport } from '@/types';
import { getTopicReport } from '@/lib/api';
import { getMockTopicReport } from '@/lib/mock';

export type ReportStatus = 'idle' | 'loading' | 'error';

interface UseTopicReportResult {
  report: TopicReport;
  status: ReportStatus;
  error: string | null;
  /** Re-fetch for a new query/timeframe. Aborts any in-flight request. */
  probe: (query: string, days?: number) => void;
}

/**
 * Owns the report lifecycle: loading / error / data, with in-flight abort.
 *
 * Source of truth toggle: when NEXT_PUBLIC_API_BASE_URL is set we hit the live
 * backend via getTopicReport; otherwise we fall back to local mock data so the
 * UI is fully functional standalone. Swapping to live requires no component
 * changes — only the env var.
 */
export function useTopicReport(initial: TopicReport): UseTopicReportResult {
  const [report, setReport] = useState<TopicReport>(initial);
  const [status, setStatus] = useState<ReportStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const useLive = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

  const probe = useCallback(
    (query: string, days = 30) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setStatus('loading');
      setError(null);

      const request = useLive
        ? getTopicReport(query, days, controller.signal)
        : getMockTopicReport();

      request
        .then((next) => {
          if (controller.signal.aborted) return;
          setReport(next);
          setStatus('idle');
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || (err as Error)?.name === 'AbortError')
            return;
          setError(err instanceof Error ? err.message : 'Probe failed');
          setStatus('error');
        });
    },
    [useLive],
  );

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  return { report, status, error, probe };
}
