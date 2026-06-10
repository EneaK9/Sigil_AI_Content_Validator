import {
  Heart,
  MessageCircle,
  Share2,
  Repeat2,
  ArrowBigUp,
  Eye,
  type LucideIcon,
} from 'lucide-react';
import type { Engagement } from '@/types';
import { formatCompact } from '@/lib/format';

interface EngagementRowProps {
  engagement: Engagement;
}

// Ordered so the most platform-defining metrics read first.
const FIELDS: { key: keyof Engagement; icon: LucideIcon; label: string }[] = [
  { key: 'likes', icon: Heart, label: 'likes' },
  { key: 'upvotes', icon: ArrowBigUp, label: 'upvotes' },
  { key: 'reposts', icon: Repeat2, label: 'reposts' },
  { key: 'shares', icon: Share2, label: 'shares' },
  { key: 'comments', icon: MessageCircle, label: 'comments' },
  { key: 'views', icon: Eye, label: 'views' },
];

/** Mono engagement metrics; renders only the fields present on `engagement`. */
export function EngagementRow({ engagement }: EngagementRowProps) {
  const present = FIELDS.filter((f) => typeof engagement[f.key] === 'number');

  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-muted">
      {present.map(({ key, icon: Icon, label }) => (
        <li key={key} className="inline-flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="font-mono text-xs text-ink-soft">
            {formatCompact(engagement[key] as number)}
          </span>
          <span className="sr-only">{label}</span>
        </li>
      ))}
    </ul>
  );
}
