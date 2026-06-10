import { useId } from 'react';
import type { VolumePoint } from '@/types';

interface AreaChartProps {
  points: VolumePoint[];
  height?: number;
}

const VIEW_W = 300;
const VIEW_H = 80;
const PAD = 6;

/**
 * Hand-rolled SVG area chart. Petrol stroke + soft gradient fill.
 * Values are normalized to the viewBox; uses a unique gradient id per instance.
 */
export function AreaChart({ points, height = 72 }: AreaChartProps) {
  const gradientId = useId();

  if (points.length === 0) {
    return <div style={{ height }} aria-hidden="true" />;
  }

  const values = points.map((p) => p.value);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const step = points.length > 1 ? VIEW_W / (points.length - 1) : VIEW_W;

  const coords = points.map((p, i) => {
    const x = i * step;
    // Leave a little headroom top/bottom so the stroke isn't clipped.
    const y = VIEW_H - PAD - ((p.value - min) / range) * (VIEW_H - PAD * 2);
    return { x, y };
  });

  const line = coords
    .map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(2)},${c.y.toFixed(2)}`)
    .join(' ');

  const area = `${line} L${VIEW_W},${VIEW_H} L0,${VIEW_H} Z`;

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      role="img"
      aria-label="Trend over time"
      className="block"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--petrol)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--petrol)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path
        d={line}
        fill="none"
        stroke="var(--petrol)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
