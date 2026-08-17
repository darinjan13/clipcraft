import { Cpu, WandSparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Panel } from '@/components/ui/Panel';
import { Select } from '@/components/ui/Select';
import { useVideoStore } from '@/features/videos/store/useVideoStore';
import type { ModelOption } from '@/features/videos/types';
import type { AiProvider } from '@/features/settings/types';
import { ModelSelector } from './ModelSelector';

interface Props {
  onSubmit: () => void;
  loading: boolean;
  textModels: ModelOption[];
  imageModels: ModelOption[];
  modelsLoading: boolean;
  modelsError?: boolean;
  onRetryModels: () => void;
  providers: AiProvider[];
  error?: string;
}

export function GenerateForm({ onSubmit, loading, textModels, imageModels, modelsLoading, modelsError, onRetryModels, providers, error }: Props) {
  const { draft, setDraft } = useVideoStore();
  const providerLabels = Object.fromEntries(providers.map((provider) => [provider.provider_id, provider.display_name]));

  return (
    <Panel className="p-5 sm:p-7">
      <div className="mb-6 flex items-start justify-between">
        <div><p className="eyebrow">Creative brief</p><h2 className="mt-2 text-lg font-semibold text-white">Shape your next video</h2></div>
        <span className="rounded-lg bg-violet-400/10 p-2 text-violet-200"><WandSparkles className="size-4" /></span>
      </div>
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        {error && <p className="rounded-lg border border-rose-300/15 bg-rose-400/[.06] px-3 py-2 text-xs leading-5 text-rose-100" role="alert">{error}</p>}
        <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">Working title</span><Input value={draft.title} onChange={(event) => setDraft({ title: event.target.value })} placeholder="Give this idea a name" /></label>
        <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">What should we make?</span><textarea value={draft.prompt} onChange={(event) => setDraft({ prompt: event.target.value })} placeholder="Describe the story, mood, and visual direction..." className="min-h-36 w-full resize-none rounded-lg border border-white/10 bg-black/20 p-3.5 text-sm leading-6 text-white outline-none placeholder:text-white/25 focus:border-violet-300/50" /></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label><span className="mb-2 block text-xs font-medium text-white/55">Duration</span><Select value={draft.duration} onChange={(event) => setDraft({ duration: event.target.value })}><option value="30">30 seconds</option><option value="45">45 seconds</option><option value="60">60 seconds</option><option value="90">90 seconds</option></Select></label>
          <label><span className="mb-2 block text-xs font-medium text-white/55">Visual style</span><Select value={draft.style} onChange={(event) => setDraft({ style: event.target.value })}><option>Cinematic</option><option>Editorial</option><option>Minimal</option><option>Documentary</option></Select></label>
          <label><span className="mb-2 block text-xs font-medium text-white/55">Voice</span><Select value={draft.voice} onChange={(event) => setDraft({ voice: event.target.value })}><option>Warm narrator</option><option>Studio neutral</option><option>Energetic guide</option></Select></label>
          <label><span className="mb-2 block text-xs font-medium text-white/55">Captions</span><Select value={draft.captions} onChange={(event) => setDraft({ captions: event.target.value })}><option>Clean</option><option>Bold highlighted words</option><option>Minimal</option></Select></label>
        </div>

        <div className="border-t border-white/[.07] pt-5">
          <div className="mb-4 flex items-center gap-2">
            <Cpu className="size-3.5 text-white/35" />
            <span className="text-xs font-semibold text-white/55">AI Models</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <ModelSelector
              label="Text model"
              models={textModels}
              selectedProvider={draft.text_provider ?? ''}
              selectedModel={draft.text_model ?? ''}
              onChange={(provider, model) => setDraft({ text_provider: provider, text_model: model })}
              providerLabels={providerLabels}
              loading={modelsLoading}
            />
            <ModelSelector
              label="Image model"
              models={imageModels}
              selectedProvider={draft.image_provider ?? ''}
              selectedModel={draft.image_model ?? ''}
              onChange={(provider, model) => setDraft({ image_provider: provider, image_model: model })}
              providerLabels={providerLabels}
              loading={modelsLoading}
            />
          </div>
          {modelsError && <p className="mt-4 rounded-lg border border-rose-300/15 bg-rose-400/[.06] px-3 py-2 text-xs leading-5 text-rose-100" role="alert">AI options could not be loaded. <button type="button" className="ml-1 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70" onClick={onRetryModels}>Try again</button></p>}
        </div>

        <div className="border-t border-white/[.07] pt-5">
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <label><span className="mb-2 block text-xs font-medium text-white/70">Visual source</span><Select value={draft.visual_source ?? 'ai'} onChange={(event) => setDraft({ visual_source: event.target.value as 'ai' | 'pexels' })} aria-describedby="visual-source-help"><option value="ai">AI-generated images</option><option value="pexels" disabled>Pexels stock media (unavailable)</option></Select><span id="visual-source-help" className="mt-1.5 block text-[11px] leading-snug text-white/45">Stock media becomes selectable when a supported Pexels connection is available.</span></label>
            {draft.visual_source === 'pexels' ? <><label><span className="mb-2 block text-xs font-medium text-white/70">Pexels media type</span><Select value={draft.pexels_media_type ?? 'photo'} onChange={(event) => setDraft({ pexels_media_type: event.target.value as 'photo' | 'video' })}><option value="photo">Photos</option><option value="video">Videos</option></Select></label><label><span className="mb-2 block text-xs font-medium text-white/70">Pexels orientation</span><Select value={draft.pexels_orientation ?? 'landscape'} onChange={(event) => setDraft({ pexels_orientation: event.target.value as 'landscape' | 'portrait' | 'square' })}><option value="landscape">Landscape</option><option value="portrait">Portrait</option><option value="square">Square</option></Select></label></> : null}
          </div>

          <div className="mb-4">
            <label className="block">
              <span className="mb-2 block text-xs font-medium text-white/55">Voice Source</span>
              <Select value={draft.audio_mode ?? 'automatic'} onChange={(event) => setDraft({ audio_mode: event.target.value as 'automatic' | 'custom_audio' })} aria-label="Voice source">
                <option value="automatic">Automatic (ClipCraft TTS)</option>
                <option value="custom_audio">Custom Audio (Upload your own)</option>
              </Select>
              <span className="mt-1.5 block text-[11px] leading-snug text-white/40">
                Automatic: ClipCraft generates narration. Custom: Generate script first, then upload your own MP3/WAV (e.g., from ElevenLabs).
              </span>
            </label>
          </div>

          {draft.audio_mode === 'custom_audio' ? (
            <div className="mb-4 p-3 rounded-lg border border-white/10 bg-black/20">
              <p className="text-xs font-medium text-white/70 mb-2">Custom Audio Mode</p>
              <p className="text-[11px] text-white/50 mb-3">
                ClipCraft will generate the script, then pause for you to upload your own narration audio (MP3/WAV).
                The uploaded audio duration will determine the final video length.
              </p>
              <label className="block text-xs font-medium text-white/50 mb-1">Voice reference (for script generation only)</label>
              <Select value={draft.voice} onChange={(event) => setDraft({ voice: event.target.value })} aria-label="Voice reference for script generation">
                <option value="Warm narrator">Warm narrator</option>
                <option value="Studio neutral">Studio neutral</option>
                <option value="Energetic guide">Energetic guide</option>
              </Select>
              <p className="mt-1 text-[10px] text-white/40">Voice selection affects script style only. Your uploaded audio will be used for the final video.</p>
            </div>
          ) : (
            <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">Voice</span><Select value={draft.voice} onChange={(event) => setDraft({ voice: event.target.value })}><option>Warm narrator</option><option>Studio neutral</option><option>Energetic guide</option></Select></label>
          )}

          <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center"><span className="text-xs text-white/45">9:16 vertical format</span><Button type="submit" className="w-full sm:w-auto" loading={loading} disabled={Boolean(modelsError || modelsLoading || !draft.prompt.trim() || !draft.text_provider || !draft.text_model || (draft.visual_source !== 'pexels' && (!draft.image_provider || !draft.image_model)))} icon={<WandSparkles className="size-4" />}>Generate video</Button></div>
        </div>
      </form>
    </Panel>
  );
}
