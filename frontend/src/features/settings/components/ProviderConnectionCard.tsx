import { CheckCircle2, CircleAlert, KeyRound, TestTube2, Trash2, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import type { AiProvider, Credential } from '../types';

const statusLabels: Record<string, string> = {
  connected: 'Connected',
  invalid_credentials: 'Invalid credentials',
  quota_exceeded: 'Quota exceeded',
  rate_limited: 'Rate limited',
  unavailable: 'Provider unavailable',
  timeout: 'Timed out',
  not_implemented: 'Not implemented',
  configuration_error: 'Needs configuration',
  provider_error: 'Provider error',
};

function formatStatus(status?: string | null) {
  return status ? statusLabels[status] ?? status.replaceAll('_', ' ') : 'Not tested';
}

type Props = {
  provider: AiProvider;
  credential?: Credential;
  testPending: boolean;
  canConfigure: boolean;
  canTest: boolean;
  onConfigure: () => void;
  onTest: () => void;
  onDelete: () => void;
};

export function ProviderConnectionCard({ provider, credential, testPending, canConfigure, canTest, onConfigure, onTest, onDelete }: Props) {
  const configured = Boolean(credential?.configured);
  const status = credential?.last_test_status;
  const statusTone = status === 'connected' ? 'text-emerald-200' : status ? 'text-amber-200' : 'text-white/60';
  const capabilityLabel = provider.capabilities.map((capability) => capability.replace('_', ' ')).join(' / ');

  return (
    <article className="rounded-2xl border border-white/[.08] bg-white/[.035] p-5 transition hover:border-white/[.14]" aria-labelledby={`provider-${provider.provider_id}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-400/10 text-violet-200" aria-hidden="true">
            <span className="text-sm font-semibold">{provider.display_name.slice(0, 1)}</span>
          </span>
          <div className="min-w-0">
            <h3 id={`provider-${provider.provider_id}`} className="font-medium text-white">{provider.display_name}</h3>
            <p className="mt-1 text-xs capitalize text-white/60">{capabilityLabel}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px] font-medium">
          <span className={`rounded-full px-2.5 py-1 ${provider.implemented ? 'bg-emerald-400/10 text-emerald-200' : 'bg-amber-400/10 text-amber-200'}`}>
            {provider.implemented ? 'Implemented' : 'Planned'}
          </span>
          <span className={`rounded-full px-2.5 py-1 ${provider.enabled ? 'bg-white/[.07] text-white/65' : 'bg-rose-400/10 text-rose-200'}`}>
            {provider.enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
      </div>

      <div className="mt-5 grid gap-3 rounded-xl border border-white/[.06] bg-black/15 p-3 sm:grid-cols-3">
        <div>
          <p className="text-[11px] uppercase tracking-[.14em] text-white/55">Connection</p>
          <p className={`mt-1 flex items-center gap-1.5 text-sm ${configured ? 'text-white/80' : 'text-white/55'}`}>
            {configured ? <CheckCircle2 className="size-3.5 text-emerald-300" aria-hidden="true" /> : <KeyRound className="size-3.5" aria-hidden="true" />}
            {configured ? `Configured${credential?.secret_last_four ? ` · ••••${credential.secret_last_four}` : ''}` : 'Not configured'}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[.14em] text-white/55">Last test</p>
          <p className={`mt-1 text-sm capitalize ${statusTone}`}>{formatStatus(status)}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[.14em] text-white/55">Checked</p>
          <p className="mt-1 text-sm text-white/65">{credential?.last_tested_at ? new Date(credential.last_tested_at).toLocaleString() : 'Not yet'}</p>
        </div>
      </div>

      {credential?.last_test_error_safe && <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-amber-100/90" role="alert"><CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{credential.last_test_error_safe}</p>}

      {!provider.implemented && provider.provider_id === 'nvidia' && <p className="mt-3 text-xs leading-5 text-white/55">Generation and connection testing will unlock after model verification. You can securely configure the credential now.</p>}

      <div className="mt-5 flex flex-wrap gap-2">
        {canConfigure ? (
          <Button type="button" variant={configured ? 'secondary' : 'primary'} onClick={onConfigure} icon={<KeyRound className="size-4" />}>
            {configured ? 'Replace credential' : 'Configure'}
          </Button>
        ) : <span className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/[.08] px-4 text-sm text-white/45"><Wrench className="size-4" aria-hidden="true" />Unavailable</span>}
        {configured && canTest && <Button type="button" variant="ghost" loading={testPending} onClick={onTest} icon={<TestTube2 className="size-4" />} aria-label={`Test ${provider.display_name} connection`}>Test connection</Button>}
        {configured && canConfigure && <Button type="button" variant="danger" onClick={onDelete} icon={<Trash2 className="size-4" />}>Delete</Button>}
      </div>
    </article>
  );
}
