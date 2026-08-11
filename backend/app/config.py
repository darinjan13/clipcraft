import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    n8n_base_url: str
    n8n_api_key: str = field(repr=False)
    supabase_url: str
    supabase_service_role_key: str = field(repr=False)
    data_dir: str
    gemini_api_key: str = field(repr=False)
    gemini_text_model: str
    gemini_image_enabled: bool
    gemini_image_model: str
    cloudflare_ai_token: str = field(default="", repr=False)
    cloudflare_account_id: str = ""
    shadow_provider_execution: bool = False
    shadow_runtime_comparison: bool = True
    n8n_internal_signing_secret: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            n8n_base_url=os.getenv("N8N_BASE_URL", "http://clipcraft-n8n:5678").rstrip("/"),
            n8n_api_key=os.getenv("N8N_API_KEY", ""),
            supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            data_dir=os.getenv("CLIPCRAFT_DATA_DIR", os.getenv("VIDEO_STORAGE_PATH", "/data/jobs")),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_text_model=os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            gemini_image_enabled=os.getenv("GEMINI_IMAGE_ENABLED", "false").lower() == "true",
            gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", ""),
            cloudflare_ai_token=os.getenv("CLOUDFLARE_AI_TOKEN", ""),
            cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            shadow_provider_execution=os.getenv("SHADOW_PROVIDER_EXECUTION", "false").lower() == "true",
            shadow_runtime_comparison=os.getenv("SHADOW_RUNTIME_COMPARISON", "true").lower() == "true",
            n8n_internal_signing_secret=os.getenv("N8N_INTERNAL_SIGNING_SECRET", ""),
        )
