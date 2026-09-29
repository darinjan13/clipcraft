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
  // Same host as the page (works on localhost AND on phones via LAN IP).
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:8000`;
  }
  return 'http://127.0.0.1:8000';
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

export function getPreferences(): Promise<Preferences> {
  return request<Preferences>('/api/settings/preferences');
}

export function savePreferences(input: PreferencesInput): Promise<Preferences> {
  return request<Preferences>('/api/settings/preferences', {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}
