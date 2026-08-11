import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; icon?: ReactNode };

export function Button({ className, variant = 'secondary', loading, icon, children, disabled, ...props }: Props) {
  return <button disabled={disabled || loading} className={cn('inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet/70 disabled:cursor-not-allowed disabled:opacity-45', {
    'bg-action text-white shadow-glow hover:brightness-110': variant === 'primary',
    'border border-white/10 bg-white/[.06] text-white/80 hover:bg-white/[.11]': variant === 'secondary',
    'text-white/55 hover:bg-white/[.07] hover:text-white': variant === 'ghost',
    'border border-rose-300/20 bg-rose-400/10 text-rose-200 hover:bg-rose-400/20': variant === 'danger',
  }, className)} {...props}>{loading ? <LoaderCircle className="size-4 animate-spin" /> : icon}{children}</button>;
}
