interface HeaderProps {
  workspace?: string;
}

/** App header: wordmark + tagline, workspace label, user avatar. */
export function Header({ workspace = 'Newsroom · Balkans' }: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 py-6">
      <div className="flex items-baseline gap-3">
        <span className="font-display text-2xl font-semibold tracking-tight text-ink">
          Sond<span className="text-amber">ë</span>
        </span>
        <span className="font-mono text-xs uppercase tracking-wide text-muted">
          topic intelligence
        </span>
      </div>
      <div className="flex items-center gap-3">
        <span className="hidden font-mono text-xs text-muted sm:inline">
          {workspace}
        </span>
        <span
          className="flex h-8 w-8 items-center justify-center rounded-full bg-petrol font-mono text-xs font-medium text-white"
          aria-label="User"
        >
          EA
        </span>
      </div>
    </header>
  );
}
