'use client';

import { ExternalLink } from 'lucide-react';

interface ReviewButtonProps {
  onReview?: () => void;
}

/**
 * The single Review action. By design there is no bulk-report / "report all"
 * affordance anywhere in the product.
 */
export function ReviewButton({ onReview }: ReviewButtonProps) {
  return (
    <button
      type="button"
      onClick={onReview}
      className="inline-flex items-center gap-1.5 rounded-[var(--r)] border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:border-petrol hover:text-petrol"
    >
      Review
      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}
