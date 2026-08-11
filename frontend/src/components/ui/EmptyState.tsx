import type { ReactNode } from 'react';
import { Film } from 'lucide-react';

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) { return <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-white/10 bg-white/[.02] p-8 text-center"><span className="grid size-12 place-items-center rounded-2xl bg-white/[.06] text-white/35"><Film className="size-5" /></span><h3 className="text-sm font-semibold text-white/80">{title}</h3><p className="max-w-xs text-sm leading-6 text-white/40">{description}</p>{action}</div>; }
