import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        ink: 'var(--ink)',
        'ink-soft': 'var(--ink-soft)',
        muted: 'var(--muted)',
        paper: 'var(--paper)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        line: 'var(--line)',
        'line-soft': 'var(--line-soft)',
        petrol: {
          DEFAULT: 'var(--petrol)',
          deep: 'var(--petrol-deep)',
        },
        amber: { DEFAULT: 'var(--amber)', tint: 'var(--amber-tint)' },
        alert: { DEFAULT: 'var(--alert)', tint: 'var(--alert-tint)' },
        ok: { DEFAULT: 'var(--ok)', tint: 'var(--ok-tint)' },
        'petrol-tint': 'var(--petrol-tint)',
      },
      fontFamily: {
        display: ['var(--font-display)'],
        sans: ['var(--font-body)'],
        mono: ['var(--font-mono)'],
      },
      borderRadius: {
        DEFAULT: 'var(--r)',
      },
      boxShadow: {
        card: '0 1px 0 rgba(22,33,43,0.03)',
        pop: '0 14px 34px rgba(22,33,43,0.14)',
      },
      maxWidth: {
        shell: '1180px',
      },
    },
  },
  plugins: [],
};

export default config;
