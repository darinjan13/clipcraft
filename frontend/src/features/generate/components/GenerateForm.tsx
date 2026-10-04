import { useQuery } from '@tanstack/react-query';
import { Cpu, WandSparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Panel } from '@/components/ui/Panel';
import { Select } from '@/components/ui/Select';
import { listMusic } from '@/features/settings/api/settingsService';
import { settingsKeys } from '@/features/settings/api/queryKeys';
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
  const musicQuery = useQuery({ queryKey: settingsKeys.music, queryFn: listMusic, staleTime: 60 * 1000 });
  const musicTracks = musicQuery.data ?? [];
  const providerLabels = Object.fromEntries(providers.map((provider) => [provider.provider_id, provider.display_name]));

  // Voice Source (automatic vs third-party TTS) comes from the draft.

  const voiceMatch = /^(.*) \((female|male)\)$/.exec(draft.voice);
  const voiceVibe = voiceMatch ? voiceMatch[1] : draft.voice;
  const voiceGender = voiceMatch ? voiceMatch[2] : 'female';
  const setVoice = (vibe: string, gender: string) => setDraft({ voice: vibe === 'Tagalog narrator' ? 'Tagalog narrator' : `${vibe} (${gender})` });

  return (
    <Panel className="p-5 sm:p-7">
      <div className="mb-6 flex items-start justify-between">
        <div><p className="eyebrow">Creative brief</p><h2 className="mt-2 text-lg font-semibold text-white">Shape your next video</h2></div>
        <span className="rounded-lg bg-violet-400/10 p-2 text-violet-200"><WandSparkles className="size-4" /></span>
      </div>
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        {error && <p className="rounded-lg border border-rose-300/15 bg-rose-400/[.06] px-3 py-2 text-xs leading-5 text-rose-100" role="alert">{error}</p>}
        <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">Working title</span><Input value={draft.title} onChange={(event) => setDraft({ title: event.target.value })} placeholder="Give this idea a name" /></label>
        <div className="flex gap-2" role="group" aria-label="Generation mode">
          {(['creative', 'story'] as const).map((mode) => (
            <button key={mode} type="button" onClick={() => setDraft({ mode })} aria-pressed={(draft.mode ?? 'creative') === mode} className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium capitalize transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300/70 ${(draft.mode ?? 'creative') === mode ? 'border-violet-300/50 bg-violet-400/10 text-white' : 'border-white/10 bg-black/20 text-white/55 hover:text-white'}`}>{mode === 'creative' ? 'Creative' : 'Story'}</button>
          ))}
        </div>
        {(draft.mode ?? 'creative') === 'story' ? (
          <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">Paste your story <span className="text-white/35">({(draft.story_text ?? '').length}/3000)</span></span><textarea value={draft.story_text ?? ''} maxLength={3000} onChange={(event) => setDraft({ story_text: event.target.value })} placeholder="Paste the full story text here. It will be narrated word-for-word..." className="min-h-36 w-full resize-none rounded-lg border border-white/10 bg-black/20 p-3.5 text-sm leading-6 text-white outline-none placeholder:text-white/25 focus:border-violet-300/50" /></label>
        ) : (
          <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">What should we make?</span><textarea value={draft.prompt} onChange={(event) => setDraft({ prompt: event.target.value })} placeholder="Describe the story, mood, and visual direction..." className="min-h-36 w-full resize-none rounded-lg border border-white/10 bg-black/20 p-3.5 text-sm leading-6 text-white outline-none placeholder:text-white/25 focus:border-violet-300/50" /></label>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {(draft.mode ?? 'creative') === 'story' ? (
            <div><span className="mb-2 block text-xs font-medium text-white/55">Duration</span><p className="rounded-lg border border-white/10 bg-black/20 px-3.5 py-2.5 text-sm text-white/70">≈ {(() => { const words = (draft.story_text ?? '').trim().split(/\s+/).filter(Boolean).length; const secs = Math.round(words / 140 * 60); return `${Math.floor(secs / 60)} min ${secs % 60} sec`; })()} — follows your story</p></div>
          ) : (
            <label><span className="mb-2 block text-xs font-medium text-white/55">Duration</span><Select value={draft.duration} onChange={(event) => setDraft({ duration: event.target.value })}><option value="30">30 seconds</option><option value="45">45 seconds</option><option value="60">60 seconds</option><option value="90">90 seconds</option></Select></label>
          )}
          <label><span className="mb-2 block text-xs font-medium text-white/55">Visual style</span><Select value={draft.style} onChange={(event) => setDraft({ style: event.target.value })}><option>Cinematic</option><option>Editorial</option><option>Minimal</option><option>Documentary</option></Select></label>
          <label><span className="mb-2 block text-xs font-medium text-white/55">Mood</span><Select value={draft.mood ?? ''} onChange={(event) => setDraft({ mood: (event.target.value || undefined) as 'horror' | 'mystery' | 'dark' | undefined })} aria-label="Mood"><option value="">None</option><option value="horror">Horror</option><option value="mystery">Mystery</option><option value="dark">Dark</option></Select></label>
          {(draft.audio_mode ?? 'automatic') === 'automatic' && <div className="grid gap-4 sm:grid-cols-2"><label><span className="mb-2 block text-xs font-medium text-white/55">Voice</span><Select value={voiceVibe} onChange={(event) => setVoice(event.target.value, voiceGender)}><option>Warm narrator</option><option>Studio neutral</option><option>Energetic guide</option><option>Dark narrator</option><option>Tagalog narrator</option></Select></label>{voiceVibe !== 'Tagalog narrator' && <label><span className="mb-2 block text-xs font-medium text-white/55">Gender</span><Select value={voiceGender} onChange={(event) => setVoice(voiceVibe, event.target.value)}><option value="female">Female</option><option value="male">Male</option></Select></label>}</div>}
          <label><span className="mb-2 block text-xs font-medium text-white/55">Voice Source</span><Select value={draft.audio_mode ?? 'automatic'} onChange={(event) => setDraft({ audio_mode: event.target.value as 'automatic' | 'custom_audio' })} aria-label="Voice source"><option value="automatic">Automatic</option><option value="custom_audio">Third-Party TTS</option></Select></label>
          <label><span className="mb-2 block text-xs font-medium text-white/55">Captions</span><Select value={draft.captions} onChange={(event) => setDraft({ captions: event.target.value })}><option>Clean</option><option>Bold highlighted words</option><option>Minimal</option></Select></label>
          <label><span className="mb-2 block text-xs font-medium text-white/55">Music bed</span><Select value={draft.music_track ?? ''} onChange={(event) => setDraft({ music_track: event.target.value || undefined })}><option value="">No music</option>{musicTracks.map((track) => <option key={track.name} value={track.name}>{track.name}</option>)}</Select></label>
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
            <label><span className="mb-2 block text-xs font-medium text-white/70">Visual source</span><Select value={draft.visual_source ?? 'ai'} onChange={(event) => setDraft({ visual_source: event.target.value as 'ai' | 'pexels' | 'pixabay' })} aria-describedby="visual-source-help"><option value="ai">AI-generated images</option><option value="pexels">Pexels stock media</option><option value="pixabay">Pixabay stock media</option></Select><span id="visual-source-help" className="mt-1.5 block text-[11px] leading-snug text-white/45">Stock media needs a saved {draft.visual_source === 'pixabay' ? 'Pixabay' : 'Pexels'} key in Settings → Provider credentials.</span></label>
            {draft.visual_source === 'pexels' ? <><label><span className="mb-2 block text-xs font-medium text-white/70">Pexels media type</span><Select value={draft.pexels_media_type ?? 'photo'} onChange={(event) => setDraft({ pexels_media_type: event.target.value as 'photo' | 'video' | 'both' })}><option value="photo">Photos</option><option value="video">Videos</option><option value="both">Mix photos & videos</option></Select></label><label><span className="mb-2 block text-xs font-medium text-white/70">Pexels orientation</span><Select value={draft.pexels_orientation ?? 'landscape'} onChange={(event) => setDraft({ pexels_orientation: event.target.value as 'landscape' | 'portrait' | 'square' })}><option value="landscape">Landscape</option><option value="portrait">Portrait</option><option value="square">Square</option></Select></label></> : null}
            {draft.visual_source === 'pixabay' ? <><label><span className="mb-2 block text-xs font-medium text-white/70">Pixabay media type</span><Select value={draft.pixabay_media_type ?? 'photo'} onChange={(event) => setDraft({ pixabay_media_type: event.target.value as 'photo' | 'video' | 'both' })}><option value="photo">Photos</option><option value="video">Videos</option><option value="both">Mix photos & videos</option></Select></label><label><span className="mb-2 block text-xs font-medium text-white/70">Pixabay orientation</span><Select value={draft.pixabay_orientation ?? 'landscape'} onChange={(event) => setDraft({ pixabay_orientation: event.target.value as 'landscape' | 'portrait' | 'square' })}><option value="landscape">Landscape</option><option value="portrait">Portrait</option><option value="square">Square</option></Select></label></> : null}
          </div>

          {(draft.audio_mode ?? 'automatic') === 'custom_audio' ? (
            <div className="mb-4 p-3 rounded-lg border border-white/10 bg-black/20">
              <p className="text-xs font-medium text-white/70 mb-2">Third-Party TTS</p>
              <p className="text-[11px] text-white/50 mb-3">
                ClipCraft will generate a script for export, then pause for your MP3/WAV upload.
              </p>
              <label className="block"><span className="mb-2 block text-xs font-medium text-white/55">Narration Export Style</span><Select value={draft.narration_export_style ?? 'clean'} onChange={(event) => setDraft({ narration_export_style: event.target.value as 'clean' | 'expressive' })} aria-label="Narration Export Style"><option value="clean">Clean</option><option value="expressive">Expressive</option></Select><span className="mt-1.5 block text-[11px] leading-snug text-white/40">Clean exports spoken text only. Expressive adds sparse delivery cues.</span></label>
            </div>
          ) : null}

          <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center"><span className="text-xs text-white/45">9:16 vertical format</span><Button type="submit" className="w-full sm:w-auto" loading={loading} disabled={Boolean(modelsError || modelsLoading || ((draft.mode ?? 'creative') === 'story' ? !(draft.story_text ?? '').trim() : !draft.prompt.trim()) || !draft.text_provider || !draft.text_model || (draft.visual_source !== 'pexels' && draft.visual_source !== 'pixabay' && (!draft.image_provider || !draft.image_model)))} icon={<WandSparkles className="size-4" />}>Generate video</Button></div>
        </div>
      </form>
    </Panel>
  );
}