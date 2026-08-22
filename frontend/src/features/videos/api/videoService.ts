import type { ModelCapabilities, PipelineStatus, Video, VideoDraft } from '../types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function withApiOrigin(video: Video): Video {
  return {
    ...video,
    thumbnail: video.thumbnail.startsWith('/') ? `${API_BASE_URL}${video.thumbnail}` : video.thumbnail,
    videoUrl: video.videoUrl?.startsWith('/') ? `${API_BASE_URL}${video.videoUrl}` : video.videoUrl,
  };
}

export function listVideos(): Promise<Video[]> {
  return request<Video[]>('/api/videos').then((videos) => videos.map(withApiOrigin));
}

export function getVideo(id: string): Promise<Video> {
  return request<Video>(`/api/videos/${encodeURIComponent(id)}`).then(withApiOrigin);
}

export function getVideoStatus(id: string): Promise<PipelineStatus> {
  return request<PipelineStatus>(`/api/videos/${encodeURIComponent(id)}/status`);
}

export function createVideo(draft: VideoDraft): Promise<Video> {
  const { visual_source, pexels_media_type, pexels_orientation, ...requestDraft } = draft;
  const { image_provider: _imageProvider, image_model: _imageModel, ...pexelsRequestDraft } = requestDraft;
  return request<Video>('/api/videos', {
    method: 'POST',
    body: JSON.stringify({
      ...(visual_source === 'pexels' ? pexelsRequestDraft : requestDraft),
      ...(visual_source ? { visual_source } : {}),
      ...(visual_source === 'pexels' ? { pexels_media_type, pexels_orientation } : {}),
      credential_source: draft.text_provider === 'nvidia' ? 'stored' : 'environment',
      provider_configuration_version: '1',
    }),
  }).then(withApiOrigin);
}

export function renameVideo(id: string, title: string): Promise<Video> {
  return request<Video>(`/api/videos/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  }).then(withApiOrigin);
}

export function regenerateVideo(id: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/videos/${encodeURIComponent(id)}/regenerate`, { method: 'POST' });
}

export function duplicateVideo(id: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/videos/${encodeURIComponent(id)}/duplicate`, { method: 'POST' });
}

export function deleteVideo(id: string): Promise<{ ok: boolean; id: string }> {
  return request<{ ok: boolean; id: string }>(`/api/videos/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function cancelVideo(id: string): Promise<{ ok: boolean; id: string; status: string }> {
  return request<{ ok: boolean; id: string; status: string }>(`/api/videos/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
}

export function downloadVideo(id: string, filename = 'clipcraft-video.mp4'): void {
  const a = document.createElement('a');
  a.href = `${API_BASE_URL}/api/videos/${encodeURIComponent(id)}/file`;
  a.download = filename;
  a.click();
}

export function getNarration(id: string): Promise<Blob> {
  return fetch(`${API_BASE_URL}/api/videos/${encodeURIComponent(id)}/narration`).then(async (response) => {
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
    }
    return response.blob();
  });
}

export function uploadCustomAudio(id: string, audio: File): Promise<{
  ok: boolean;
  job_id: string;
  uploaded_duration: number;
  target_duration: number;
  duration_ratio: number;
  path: string;
  mime_type: string;
  file_size: number;
}> {
  const formData = new FormData();
  formData.append('audio', audio);
  return fetch(`${API_BASE_URL}/api/videos/${encodeURIComponent(id)}/audio`, {
    method: 'POST',
    body: formData,
  }).then(async r => {
    if (!r.ok) {
      const body = await r.json().catch(() => null);
      throw new Error(body?.detail?.message || 'Upload failed');
    }
    return r.json();
  });
}

export function resumeCustomAudio(id: string): Promise<{ ok: boolean; status: string; next_stage: string }> {
  return request<{ ok: boolean; status: string; next_stage: string }>(`/api/videos/${encodeURIComponent(id)}/resume`, {
    method: 'POST',
  });
}

export function getModelCapabilities(): Promise<ModelCapabilities> {
  return request<ModelCapabilities>('/api/ai/models');
}
