export type VideoStatus = 'queued' | 'rendering' | 'completed' | 'failed' | 'cancelled';
export type Video = { id: string; title: string; prompt: string; status: VideoStatus; progress: number; duration: number; aspectRatio: '9:16' | '16:9' | '1:1'; style: string; createdAt: string; thumbnail: string; videoUrl?: string };
export type VideoDraft = {
  title: string;
  prompt: string;
  duration: string;
  style: string;
  voice: string;
  captions: string;
  aspectRatio: Video['aspectRatio'];
  text_provider?: string;
  text_model?: string;
  image_provider?: string;
  image_model?: string;
  visual_source?: 'ai' | 'pexels';
  pexels_media_type?: 'photo' | 'video';
  pexels_orientation?: 'landscape' | 'portrait' | 'square';
  credential_source?: 'environment';
  provider_configuration_version?: '1';
};

export type ModelOption = {
  provider: string;
  model: string;
  display_name: string;
  description: string;
  available: boolean;
  is_default: boolean;
};

export type ModelCapabilities = {
  defaults: {
    text_provider: string;
    text_model: string;
    image_provider: string;
    image_model: string;
  };
  text_models: ModelOption[];
  image_models: ModelOption[];
  providers: import('@/features/settings/types').AiProvider[];
};

export type PipelineStatus = {
  id: string;
  status: string;
  display_status: string;
  progress: number;
  current_step: string | null;
  created_at: string | null;
  updated_at: string | null;
  elapsed_seconds: number;
  stale: boolean;
  image_progress: { completed: number; total: number; failed: number } | null;
  assets: { narration: boolean; captions: boolean; manifest: boolean; video: boolean; thumbnail: boolean } | null;
  error: { code: string; message: string } | null;
  recent_events: Array<{ id: string; type: string; stage: string | null; status: string | null; progress: number | null; message: string; created_at: string }>;
};
