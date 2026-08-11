import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Film, Library, Menu, Settings2, Sparkles, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const links = [{ to: '/generate', label: 'Generate', icon: Sparkles }, { to: '/library', label: 'Library', icon: Library }, { to: '/settings', label: 'Settings', icon: Settings2 }];

export function AppShell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const close = () => setOpen(false);
  return <div className="min-h-screen bg-aurora bg-canvas">
    <aside className={cn('fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/[.07] bg-[#0d0d0f]/90 px-4 py-5 backdrop-blur-2xl transition-transform lg:translate-x-0', open ? 'translate-x-0' : '-translate-x-full')}>
      <div className="flex items-center justify-between px-3"><div className="flex items-center gap-2.5"><div className="grid size-8 place-items-center rounded-xl bg-action shadow-glow"><Film className="size-4 text-white" /></div><div><p className="text-sm font-semibold tracking-tight text-white">ClipCraft</p><p className="font-mono text-[9px] uppercase tracking-[.18em] text-white/35">AI video studio</p></div></div><button onClick={close} className="text-white/40 lg:hidden"><X className="size-5" /></button></div>
      <nav className="mt-14 space-y-1">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={close} className={({ isActive }) => cn('group flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition', isActive || (to === '/library' && location.pathname.startsWith('/library')) ? 'bg-violet-400/10 text-white shadow-[inset_3px_0_0_#a078ff]' : 'text-white/45 hover:bg-white/[.05] hover:text-white/80')}><Icon className="size-4" />{label}</NavLink>)}</nav>
      <div className="mt-auto rounded-2xl border border-white/[.07] bg-white/[.03] p-4"><p className="eyebrow">Local workspace</p><p className="mt-2 text-sm text-white/75">Everything stays on this device.</p><div className="mt-4 h-1 rounded-full bg-white/10"><div className="h-full w-2/5 rounded-full bg-action" /></div><p className="mt-2 font-mono text-[10px] text-white/30">2.4 GB available</p></div>
    </aside>
    {open && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={close} />}
    <main className="min-h-screen lg:pl-64"><header className="flex h-16 items-center justify-between border-b border-white/[.07] px-5 sm:px-8 lg:px-10"><button onClick={() => setOpen(true)} className="text-white/60 lg:hidden"><Menu className="size-5" /></button><div className="hidden lg:block"><p className="font-mono text-[10px] uppercase tracking-[.18em] text-white/30">Workspace / {location.pathname.startsWith('/library') ? 'Library' : location.pathname.slice(1) || 'Generate'}</p></div><div className="ml-auto flex items-center gap-3"><span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_12px_#34d399]" /><span className="font-mono text-[10px] uppercase tracking-[.14em] text-white/35">Local mode</span></div></header><div className="mx-auto max-w-[1440px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10"><Outlet /></div></main>
  </div>;
}
