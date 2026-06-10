'use client';

import { useRef } from 'react';
import clsx from 'clsx';
import type { TabId } from '@/types';

interface TabDef {
  id: TabId;
  label: string;
  count?: number;
}

interface TabBarProps {
  tabs: TabDef[];
  active: TabId;
  onChange: (id: TabId) => void;
}

/** ARIA tablist with arrow-key navigation; active tab has a petrol underline. */
export function TabBar({ tabs, active, onChange }: TabBarProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function handleKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const dir = e.key === 'ArrowRight' ? 1 : -1;
    const next = (index + dir + tabs.length) % tabs.length;
    const nextId = tabs[next].id;
    onChange(nextId);
    refs.current[nextId]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Results"
      className="flex gap-1 overflow-x-auto border-b border-line"
    >
      {tabs.map((tab, i) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => handleKeyDown(e, i)}
            className={clsx(
              'flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors -mb-px',
              selected
                ? 'border-petrol text-ink'
                : 'border-transparent text-muted hover:text-ink-soft',
            )}
          >
            {tab.label}
            {typeof tab.count === 'number' && (
              <span
                className={clsx(
                  'font-mono text-xs',
                  selected ? 'text-petrol' : 'text-muted',
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
