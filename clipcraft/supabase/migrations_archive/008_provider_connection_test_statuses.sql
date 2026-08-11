-- ClipCraft AI - Normalized provider connection-test statuses
-- Prerequisites: 007_ai_provider_credentials.sql

alter table public.ai_provider_credentials
  drop constraint if exists ai_provider_credentials_last_test_status_check;

alter table public.ai_provider_credentials
  add constraint ai_provider_credentials_last_test_status_check
  check (last_test_status is null or last_test_status in (
    'connected',
    'invalid_credentials',
    'quota_exceeded',
    'rate_limited',
    'unavailable',
    'timeout',
    'not_implemented',
    'configuration_error',
    'provider_error'
  ));
