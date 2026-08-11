import type { SelectHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) { return <select className={cn('h-11 w-full appearance-none rounded-lg border border-white/10 bg-[#111113] px-3.5 text-sm text-white/80 outline-none transition focus:border-violet-300/50 focus-visible:ring-2 focus-visible:ring-violet-400/40', className)} {...props}>{children}</select>; }
