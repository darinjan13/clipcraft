import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { MonitorCog, Palette, Save } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { LoadingState } from '@/components/ui/LoadingState';
import { Modal } from '@/components/ui/Modal';
import { Panel } from '@/components/ui/Panel';
import { Select } from '@/components/ui/Select';
import { useToast } from '@/components/ui/Toast';
import { CredentialDialog } from '../components/CredentialDialog';
import { PreferencesSection } from '../components/PreferencesSection';
import { ProviderConnectionCard } from '../components/ProviderConnectionCard';
import { settingsKeys } from '../api/queryKeys';
import { deleteCredential, getPreferences, listCredentials, listProviders, saveCredential, savePreferences, SettingsApiError, testCredential } from '../api/settingsService';
import type { AiProvider, PreferencesInput } from '../types';
import { useSettingsStore } from '../store/useSettingsStore';

type Section = 'connections' | 'defaults' | 'workspace';

const preferenceFieldLabels: Record<string, string> = {
  unknown_provider: 'Choose a supported provider.',
  unknown_model: 'Choose a supported model.',
  provider_model_mismatch: 'Choose a model from the selected provider.',
  provider_unimplemented: 'That provider is not available yet.',
  disabled_provider: 'That provider is currently disabled.',
  unsupported_visual_source: 'Choose a supported visual source.',
};

const sections = [['connections', 'Provider connections'], ['defaults', 'Generation defaults'], ['workspace', 'Workspace']] as const;

export function SettingsPage() {
  const settings = useSettingsStore();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [section, setSection] = useState<Section>('connections');
  const [credentialProvider, setCredentialProvider] = useState<AiProvider | null>(null);
  const [deleteProvider, setDeleteProvider] = useState<AiProvider | null>(null);
  const [preferenceValues, setPreferenceValues] = useState<PreferencesInput | null>(null);
  const [preferencesDirty, setPreferencesDirty] = useState(false);
  const [preferencesError, setPreferencesError] = useState('');
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const providersQuery = useQuery({ queryKey: settingsKeys.providers, queryFn: listProviders, staleTime: 5 * 60 * 1000 });
  const credentialsQuery = useQuery({ queryKey: settingsKeys.credentials, queryFn: listCredentials, staleTime: 30 * 1000 });
  const preferencesQuery = useQuery({ queryKey: settingsKeys.preferences, queryFn: getPreferences, staleTime: 30 * 1000 });

  useEffect(() => {
    if (preferencesQuery.data && !preferencesDirty) {
      const { updated_at: _updatedAt, ...values } = preferencesQuery.data;
      setPreferenceValues(values);
    }
  }, [preferencesQuery.data, preferencesDirty]);

  const saveCredentialMutation = useMutation({
    mutationFn: ({ providerId, secret, metadata }: { providerId: string; secret: string; metadata?: Record<string, string> }) => saveCredential(providerId, { secret, metadata }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.credentials });
      setCredentialProvider(null);
      toast('success', 'Credential saved securely.');
    },
    onError: (error: Error) => toast('error', error.message || 'Could not save credential.'),
  });

  const testMutation = useMutation({
    mutationFn: (providerId: string) => testCredential(providerId),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.credentials });
      toast(result.status === 'connected' ? 'success' : 'error', result.message);
    },
    onError: (error: Error) => toast('error', error.message || 'Connection test failed.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (providerId: string) => deleteCredential(providerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKeys.credentials });
      setDeleteProvider(null);
      toast('success', 'Credential deleted.');
    },
    onError: (error: Error) => toast('error', error.message || 'Could not delete credential.'),
  });

  const preferencesMutation = useMutation({
    mutationFn: (values: PreferencesInput) => savePreferences(values),
    onSuccess: (saved) => {
      const { updated_at: _updatedAt, ...values } = saved;
      setPreferenceValues(values);
      setPreferencesDirty(false);
      setPreferencesError('');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.preferences });
      toast('success', 'Generation defaults saved.');
    },
    onError: (error: Error) => {
      const apiError = error as SettingsApiError;
      setPreferencesError(preferenceFieldLabels[apiError.code ?? ''] ?? error.message ?? 'Could not save defaults.');
    },
  });

  const credentials = useMemo(() => new Map((credentialsQuery.data ?? []).map((credential) => [credential.provider_id, credential])), [credentialsQuery.data]);
  const providers = providersQuery.data ?? [];

  function updatePreference(field: keyof PreferencesInput, value: string | null) {
    setPreferenceValues((current) => current ? { ...current, [field]: value } : current);
    setPreferencesDirty(true);
    setPreferencesError('');
  }

  function updateProvider(field: 'default_text_provider' | 'default_image_provider', providerId: string) {
    const capability = field === 'default_text_provider' ? 'text' : 'image';
    const provider = providers.find((item) => item.provider_id === providerId);
    const firstModel = provider?.models.find((model) => model.capability === capability && model.enabled && model.implemented && !model.deprecated && model.available);
    updatePreference(field, providerId);
    if (firstModel) updatePreference(field === 'default_text_provider' ? 'default_text_model' : 'default_image_model', firstModel.model_id);
  }

  const preferencesLoading = preferencesQuery.isLoading || providersQuery.isLoading;

  return (
    <div className="max-w-5xl space-y-8">
      <header>
        <p className="eyebrow">Studio / 04</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Settings</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-white/60">Keep your local AI connections tidy, then choose the defaults ClipCraft should remember.</p>
      </header>

      <div className="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-white/[.08] bg-white/[.025] p-1" role="tablist" aria-label="Settings sections" onKeyDown={(event) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const current = sections.findIndex(([value]) => value === section);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? sections.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + sections.length) % sections.length;
        setSection(sections[next][0]);
        tabRefs.current[next]?.focus();
      }}>
        {sections.map(([value, label], index) => <button key={value} ref={(element) => { tabRefs.current[index] = element; }} type="button" role="tab" tabIndex={section === value ? 0 : -1} aria-selected={section === value} aria-controls={`settings-panel-${value}`} onClick={() => setSection(value)} className={`whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70 ${section === value ? 'bg-white/[.1] text-white' : 'text-white/60 hover:bg-white/[.05] hover:text-white/85'}`}>{label}</button>)}
      </div>

      {section === 'connections' && <section id="settings-panel-connections" role="tabpanel" aria-labelledby="connections-heading" className="space-y-5">
        <div><h2 id="connections-heading" className="text-lg font-semibold text-white">Provider connections</h2><p className="mt-1 text-sm text-white/60">Credentials stay encrypted on this local backend. ClipCraft never displays a saved secret.</p></div>
        {providersQuery.isLoading ? <LoadingState label="Loading providers" /> : providersQuery.isError ? <div className="rounded-2xl border border-rose-300/15 bg-rose-400/[.06] p-5 text-sm text-rose-100" role="alert">Could not load providers. <button type="button" className="ml-1 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70" onClick={() => void providersQuery.refetch()}>Try again</button></div> : <div className="grid gap-4 lg:grid-cols-2">{providers.map((provider) => <ProviderConnectionCard key={provider.provider_id} provider={provider} credential={credentials.get(provider.provider_id)} canConfigure={provider.enabled && (provider.implemented || provider.capabilities.includes('stock_media'))} testPending={testMutation.isPending && testMutation.variables === provider.provider_id} onConfigure={() => setCredentialProvider(provider)} onTest={() => testMutation.mutate(provider.provider_id)} onDelete={() => setDeleteProvider(provider)} />)}</div>}
      </section>}

      {section === 'defaults' && <section id="settings-panel-defaults" role="tabpanel" aria-labelledby="defaults-heading" className="space-y-5">
        <div><h2 id="defaults-heading" className="text-lg font-semibold text-white">Generation defaults</h2><p className="mt-1 text-sm text-white/60">Saved for your workspace. These settings are not wired into generation yet.</p></div>
        {preferencesLoading ? <LoadingState label="Loading defaults" /> : preferencesQuery.isError || !preferenceValues ? <div className="rounded-2xl border border-rose-300/15 bg-rose-400/[.06] p-5 text-sm text-rose-100" role="alert">Could not load defaults. <button type="button" className="ml-1 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70" onClick={() => void preferencesQuery.refetch()}>Try again</button></div> : <PreferencesSection providers={providers} values={preferenceValues} dirty={preferencesDirty} pending={preferencesMutation.isPending} error={preferencesError} onChange={(field, value) => field === 'default_text_provider' || field === 'default_image_provider' ? updateProvider(field, value ?? '') : updatePreference(field, value)} onSave={() => preferencesMutation.mutate(preferenceValues)} />}
      </section>}

      {section === 'workspace' && <section id="settings-panel-workspace" role="tabpanel" aria-labelledby="workspace-heading" className="space-y-5">
        <div><h2 id="workspace-heading" className="text-lg font-semibold text-white">Workspace preferences</h2><p className="mt-1 text-sm text-white/60">Small local choices for this browser and device.</p></div>
        <Panel className="divide-y divide-white/[.07]">
          <div className="flex items-start gap-4 p-6"><span className="grid size-9 place-items-center rounded-xl bg-violet-400/10 text-violet-200" aria-hidden="true"><Palette className="size-4" /></span><div className="flex-1"><h3 className="text-sm font-semibold text-white/90">Creative defaults</h3><p className="mt-1 text-xs leading-5 text-white/60">These local values continue to prefill the existing Generate form.</p><div className="mt-5 grid gap-4 sm:grid-cols-2"><label><span className="mb-2 block text-xs text-white/70">Default duration</span><Select value={settings.defaultDuration} onChange={(event) => settings.setSetting('defaultDuration', event.target.value)} aria-label="Default duration"><option value="15">15 seconds</option><option value="30">30 seconds</option><option value="45">45 seconds</option></Select></label><label><span className="mb-2 block text-xs text-white/70">Default style</span><Select value={settings.defaultStyle} onChange={(event) => settings.setSetting('defaultStyle', event.target.value)} aria-label="Default style"><option>Cinematic</option><option>Editorial</option><option>Minimal</option></Select></label></div></div></div>
          <div className="flex items-start gap-4 p-6"><span className="grid size-9 place-items-center rounded-xl bg-blue-400/10 text-blue-200" aria-hidden="true"><MonitorCog className="size-4" /></span><div className="flex-1"><h3 className="text-sm font-semibold text-white/90">Playback & accessibility</h3><p className="mt-1 text-xs leading-5 text-white/60">Control how previews behave on this device.</p><div className="mt-5 space-y-4"><Toggle label="Auto-generate captions" value={settings.autoCaptions} onChange={(value) => settings.setSetting('autoCaptions', value)} /><Toggle label="Reduce motion" value={settings.reduceMotion} onChange={(value) => settings.setSetting('reduceMotion', value)} /></div></div></div>
          <div className="flex flex-col items-start justify-between gap-4 p-6 sm:flex-row sm:items-center"><div><h3 className="text-sm font-semibold text-white/90">Local workspace</h3><p className="mt-1 text-xs text-white/60">Your existing local settings stay on this device.</p></div><Button type="button" className="w-full sm:w-auto" variant="secondary" icon={<Save className="size-4" />} onClick={() => toast('success', 'Workspace settings saved locally.')}>Save workspace</Button></div>
        </Panel>
      </section>}

      <CredentialDialog provider={credentialProvider} open={Boolean(credentialProvider)} pending={saveCredentialMutation.isPending} onClose={() => setCredentialProvider(null)} onSave={(secret, metadata) => credentialProvider && saveCredentialMutation.mutate({ providerId: credentialProvider.provider_id, secret, metadata })} />
      <Modal open={Boolean(deleteProvider)} onClose={() => !deleteMutation.isPending && setDeleteProvider(null)} title={`Delete ${deleteProvider?.display_name ?? ''} credential?`} description="This removes the encrypted credential from ClipCraft. You can add it again later." footer={<><Button type="button" variant="ghost" disabled={deleteMutation.isPending} onClick={() => setDeleteProvider(null)}>Cancel</Button><Button type="button" variant="danger" loading={deleteMutation.isPending} onClick={() => deleteProvider && deleteMutation.mutate(deleteProvider.provider_id)}>Delete credential</Button></>}>
        <p className="text-sm leading-6 text-white/70">Any future connection tests for this provider will require entering the credential again.</p>
      </Modal>
    </div>
  );
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) {
  return <button type="button" role="switch" aria-checked={value} className="flex w-full items-center justify-between rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70" onClick={() => onChange(!value)}><span className="text-sm text-white/75">{label}</span><span aria-hidden="true" className={`relative h-6 w-11 rounded-full transition ${value ? 'bg-violet-400' : 'bg-white/10'}`}><span className={`absolute top-1 size-4 rounded-full bg-white transition ${value ? 'left-6' : 'left-1'}`} /></span></button>;
}
