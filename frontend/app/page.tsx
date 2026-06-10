import { Dashboard } from '@/components/Dashboard';
import { getTopicReport } from '@/lib/api';
import { mockReport } from '@/lib/mock';
import type { TopicReport } from '@/types';

/**
 * Fetch the initial report once at the page level and hand it to the client
 * Dashboard. When NEXT_PUBLIC_API_BASE_URL is set we hit the live backend;
 * otherwise we render against local mock data so the UI works standalone.
 */
async function loadInitialReport(): Promise<TopicReport> {
  if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
    return mockReport;
  }
  try {
    return await getTopicReport(mockReport.query, mockReport.timeframeDays);
  } catch {
    // Fall back to mock so the dashboard still renders if the backend is down.
    return mockReport;
  }
}

export default async function Page() {
  const report = await loadInitialReport();
  return <Dashboard initialReport={report} />;
}
