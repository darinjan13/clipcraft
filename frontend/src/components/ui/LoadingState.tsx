import { LoaderCircle } from 'lucide-react';

export function LoadingState({ label = 'Loading workspace' }: { label?: string }) { return <div className="flex min-h-64 items-center justify-center gap-3 text-sm text-white/40"><LoaderCircle className="size-4 animate-spin text-violet-300" />{label}</div>; }
