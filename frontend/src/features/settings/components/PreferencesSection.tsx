import type { ReactNode } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Panel } from '@/components/ui/Panel';
import { Select } from '@/components/ui/Select';
import type { AiProvider, PreferencesInput, ProviderCapability } from '../types';

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
  const textProviders = usableProviders(providers, 'text', values.default_text_provider);
  const imageProviders = usableProviders(providers, 'image', values.default_image_provider);
  const textModels = usableModels(providers, values.default_text_provider, 'text', values.default_text_model);
  const imageModels = usableModels(providers, values.default_image_provider, 'image', values.default_image_model);
  const valid = textProviders.some((provider) => provider.provider_id === values.default_text_provider)
    && textModels.some((model) => model.model_id === values.default_text_model)
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
          <FieldLabel label="Default text model"><Select value={values.default_text_model} onChange={(event) => onChange('default_text_model', event.target.value)} aria-label="Default text model">{textModels.map((model) => <option key={model.model_id} value={model.model_id} disabled={!model.available}>{model.display_name}{!model.available ? ' (credential needed)' : ''}</option>)}</Select></FieldLabel>
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
