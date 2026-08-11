import type { PipelineStatus } from '@/features/videos/types';

export const ACTIVE_POLL_MS = 2_000;
export const HIDDEN_POLL_MS = 15_000;
export const STALE_AFTER_MS = 60_000;

export const STAGES = [
  { id: 'generate_script', label: 'Generate script' },
  { id: 'generate_images', label: 'Generate images' },
  { id: 'generate_voice', label: 'Generate voice' },
  { id: 'build_captions', label: 'Build captions' },
  { id: 'build_manifest', label: 'Build manifest' },
  { id: 'render', label: 'Render video' },
] as const;

export type PipelineStageId = (typeof STAGES)[number]['id'];

export function rawStatusToStage(raw: string): PipelineStageId {
  const map: Record<string, PipelineStageId> = {
    queued: 'generate_script',
    generating_script: 'generate_script',
    script_ready: 'generate_script',
    generating_images: 'generate_images',
    generating_voice: 'generate_voice',
    building_captions: 'build_captions',
    building_manifest: 'build_manifest',
    rendering: 'render',
    processing: 'render',
  };
  return map[raw] ?? 'generate_script';
}

export function currentStageIndex(status: PipelineStatus | null | undefined): number {
  if (!status) return 0;
  let best = -1;
  for (const event of status.recent_events ?? []) {
    const stage = event.stage;
    if ((event.type !== 'stage_changed' && event.type !== 'stage_completed') || !stage) continue;
    const idx = STAGES.findIndex((s) => s.id === rawStatusToStage(stage));
    if (idx > best) best = idx;
  }
  if (best >= 0) return best;
  return STAGES.findIndex((s) => s.id === rawStatusToStage(status.status ?? ''));
}

export function getActivePollInterval(status: string, isHidden: boolean): number | false {
  const terminal = status === 'completed' || status === 'failed' || status === 'cancelled';
  if (terminal) return false;
  return isHidden ? HIDDEN_POLL_MS : ACTIVE_POLL_MS;
}

export function isStale(status: PipelineStatus | null): boolean {
  if (!status || !status.updated_at) return false;
  if (status.status === 'completed' || status.status === 'failed') return false;
  return (Date.now() - new Date(status.updated_at).getTime()) > STALE_AFTER_MS;
}

export function formatElapsed(totalSeconds: number): string {
  if (totalSeconds < 60) return `${Math.floor(totalSeconds)}s`;
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}m ${s}s`;
}

export function elapsed(created: string | null, updated: string | null, isTerminal: boolean): number {
  if (!created) return 0;
  const start = new Date(created).getTime();
  const end = isTerminal && updated ? new Date(updated).getTime() : Date.now();
  return Math.max(0, (end - start) / 1000);
}

export const ERROR_MESSAGES: Record<string, string> = {
  NARRATION_WORD_COUNT_OUT_OF_RANGE: 'The generated narration was too short.',
  NARRATION_WORD_COUNT_OUT_OF_RANGE_AFTER_REVISION: 'The generated narration was still too short after two attempts.',
  NARRATION_DURATION_OUT_OF_RANGE: 'The generated narration duration was outside the accepted range.',
  NARRATION_DURATION_OUT_OF_RANGE_AFTER_REVISION: 'The narration duration was still outside range after revision.',
};

export function errorDisplay(err: PipelineStatus['error']): string {
  if (!err) return '';
  return ERROR_MESSAGES[err.code] ?? err.message;
}