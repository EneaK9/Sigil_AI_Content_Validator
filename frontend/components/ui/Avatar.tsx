import clsx from 'clsx';

interface AvatarProps {
  initials: string;
  color: string; // hex background tile
  size?: 'sm' | 'md';
}

/** Square initials tile. Color is data-driven (per author), not a token. */
export function Avatar({ initials, color, size = 'md' }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      style={{ backgroundColor: color }}
      className={clsx(
        'inline-flex shrink-0 items-center justify-center rounded-md font-mono font-medium uppercase text-white',
        size === 'sm' ? 'h-8 w-8 text-xs' : 'h-9 w-9 text-sm',
      )}
    >
      {initials}
    </span>
  );
}
