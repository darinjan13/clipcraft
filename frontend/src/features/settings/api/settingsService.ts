import type {
  AiProvider,
  ConnectionTestResult,
  Credential,
  CredentialInput,
  Preferences,
  PreferencesInput,
} from '../types';

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured.replace(/\/$/, '');
  // Same-origin requests are proxied by Vite for LAN, Tailscale, and tunnels.
  return '';
}
const API_BASE_URL = apiBaseUrl();

export class SettingsApiError extends Error {
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'SettingsApiError';
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: { message?: string; code?: string } | string } | null;
    const detail = body?.detail;
    const message = typeof detail === 'object' ? detail.message : detail;
    throw new SettingsApiError(message ?? `Request failed with status ${response.status}`, typeof detail === 'object' ? detail.code : undefined);
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export async function listProviders(): Promise<AiProvider[]> {
  const response = await request<{ providers: AiProvider[] }>('/api/ai/providers');
  return response.providers;
}

export async function discoverNvidiaModels(): Promise<{ models: any[] }> {
  return request<{ models: any[] }>('/api/ai/models/nvidia/discover');
}

export async function listCredentials(): Promise<Credential[]> {
  const response = await request<{ credentials: Credential[] }>('/api/ai/credentials');
  return response.credentials;
}

export function saveCredential(providerId: string, input: CredentialInput): Promise<Credential> {
  return request<Credential>(`/api/ai/credentials/${encodeURIComponent(providerId)}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

export function testCredential(providerId: string): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>(`/api/ai/credentials/${encodeURIComponent(providerId)}/test`, { method: 'POST' });
}

export function deleteCredential(providerId: string): Promise<void> {
  return request<void>(`/api/ai/credentials/${encodeURIComponent(providerId)}`, { method: 'DELETE' });
}

export interface MusicTrack {
  name: string;
  duration: number;
  file_size: number;
}

export async function listMusic(): Promise<MusicTrack[]> {
  const response = await request<{ tracks: MusicTrack[] }>('/api/music');
  return response.tracks;
}

export async function uploadMusic(file: File): Promise<MusicTrack> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}/api/music`, { method: 'POST', body: formData });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new SettingsApiError(typeof body?.detail === 'string' ? body.detail : 'Upload failed');
  }
  return response.json() as Promise<MusicTrack>;
}

export async function deleteMusic(name: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/music/${encodeURIComponent(name)}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new SettingsApiError('Could not delete track.');
  }
}

export function getPreferences(): Promise<Preferences> {
  return request<Preferences>('/api/settings/preferences');
}

export function savePreferences(input: PreferencesInput): Promise<Preferences> {
  return request<Preferences>('/api/settings/preferences', {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}
