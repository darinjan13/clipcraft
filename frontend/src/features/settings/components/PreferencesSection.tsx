import type { ReactNode } from 'react';
import { useState } from 'react';
import { SlidersHorizontal, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Panel } from '@/components/ui/Panel';
import { Select } from '@/components/ui/Select';
import type { AiProvider, PreferencesInput, ProviderCapability } from '../types';
import { discoverNvidiaModels } from '../api/settingsService';

type Props = {
  providers: AiProvider[];
  values: PreferencesInput;
  dirty: boolean;
  pending: boolean;
  error?: string;
  onChange: (field: keyof PreferencesInput, value: string | null) => void;
  onSave: () => void;
};

function usableProviders(providers: AiProvider[], capability: ProviderCapability, selectedProvider: string) {
  return providers.filter((provider) => provider.enabled && provider.implemented && provider.capabilities.includes(capability) && (provider.available || provider.provider_id === selectedProvider));
}

function usableModels(providers: AiProvider[], providerId: string, capability: ProviderCapability, selectedModel: string) {
  return providers.find((provider) => provider.provider_id === providerId)?.models.filter((model) => model.enabled && model.implemented && !model.deprecated && model.capability === capability && (model.available || model.model_id === selectedModel)) ?? [];
}

function FieldLabel({ label, children, error }: { label: string; children: ReactNode; error?: string }) {
  return <label className="block"><span className="mb-2 block text-xs font-medium text-white/75">{label}</span>{children}{error && <span className="mt-2 block text-xs text-rose-200" role="alert">{error}</span>}</label>;
}

export function PreferencesSection({ providers, values, dirty, pending, error, onChange, onSave }: Props) {
  const [discoveringNvidia, setDiscoveringNvidia] = useState(false);
  const [discoveredNvidiaModels, setDiscoveredNvidiaModels] = useState<{ id: string; name: string; description?: string }[]>([]);
  const [discoverError, setDiscoverError] = useState<string | null>(null);

  const handleDiscoverNvidia = async () => {
    setDiscoveringNvidia(true);
    setDiscoverError(null);
    try {
      const { models } = await discoverNvidiaModels();
      // Filter for text generation models only
      const textModels = models.filter((model: any) => 
        model.id && (
          model.id.includes('llama') || 
          model.id.includes('nemotron') || 
          model.id.includes('text') ||
          (model.capabilities && model.capabilities.includes('text'))
        )
      );
      const formattedModels = textModels.map((model: any) => ({
        id: model.id,
        name: model.name || model.id,
        description: model.description || '',
      }));
      setDiscoveredNvidiaModels(formattedModels);
    } catch (err) {
      setDiscoverError(err instanceof Error ? err.message : 'Failed to discover NVIDIA models');
    } finally {
      setDiscoveringNvidia(false);
    }
  };

  const textProviders = usableProviders(providers, 'text', values.default_text_provider);
  const imageProviders = usableProviders(providers, 'image', values.default_image_provider);
  const textModels = usableModels(providers, values.default_text_provider, 'text', values.default_text_model);
  const imageModels = usableModels(providers, values.default_image_provider, 'image', values.default_image_model);
  
  // Merge discovered NVIDIA models into the text models if NVIDIA is the selected provider
  const mergedTextModels = values.default_text_provider === 'nvidia' && discoveredNvidiaModels.length > 0
    ? [...textModels, ...discoveredNvidiaModels.map(m => ({
        model_id: m.id,
        display_name: m.name,
        capability: 'text' as const,
        implemented: true,
        enabled: true,
        deprecated: false,
        available: true,
        description: m.description,
      }))]
    : textModels;

  const valid = textProviders.some((provider) => provider.provider_id === values.default_text_provider)
    && mergedTextModels.some((model) => model.model_id === values.default_text_model)
    && imageProviders.some((provider) => provider.provider_id === values.default_image_provider)
    && imageModels.some((model) => model.model_id === values.default_image_model)
    && values.default_visual_source === 'ai';

  return (
    <Panel className="overflow-hidden">
      <div className="flex items-start gap-4 border-b border-white/[.07] p-6">
        <span className="grid size-9 place-items-center rounded-xl bg-blue-400/10 text-blue-200" aria-hidden="true"><SlidersHorizontal className="size-4" /></span>
        <div className="flex-1">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div><p className="text-sm font-semibold text-white">Provider and model selection</p><p className="mt-1 text-xs leading-5 text-white/60">These preferences are saved for the next Settings update. Generation still uses its current defaults until routing is enabled.</p></div>
            {dirty && <span className="rounded-full bg-violet-400/10 px-2.5 py-1 text-[11px] font-medium text-violet-200">Unsaved changes</span>}
          </div>
        </div>
      </div>
      <div className="space-y-6 p-6">
        {error && <p className="rounded-xl border border-rose-300/15 bg-rose-400/[.06] px-3 py-2.5 text-sm text-rose-100" role="alert">{error}</p>}
        <div className="grid gap-5 sm:grid-cols-2">
          <FieldLabel label="Default text provider"><Select value={values.default_text_provider} onChange={(event) => onChange('default_text_provider', event.target.value)} aria-label="Default text provider">{textProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id} disabled={!provider.available}>{provider.display_name}{!provider.available ? ' (credential needed)' : ''}</option>)}</Select></FieldLabel>
          <FieldLabel label="Default text model">
            <Select value={values.default_text_model} onChange={(event) => onChange('default_text_model', event.target.value)} aria-label="Default text model">
              {mergedTextModels.map((model) => (
                <option key={model.model_id} value={model.model_id} disabled={!model.available}>
                  {model.display_name}{!model.available ? ' (credential needed)' : ''}
                </option>
              ))}
            </Select>
            {values.default_text_provider === 'nvidia' && (
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    loading={discoveringNvidia}
                    onClick={handleDiscoverNvidia}
                    disabled={discoveringNvidia}
                    icon={<RefreshCw className="size-3.5" />}
                    className="h-8 px-3 text-xs"
                  >
                    Discover NVIDIA Models
                  </Button>
                  {discoverError && <span className="text-xs text-rose-200">{discoverError}</span>}
                  {discoveredNvidiaModels.length > 0 && (
                    <span className="text-xs text-emerald-200">
                      Found {discoveredNvidiaModels.length} models
                    </span>
                  )}
                </div>
                {discoveredNvidiaModels.length > 0 && (
                  <details className="rounded-lg border border-white/10 bg-black/20 p-3">
                    <summary className="text-xs font-medium text-white/70 cursor-pointer">
                      Discovered NVIDIA Models ({discoveredNvidiaModels.length})
                    </summary>
                    <ul className="mt-2 space-y-1">
                      {discoveredNvidiaModels.map((model) => (
                        <li key={model.id} className="text-xs text-white/70 flex items-center gap-2">
                          <code className="rounded bg-white/5 px-1.5 py-0.5 text-[10px]">{model.id}</code>
                          <span>{model.name}</span>
                          {model.description && <span className="text-white/40">— {model.description}</span>}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-[11px] text-white/40">
                      Select a model from the dropdown above. Models marked as available will be used for generation.
                    </p>
                  </details>
                )}
              </div>
            )}
          </FieldLabel>
          <FieldLabel label="Default visual source"><div className="flex h-11 items-center rounded-lg border border-white/10 bg-[#111113] px-3.5 text-sm text-white/80" role="textbox" aria-readonly="true" aria-label="Default visual source">AI-generated visuals</div></FieldLabel>
          <FieldLabel label="Default image provider"><Select value={values.default_image_provider} onChange={(event) => onChange('default_image_provider', event.target.value)} aria-label="Default image provider">{imageProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id} disabled={!provider.available}>{provider.display_name}{!provider.available ? ' (credential needed)' : ''}</option>)}</Select></FieldLabel>
          <FieldLabel label="Default image model"><Select value={values.default_image_model} onChange={(event) => onChange('default_image_model', event.target.value)} aria-label="Default image model">{imageModels.map((model) => <option key={model.model_id} value={model.model_id} disabled={!model.available}>{model.display_name}{!model.available ? ' (credential needed)' : ''}</option>)}</Select></FieldLabel>
        </div>
        <p className="text-xs leading-5 text-white/55">Stock media defaults will appear here when Pexels support is implemented.</p>
        <div className="flex flex-col items-start justify-between gap-3 border-t border-white/[.07] pt-5 sm:flex-row sm:items-center">
          <p className="text-xs text-white/50">{dirty ? 'Save to keep these defaults in your local workspace.' : 'All defaults are saved.'}</p>
          <Button type="button" className="w-full sm:w-auto" variant="primary" loading={pending} disabled={!dirty || !valid} onClick={onSave}>Save defaults</Button>
        </div>
      </div>
    </Panel>
  );
}
