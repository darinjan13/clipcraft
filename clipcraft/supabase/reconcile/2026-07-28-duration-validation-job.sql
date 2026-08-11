-- Reconcile the one duration-validation job that failed with
-- NARRATION_WORD_COUNT_OUT_OF_RANGE_AFTER_REVISION but was never
-- persisted as terminal because the legacy error handler required
-- full lease context (n8n executions 9158 / 9159).
--
-- Prerequisites: migration 005_video_job_events.sql must be applied.
-- Safe to re-run: the RPC is idempotent.
--
-- Run: psql $DATABASE_URL -f .../2026-07-28-duration-validation-job.sql

select public.persist_video_job_failure(
  p_job_id          := '6c9b8f51-620c-4805-9c86-aad17228b286'::uuid,
  p_idempotency_key := '6c9b8f51-620c-4805-9c86-aad17228b286:narration-word-count-revision-failed',
  p_stage           := 'generating_script',
  p_current_step    := 'generating_script',
  p_progress        := 5,
  p_error_code      := 'NARRATION_WORD_COUNT_OUT_OF_RANGE_AFTER_REVISION',
  p_user_message    := 'The generated narration was still too short after two attempts.',
  p_metadata        := '{
    "actual_words": 48,
    "target_words": 97,
    "minimum_words": 89,
    "maximum_words": 105,
    "attempt": 2,
    "maximum_attempts": 2,
    "execution_id": "91536"
  }'::jsonb
);