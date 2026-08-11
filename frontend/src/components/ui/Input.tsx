import type { InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) { return <input className={cn('h-11 w-full rounded-lg border border-white/10 bg-black/20 px-3.5 text-sm text-white outline-none transition placeholder:text-white/25 focus:border-violet-300/50 focus:ring-2 focus:ring-violet-400/10', className)} {...props} />; }
