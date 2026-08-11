import { useEffect, useState } from 'react';
import { ArrowUpRight, Lightbulb } from 'lucide-react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { GenerateForm } from '../components/GenerateForm';
import { GenerationProgress } from '../components/GenerationProgress';
import { createVideo, getModelCapabilities } from '@/features/videos/api/videoService';
import { useVideoStore } from '@/features/videos/store/useVideoStore';
import { useToast } from '@/components/ui/Toast';
import type { ModelOption } from '@/features/videos/types';
import type { AiProvider, ProviderCapability } from '@/features/settings/types';
import { getPreferences } from '@/features/settings/api/settingsService';
import { useSettingsStore } from '@/features/settings/store/useSettingsStore';

function availableSelection(providers: AiProvider[], capability: ProviderCapability, preferredProvider?: string, preferredModel?: string, fallbackProvider?: string, fallbackModel?: string) {
  const candidates = providers.filter((provider) => provider.enabled && provider.implemented && provider.available && provider.capabilities.includes(capability));
  const provider = candidates.find((item) => item.provider_id === preferredProvider && item.models.some((model) => model.model_id === preferredModel && model.enabled && model.implemented && !model.deprecated && model.available))
    ?? candidates.find((item) => item.provider_id === fallbackProvider && item.models.some((model) => model.model_id === fallbackModel && model.enabled && model.implemented && !model.deprecated && model.available))
    ?? candidates.find((item) => item.models.some((model) => model.enabled && model.implemented && !model.deprecated && model.available));
  const models = provider?.models.filter((model) => model.capability === capability && model.enabled && model.implemented && !model.deprecated && model.available) ?? [];
  const model = provider?.provider_id === preferredProvider && models.some((item) => item.model_id === preferredModel) ? preferredModel : provider?.provider_id === fallbackProvider && models.some((item) => item.model_id === fallbackModel) ? fallbackModel : models[0]?.model_id;
  return { provider: provider?.provider_id, model };
}

export function GeneratePage() {
  const navigate = useNavigate();
  const { draft, initializeDraft } = useVideoStore();
  const { defaultDuration, defaultStyle } = useSettingsStore();
  const { toast } = useToast();
  const [progress, setProgress] = useState(0);
  const [generationError, setGenerationError] = useState('');

  const { data: modelData, isLoading: modelsLoading, isError: modelsError, refetch: refetchModels } = useQuery({
    queryKey: ['ai', 'models'],
    queryFn: getModelCapabilities,
    staleTime: 5 * 60 * 1000,
  });

  const preferencesQuery = useQuery({ queryKey: ['settings', 'preferences'], queryFn: getPreferences, staleTime: 5 * 60 * 1000 });

  useEffect(() => {
    if (!modelData || preferencesQuery.isLoading) return;
    const preferences = preferencesQuery.data;
    const text = availableSelection(modelData.providers, 'text', preferences?.default_text_provider, preferences?.default_text_model, modelData.defaults.text_provider, modelData.defaults.text_model);
    const image = availableSelection(modelData.providers, 'image', preferences?.default_image_provider, preferences?.default_image_model, modelData.defaults.image_provider, modelData.defaults.image_model);
    const pexels = modelData.providers.find((provider) => provider.provider_id === 'pexels');
    const visualSource = preferences?.default_visual_source === 'pexels' && pexels?.enabled && pexels.implemented && pexels.available ? 'pexels' : 'ai';
initializeDraft({
      text_provider: text.provider,
      text_model: text.model,
      image_provider: image.provider,
      image_model: image.model,
      visual_source: visualSource,
      duration: defaultDuration,
      style: defaultStyle,
      pexels_media_type: preferences?.default_pexels_media_type === 'video' ? 'video' : 'photo',
      pexels_orientation: preferences?.default_pexels_orientation === 'portrait' || preferences?.default_pexels_orientation === 'square' ? preferences.default_pexels_orientation : 'landscape',
    });
  }, [initializeDraft, modelData, preferencesQuery.data]);

  const textModels: ModelOption[] = modelData?.text_models ?? [];
  const imageModels: ModelOption[] = modelData?.image_models ?? [];

  const mutation = useMutation({
    mutationFn: createVideo,
    onMutate: () => { setGenerationError(''); setProgress(18); },
    onSuccess: (video) => {
      setProgress(100);
      window.setTimeout(() => navigate(`/library/${video.id}`), 450);
    },
    onError: (err: Error) => {
      setGenerationError(err.message || 'Failed to generate video. Try again.');
      toast('error', err.message || 'Failed to generate video');
      setProgress(0);
    },
  });

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div>
          <p className="eyebrow">Create / 01</p>
          <h1 className="mt-3 max-w-xl text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Turn a thought into a <span className="bg-gradient-to-r from-violet-200 to-blue-300 bg-clip-text text-transparent">moving story.</span>
          </h1>
          <p className="mt-4 max-w-lg text-sm leading-6 text-white/45">
            Describe the feeling, message, or moment. ClipCraft will shape it into a cinematic short.
          </p>
        </div>
        <Button variant="ghost" icon={<ArrowUpRight className="size-4" />} onClick={() => navigate('/library')}>
          View library
        </Button>
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.12fr)_minmax(340px,.88fr)]">
        <GenerateForm
          loading={mutation.isPending}
          onSubmit={() => mutation.mutate(draft)}
          textModels={textModels}
          imageModels={imageModels}
          providers={modelData?.providers ?? []}
          modelsLoading={modelsLoading}
          modelsError={modelsError}
          error={generationError}
          onRetryModels={() => { void refetchModels(); void preferencesQuery.refetch(); }}
        />
        <GenerationProgress
          progress={mutation.isSuccess ? progress : mutation.isPending ? progress : 0}
          active={mutation.isPending || mutation.isSuccess}
          title={draft.title}
        />
      </div>
      <div className="flex items-start gap-3 rounded-xl border border-violet-300/10 bg-violet-400/[.045] px-4 py-3 text-xs leading-5 text-white/45">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-violet-200" />
        <span>
          <b className="font-medium text-white/70">Prompt tip:</b> Include a subject, a mood, and the kind of movement you want to see.
        </span>
      </div>
    </div>
  );
}
