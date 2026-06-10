export type Platform = 'x' | 'reddit' | 'facebook' | 'instagram' | 'tiktok';
export type SourceFilter = Platform | 'all';
export type Stance = 'support' | 'critical' | 'neutral';
export type TabId = 'flags' | 'sentiment' | 'influencers' | 'viral';
export type Severity = 'low' | 'high';

export interface Author {
  handle: string; // "@lajme_today" | "u/tirana_live" | "Albanian News Now"
  initials: string; // "lt"
  avatarColor: string; // hex for the avatar tile
  displayName?: string;
}

export interface Engagement {
  likes?: number;
  comments?: number;
  shares?: number;
  reposts?: number;
  upvotes?: number;
  views?: number;
}

export interface PolicyFlag {
  policy: string; // "Targeted harassment"
  citedRule: string; // "X Abuse & Harassment — 'targeting individuals with repeated unwanted mentions.'"
  confidence: number; // 0..100
  severity: Severity;
}

export interface Post {
  id: string;
  platform: Platform;
  author: Author;
  timestamp: string; // relative label ok ("2d ago")
  snippet: string; // if `redacted`, this is the AI's neutral summary, not raw content
  redacted?: boolean;
  engagement: Engagement;
  flag?: PolicyFlag | null; // null/undefined => clean, no policy match
}

export interface Influencer {
  id: string;
  platform: Platform;
  author: Author;
  reachLabel: string; // "1.4M followers" | "410k members"
  quote: string;
  stance: Stance;
  engagement: Engagement;
}

export interface SampleComment {
  stance: Stance;
  text: string;
  platform: Platform;
}

export interface VolumePoint {
  date: string;
  value: number; // value = relative index 0..100
}

export interface SentimentSummary {
  stance: Record<Stance, number>; // percentages, ~sum 100
  interest: VolumePoint[]; // relative interest, NOT absolute counts
  sampleComments: SampleComment[];
}

export interface Account {
  id: string;
  platform: Platform;
  handle: string;
  reach: number;
  reachUnit: string; // "FOLLOWERS" | "MEMBERS" | "KARMA"
  postsOnTopic: number;
  initials: string;
  avatarColor: string;
}

export interface SourceCount {
  platform: Platform;
  count: number;
  live: boolean;
}

export interface Metrics {
  postsFound: number;
  estimatedReach: number;
  flaggedForReview: number;
  flaggedPct: number;
  loudestSource: Platform;
  loudestSharePct: number;
}

export interface TopicReport {
  query: string;
  timeframeDays: number;
  sources: SourceCount[]; // for the source-filter pills (count + live status)
  metrics: Metrics;
  flags: Post[];
  viral: Post[];
  influencers: Influencer[];
  sentiment: SentimentSummary;
  volume: VolumePoint[]; // right-rail volume sparkline
  topAccounts: Account[]; // right-rail leaderboard
}
