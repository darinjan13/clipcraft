import { useEffect, useState } from 'react';
import { KeyRound, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import type { AiProvider } from '../types';

type Props = {
  provider: AiProvider | null;
  open: boolean;
  pending: boolean;
  onClose: () => void;
  onSave: (secret: string, metadata?: Record<string, string>) => void;
};

export function CredentialDialog({ provider, open, pending, onClose, onSave }: Props) {
  const [secret, setSecret] = useState('');
  const [accountId, setAccountId] = useState('');

  useEffect(() => {
    if (open) {
      setSecret('');
      setAccountId('');
    } else {
      setSecret('');
      setAccountId('');
    }
  }, [open, provider?.provider_id]);

  if (!provider) return null;
  const isCloudflare = provider.provider_id === 'cloudflare';
  const canSubmit = secret.length > 0 && (!isCloudflare || accountId.trim().length > 0);

  return (
    <Modal
      open={open}
      onClose={() => { if (!pending) onClose(); }}
      title={`${provider.display_name} credential`}
      description="Your secret is sent only to the local ClipCraft backend and is never shown again."
      footer={(
        <>
          <Button type="button" variant="ghost" onClick={() => { if (!pending) onClose(); }}>Cancel</Button>
          <Button type="submit" form="credential-form" variant="primary" disabled={!canSubmit} loading={pending} icon={<ShieldCheck className="size-4" />}>Save securely</Button>
        </>
      )}
    >
      <form id="credential-form" className="space-y-4" onSubmit={(event) => {
        event.preventDefault();
        if (!canSubmit || pending) return;
        const metadata = isCloudflare ? { account_id: accountId.trim() } : undefined;
        onSave(secret, metadata);
        setSecret('');
        setAccountId('');
      }}>
        <label className="block">
          <span className="mb-2 block text-xs font-medium text-white/75">{provider.credential_type === 'api_token' ? 'API token' : 'API key'}</span>
          <Input autoFocus type="password" name={`${provider.provider_id}-secret`} autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="Enter a new secret" aria-describedby="credential-secret-help" />
          <span id="credential-secret-help" className="mt-2 block text-xs leading-5 text-white/55">Saved secrets are masked and cannot be retrieved from this screen.</span>
        </label>
        {isCloudflare && <label className="block">
          <span className="mb-2 block text-xs font-medium text-white/75">Account ID</span>
          <Input type="text" name="cloudflare-account-id" autoComplete="off" value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="Your Cloudflare account ID" />
        </label>}
        <p className="flex items-start gap-2 rounded-xl border border-emerald-300/10 bg-emerald-400/[.04] px-3 py-2.5 text-xs leading-5 text-emerald-100/75"><KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />The credential is encrypted at rest. It is not stored in browser storage.</p>
      </form>
    </Modal>
  );
}
