import { createContext, useCallback, useContext, useState } from 'react';
import { cn } from '@/lib/utils';
import { X } from 'lucide-react';

type ToastKind = 'success' | 'error' | 'info';

type Toast = { id: number; kind: ToastKind; message: string };

type ToastContextValue = { toast: (kind: ToastKind, message: string) => void };

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto flex items-center gap-3 rounded-xl px-4 py-3 text-sm shadow-lg backdrop-blur-xl animate-in slide-in-from-right-2',
              t.kind === 'success' && 'border border-emerald-300/20 bg-emerald-400/10 text-emerald-200',
              t.kind === 'error' && 'border border-rose-300/20 bg-rose-400/10 text-rose-200',
              t.kind === 'info' && 'border border-white/10 bg-white/[.06] text-white/80',
            )}
            role={t.kind === 'error' ? 'alert' : 'status'}
            aria-live={t.kind === 'error' ? 'assertive' : 'polite'}
          >
            <span className="flex-1">{t.message}</span>
            <button type="button" aria-label="Dismiss notification" onClick={() => remove(t.id)} className="shrink-0 rounded p-1 opacity-60 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70">
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
