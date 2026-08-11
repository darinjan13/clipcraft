export type ProviderCapability = 'text' | 'image' | 'stock_media';

export type ProviderModel = {
  provider_id: string;
  model_id: string;
  display_name: string;
  capability: ProviderCapability;
  implemented: boolean;
  enabled: boolean;
  deprecated: boolean;
  available: boolean;
  description?: string | null;
  context_limit?: number | null;
};

export type AiProvider = {
  provider_id: string;
  display_name: string;
  provider_type: string;
  capabilities: ProviderCapability[];
  requires_credential: boolean;
  credential_type: string | null;
  enabled: boolean;
  implemented: boolean;
  available: boolean;
  models: ProviderModel[];
  default_model: string | null;
};

export type Credential = {
  provider_id: string;
  configured: boolean;
  enabled: boolean;
  status: string;
  secret_last_four: string | null;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_test_error_safe: string | null;
};

export type CredentialInput = {
  secret: string;
  metadata?: Record<string, string>;
  enabled?: boolean;
};

export type ConnectionTestResult = {
  provider_id: string;
  status: string;
  message: string;
  persisted: boolean;
};

export type Preferences = {
  default_text_provider: string;
  default_text_model: string;
  default_visual_source: string;
  default_image_provider: string;
  default_image_model: string;
  default_pexels_media_type: string | null;
  default_pexels_orientation: string | null;
  updated_at: string | null;
};

export type PreferencesInput = Omit<Preferences, 'updated_at'>;
