# Gemini 3.x Models + 429 Fallback — Design Spec

Date: 2026-09-27
Status: approved (approach A)
Branch: `feature/gemini-3-models`

## Objective

Register Gemini 3.x Flash models as text options, default new videos to
`gemini-3.5-flash-lite`, and automatically fall back across models on 429.
Doubles as the forced migration off `gemini-2.5-flash`, which retires
2026-10-20 (Google names 3.5/3.1 Flash-Lite as replacements). Note: 2.5-flash
is deliberately NOT flagged `deprecated` in the registry — that flag makes a
model unselectable and would break existing pinned selections. It stays
enabled (last in the fallback chain) until retirement; full removal is a
separate task for October.

## Facts (verified 2026-09-27)

- Free-tier quotas are per model (RPM/RPD vary by model; Lite models get
  higher RPD headroom). Limits apply per project, RPD resets midnight PT.
- Stable text-capable IDs: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`,
  `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`,
  `gemini-3.8-flash`, plus `gemini-3-flash-preview` (preview).
- Frontend model pickers are registry-driven; no frontend changes needed.

## Architecture (approach A)

1. **Registry.** Add 7 models (`capability="text"`, implemented, enabled)
   to the gemini provider. Flag `gemini-2.5-flash` `deprecated=True` (still
   selectable; existing jobs keep working). Set
   `DEFAULT_TEXT_MODEL = "gemini-3.5-flash-lite"`.
2. **Fallback chain (backend, Gemini text execution path only).** On
   `rate_limited` (429) the executor retries with the next model in
   [preferred → 3.5-flash-lite → 3.1-flash-lite → 3.6 → 3.7 → 3.8 →
   3.5-flash → 3-flash-preview], skipping the failed model and deprecated
   models unless explicitly requested. Non-429 errors never fall back.
   Each attempt logs the model id.
3. **Defaults.** New videos default to 3.5-flash-lite; in-flight jobs keep
   their pinned model.

## Non-goals

- No image-capability additions (Nano Banana lines excluded).
- No cross-provider fallback (Gemini → Cloudflare stays manual).
- No quota tracking/persistence; chain relies on per-model 429 signals.

## Verification

- Unit: chain advances on 429, stops on other errors, honors explicit
  choice, skips deprecated unless requested; registry lists all models
  with correct default.
- E2E: one script generation on the new default (shares the pending
  Gemini quota reset with the Pixabay mix retry).
