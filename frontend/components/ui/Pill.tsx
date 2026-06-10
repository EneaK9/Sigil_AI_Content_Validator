import clsx from 'clsx';

interface PillProps {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  'aria-pressed'?: boolean;
}

/** Presentational pill button used by the source filter. */
export function Pill({ active = false, onClick, children, ...rest }: PillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors',
        active
          ? 'border-petrol bg-petrol text-white'
          : 'border-line bg-surface text-ink-soft hover:border-petrol hover:text-ink',
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
