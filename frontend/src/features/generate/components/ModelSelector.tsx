import { Select } from '@/components/ui/Select';
import type { ModelOption } from '@/features/videos/types';

interface Props {
  label: string;
  models: ModelOption[];
  selectedProvider: string;
  selectedModel: string;
  onChange: (provider: string, model: string) => void;
  providerLabels?: Record<string, string>;
  loading?: boolean;
}

export function ModelSelector({ label, models, selectedProvider, selectedModel, onChange, providerLabels = {}, loading }: Props) {
  const providers = [...new Set(models.filter((model) => model.available).map((model) => model.provider))];
  const providerModels = models.filter((model) => model.provider === selectedProvider && model.available);
  const currentModel = providerModels.some((model) => model.model === selectedModel) ? selectedModel : '';

  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 block text-xs font-medium text-white/70">{label}</legend>
      {providers.length === 0 && !loading && <p className="rounded-lg border border-amber-300/15 bg-amber-400/[.06] px-3 py-2 text-xs leading-5 text-amber-100" role="status">No configured {label.toLowerCase()} provider is available. <a className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70" href="/settings">Open Settings</a></p>}
      {loading ? (
        <div className="space-y-2" aria-busy="true" aria-label={`Loading ${label.toLowerCase()} options`}><div className="h-10 animate-pulse rounded-lg border border-white/10 bg-white/5" /><div className="h-10 animate-pulse rounded-lg border border-white/10 bg-white/5" /></div>
      ) : (
        <div className="space-y-3">
          <label className="block"><span className="sr-only">{label} provider</span><Select value={selectedProvider} onChange={(event) => { const provider = event.target.value; const firstModel = models.find((model) => model.provider === provider && model.available); onChange(provider, firstModel?.model ?? ''); }} aria-label={`${label} provider`}><option value="">Choose provider</option>{providers.map((provider) => <option key={provider} value={provider}>{providerLabels[provider] ?? provider}</option>)}</Select></label>
          <label className="block"><span className="sr-only">{label} model</span><Select value={currentModel} onChange={(event) => onChange(selectedProvider, event.target.value)} disabled={!selectedProvider || providerModels.length === 0} aria-label={`${label} model`}><option value="">Choose model</option>{providerModels.map((model) => <option key={model.model} value={model.model}>{model.display_name}{model.is_default ? ' — Default' : ''}</option>)}</Select></label>
        </div>
      )}
      {currentModel && (
        <p className="mt-1.5 text-[11px] leading-snug text-white/45">
          {providerModels.find((model) => model.model === currentModel)?.description ?? ''}
        </p>
      )}
    </fieldset>
  );
}
