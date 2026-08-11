import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
};

export function Modal({ open, onClose, title, description, children, footer }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current();
      if (e.key !== 'Tab') return;
      const dialog = closeRef.current?.closest('[role="dialog"]');
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button, input, select, textarea, [href], [tabindex]:not([tabindex="-1"])')).filter((element) => !element.hasAttribute('disabled'));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', handler);
    return () => {
      document.removeEventListener('keydown', handler);
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <button type="button" aria-label="Close dialog" className="absolute inset-0 bg-black/60" onClick={() => onCloseRef.current()} />
      <div
        className="relative z-10 max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-2xl border border-white/[.08] bg-[#121116] p-6 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        aria-describedby={description ? 'modal-description' : undefined}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 id="modal-title" className="text-lg font-semibold text-white">{title}</h2>
            {description && <p id="modal-description" className="mt-1 text-sm text-white/60">{description}</p>}
          </div>
          <button ref={closeRef} type="button" aria-label="Close dialog" onClick={onClose} className="rounded-lg p-2 text-white/55 hover:bg-white/[.07] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70">
            <X className="size-4" />
          </button>
        </div>
        {children && <div className="mt-4">{children}</div>}
        {footer && <div className={cn('mt-6 flex justify-end gap-2')}>{footer}</div>}
      </div>
    </div>
  );
}
