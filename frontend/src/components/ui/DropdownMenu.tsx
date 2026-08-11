import { useEffect, useRef, useState, cloneElement, isValidElement } from 'react';
import { cn } from '@/lib/utils';

type Item = {
  label: string;
  onClick: () => void;
  danger?: boolean;
};

type Props = {
  trigger: React.ReactElement<{ onClick?: () => void }>;
  items: (Item | 'separator')[];
};

export function DropdownMenu({ trigger, items }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const toggle = () => setOpen((v) => !v);

  return (
    <div ref={ref} className="relative inline-flex">
      {isValidElement(trigger)
        ? cloneElement(trigger, { onClick: toggle })
        : trigger}
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[180px] overflow-hidden rounded-xl border border-white/[.08] bg-[#1a1920] py-1 shadow-2xl">
          {items.map((item, i) =>
            item === 'separator' ? (
              <div key={`sep-${i}`} className="mx-2 my-1 border-t border-white/[.07]" />
            ) : (
              <button
                key={item.label}
                onClick={() => { setOpen(false); item.onClick(); }}
                className={cn(
                  'flex w-full items-center px-4 py-2 text-left text-sm transition',
                  item.danger
                    ? 'text-rose-300 hover:bg-rose-400/10'
                    : 'text-white/75 hover:bg-white/[.06] hover:text-white',
                )}
              >
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
