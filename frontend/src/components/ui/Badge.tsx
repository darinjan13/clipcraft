import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'violet' | 'blue' | 'green' | 'amber' }) {
  return <span className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[.12em]', {
    'border-white/10 bg-white/[.06] text-white/55': tone === 'neutral',
    'border-violet-300/20 bg-violet-400/10 text-violet-200': tone === 'violet',
    'border-blue-300/20 bg-blue-400/10 text-blue-200': tone === 'blue',
    'border-emerald-300/20 bg-emerald-400/10 text-emerald-200': tone === 'green',
    'border-amber-300/20 bg-amber-400/10 text-amber-200': tone === 'amber',
  })}>{children}</span>;
}
