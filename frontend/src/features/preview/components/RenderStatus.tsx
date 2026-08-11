import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, LoaderCircle, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Panel } from '@/components/ui/Panel';
import { Progress } from '@/components/ui/Progress';
import type { PipelineStatus, Video } from '@/features/videos/types';
import { elapsed as calcElapsed, currentStageIndex, errorDisplay, formatElapsed, isStale, STAGES, STALE_AFTER_MS } from '../pipeline';

type StageState = 'pending' | 'active' | 'completed' | 'failed';

function stageState(status: PipelineStatus | null | undefined, stageId: string): StageState {
  if (!status) return 'pending';
  const stageIdx = STAGES.findIndex((s) => s.id === stageId);

  if (status.status === 'completed') return 'completed';

  const currentIdx = currentStageIndex(status);
  if (status.status === 'failed') {
    if (stageIdx < currentIdx) return 'completed';
    if (stageIdx === currentIdx) return 'failed';
    return 'pending';
  }
  if (stageIdx < currentIdx) return 'completed';
  if (stageIdx === currentIdx) return 'active';
  return 'pending';
}

function statusTone(status: string) {
  if (status === 'completed') return 'green' as const;
  if (status === 'failed') return 'amber' as const;
  return 'violet' as const;
}

function stageIcon(state: StageState) {
  if (state === 'completed') return <CheckCircle2 className="size-4" />;
  if (state === 'failed') return <XCircle className="size-4" />;
  if (state === 'active') return <LoaderCircle className="size-4 animate-spin" />;
  return <Clock3 className="size-4" />;
}

function stageStateColor(state: StageState) {
  if (state === 'completed') return 'bg-emerald-400/10 text-emerald-200';
  if (state === 'failed') return 'bg-rose-400/10 text-rose-200';
  if (state === 'active') return 'bg-violet-400/10 text-violet-200';
  return 'bg-white/[.06] text-white/25';
}

function stageImageText(progress: PipelineStatus['image_progress'] | undefined): string {
  if (!progress || progress.total === 0) return '';
  return `Image ${progress.completed} of ${progress.total}${progress.failed > 0 ? ` (${progress.failed} failed)` : ''}`;
}

export function RenderStatus({ video, pipeline }: { video: Video; pipeline?: PipelineStatus | null }) {
  const terminal = video.status === 'completed' || video.status === 'failed';
  const staleActive = !!pipeline && isStale(pipeline);
  const elapsedSeconds = pipeline ? calcElapsed(pipeline.created_at, pipeline.updated_at, terminal) : 0;

  return (
    <Panel className="p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow">Pipeline activity</p>
          <h2 className="mt-2 text-lg font-semibold text-white">
            {video.status === 'completed'
              ? 'Ready to share'
              : video.status === 'failed'
              ? 'Generation failed'
              : 'Creating your video'}
          </h2>
        </div>
        <Badge tone={statusTone(video.status)}>{pipeline?.display_status ?? video.status}</Badge>
      </div>

      {staleActive && !terminal && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="size-3.5" />
          <span>No update in over {STALE_AFTER_MS / 1000}s. The pipeline may have stalled.</span>
        </div>
      )}

      <div className="mt-5 flex gap-5 border-b border-white/[.07] pb-4 font-mono text-[10px] text-white/35">
        <span className="flex items-center gap-1"><Clock3 className="size-3" />{formatElapsed(elapsedSeconds)}</span>
        {pipeline?.updated_at && (
          <span>Updated {formatElapsed((Date.now() - new Date(pipeline.updated_at).getTime()) / 1000)} ago</span>
        )}
      </div>

      <div className="mt-5">
        <div className="mb-2 flex justify-between font-mono text-[10px] text-white/35">
          <span>Overall progress</span>
          <span>{video.progress}%</span>
        </div>
        <Progress value={video.progress} />
      </div>

      <div className="mt-6 space-y-1">
        {STAGES.map((stage) => {
          const state = stageState(pipeline, stage.id);
          const imageInfo = stage.id === 'generate_images' ? stageImageText(pipeline?.image_progress) : null;
          return (
            <div key={stage.id} className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-sm">
              <span className={`grid size-7 shrink-0 place-items-center rounded-full ${stageStateColor(state)}`}>
                {stageIcon(state)}
              </span>
              <span className={state === 'pending' ? 'text-white/20' : 'text-white/75'}>{stage.label}</span>
              {imageInfo && <span className="ml-auto text-[11px] text-white/30 font-mono">{imageInfo}</span>}
            </div>
          );
        })}
      </div>

      {pipeline?.assets && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-white/[.07] pt-5">
          {([
            ['narration', 'Narration'],
            ['captions', 'Captions'],
            ['manifest', 'Manifest'],
            ['video', 'Video'],
            ['thumbnail', 'Thumbnail'],
          ] as const).map(([key, label]) => (
            <span
              key={key}
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono ${
                pipeline!.assets![key as keyof typeof pipeline.assets]
                  ? 'bg-emerald-400/10 text-emerald-200'
                  : 'bg-white/[.04] text-white/20'
              }`}
            >
              {pipeline!.assets![key as keyof typeof pipeline.assets] ? <CheckCircle2 className="size-3" /> : <Clock3 className="size-3" />}
              {label}
            </span>
          ))}
        </div>
      )}

      {pipeline?.recent_events && pipeline.recent_events.length > 0 && (
        <details className="mt-5 border-t border-white/[.07] pt-5 cursor-pointer group">
          <summary className="flex items-center gap-2 text-xs text-white/45 hover:text-white/70 transition-colors list-none">
            <span>Activity events</span>
            <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
            <span className="ml-auto text-[10px] text-white/20">{pipeline.recent_events.length}</span>
          </summary>
          <div className="mt-3 space-y-2 max-h-64 overflow-y-auto">
            {pipeline.recent_events.map((event) => (
              <div key={event.id} className="flex items-start gap-2 text-xs text-white/45">
                <span
                  className={`mt-0.5 size-1.5 shrink-0 rounded-full ${
                    event.type.endsWith('_failed') ? 'bg-rose-400' : 'bg-white/30'
                  }`}
                />
                <div>
                  <span className="text-white/65">{event.message}</span>
                  {event.created_at && (
                    <span className="ml-2 text-[10.5px] text-white/20 font-mono">
                      {new Date(event.created_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {video.status === 'failed' && pipeline?.error && (
        <div className="mt-5 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4">
          <p className="text-xs font-semibold text-rose-200">{errorDisplay(pipeline.error) ?? pipeline.error.message}</p>
          <p className="mt-1 text-[11px] text-white/35 font-mono">{pipeline.error.message}</p>
          <p className="mt-0.5 text-[10px] text-white/20 font-mono">Code: {pipeline.error.code}</p>
        </div>
      )}

      <dl className="mt-7 grid grid-cols-2 gap-5">
        <div><dt className="eyebrow">Duration</dt><dd className="mt-2 text-sm text-white/75">{video.duration} seconds</dd></div>
        <div><dt className="eyebrow">Format</dt><dd className="mt-2 text-sm text-white/75">{video.aspectRatio} vertical</dd></div>
        <div><dt className="eyebrow">Style</dt><dd className="mt-2 text-sm text-white/75">{video.style}</dd></div>
        <div><dt className="eyebrow">Output</dt><dd className="mt-2 text-sm text-white/75">MP4 / H.264</dd></div>
      </dl>
    </Panel>
  );
}