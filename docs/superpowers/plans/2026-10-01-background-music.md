# Background Music Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local MP3 library with per-video manual picking and a fixed low music bed under narration.

**Architecture:** Backend serves `/data/music` (new volume mounts on backend + renderer); brief carries `musicTrack`; WF08 copies it into the manifest; renderer mixes looped/trimmed music at -22dB under voice before the existing loudnorm pass.

**Tech Stack:** FastAPI, n8n WF08 code node, ffmpeg amix/volume/afade, React+TS.

---

### Task 0: Mount the music volume where code runs

**Files:**
- Modify: `clipcraft/docker-compose.yml`

- [ ] **Step 1: Add mounts**
```yaml
# under clipcraft-backend volumes (next to clipcraft_jobs:/data/jobs):
      - clipcraft_music:/data/music
# under clipcraft-renderer volumes (next to clipcraft_jobs:/data/jobs):
      - clipcraft_music:/data/music
```

- [ ] **Step 2: Validate config**
```bash
docker compose config --format json | py -3 -c "import json,sys; c=json.load(sys.stdin); print('backend:', 'clipcraft_music:/data/music' in str(c['services']['clipcraft-backend'].get('volumes'))); print('renderer:', 'clipcraft_music:/data/music' in str(c['services']['clipcraft-renderer'].get('volumes')))"
```
Expected: both True.

- [ ] **Step 3: Commit**
```bash
git add clipcraft/docker-compose.yml
git commit -m 'chore(music): mount music volume on backend and renderer'
```

---

### Task 1: Music library API (TDD)

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_music_library.py` (create)

Library dir: `/data/music` (inside container). Safe names: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` plus `.mp3`/`.wav` extension preserved. Cap 50MB. Duration via ffprobe (same pattern as the custom-audio upload at main.py ~1214).

- [ ] **Step 1: Write failing tests**
```python
def test_list_music_empty(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/api/music")
    assert response.status_code == 200
    assert response.json() == {"tracks": []}


def test_upload_rejects_non_audio(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/api/music",
        files={"file": ("evil.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_rejects_path_traversal(tmp_path):
    client = make_client(tmp_path)
    response = client.post(
        "/api/music",
        files={"file": ("../evil.mp3", b"ID3", "audio/mpeg")},
    )
    assert response.status_code in (400, 422)
```
(Use the existing `make_client`/`FakeDatabaseClient` pattern from test_api.py.)

- [ ] **Step 2: Run (fails: 404 no route).**
```bash
py -3 -m pytest backend/tests/test_music_library.py -q -p no:warnings
```

- [ ] **Step 3: Implement endpoints**
  - `GET /api/music` → `{"tracks": [{"name": str, "duration": float, "file_size": int}]}` (ffprobe each `.mp3`/`.wav`; skip unreadable files, never 500 the list).
  - `POST /api/music` (multipart `file`): validate extension, 50MB cap, ffprobe duration > 0, save as safe name (keep extension, dedupe with `-2` suffix), return the track object.
  - `DELETE /api/music/{name}`: safe-name check, unlink if present, `{"ok": True}`.
  - Music dir resolves from a `MUSIC_DIR` setting defaulting to `/data/music`, overridable for tests via `data_dir` sibling (mirror how `root`/`data_dir` is threaded into routes; simplest: `<data_dir_parent>/music`? NO — use explicit env `CLIPCRAFT_MUSIC_DIR` default `/data/music`, monkeypatched in tests to tmp_path).

- [ ] **Step 4: Tests pass.**
- [ ] **Step 5: Commit.**

---

### Task 2: Brief plumbing (TDD)

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/main.py`
- Modify: `clipcraft/workflows/08-build-render-manifest.json` (node `Build Manifest`)
- Test: extend `backend/tests/test_api.py`

- [ ] **Step 1: Failing tests**
```python
def test_create_video_carries_music_track(tmp_path):
    # POST /api/videos with visual_source ai + music_track "horror.mp3"
    # (seed the music dir first via the Task 1 upload with monkeypatched dir)
    # assert 202 and brief["musicTrack"] == "horror.mp3"


def test_create_video_rejects_unknown_music_track(tmp_path):
    # music_track "nope.mp3" with empty library -> 422, code "unknown_music_track"
```

- [ ] **Step 2: Implement.**
  - `models.py` VideoDraft: `music_track: str | None = None`.
  - `main.py` create_video: validate against library listing (safe-name + exists) when provided; `brief["musicTrack"] = draft.music_track`. Skip validation when omitted.
  - WF08 `Build Manifest` jsCode: after `captions:` line add `music: job.brief_json && job.brief_json.musicTrack ? '/data/music/' + String(job.brief_json.musicTrack) : '',` to the manifest object. (Get Job already returns full `brief_json`; no select change needed.)
- [ ] **Step 3: Tests pass (`pytest backend/tests/test_api.py`).**
- [ ] **Step 4: Commit.**

---

### Task 3: Renderer mix + render-test extension

**Files:**
- Modify: `clipcraft/video-tools/render_video.py`
- Modify: `clipcraft/video-tools/render-test.sh`

Mix math: voice at full scale, music at 0.08 (≈ -22dB). Fades 1s in/out on the music only.

- [ ] **Step 1: Implement mux branch in `render_video.py`.** Read `music = manifest.get("music", "")`; resolve via `safe_path("/data/music", ...)` — NOTE paths: manifest music is absolute `/data/music/x.mp3`; accept absolute path only if inside `/data/music`, else treat as job-relative (reuse `safe_path` semantics; simplest: if starts with `/data/music/`, verify basename safe and exists, else ignore with a log line and render voice-only).
  - If usable: inputs `-i video_only -i narration -stream_loop -1 -i music`; filter:
```
[1:a]loudnorm=I=-16:LRA=11:TP=-1.5,atrim=duration={min_dur}[a-voice];[2:a]atrim=duration={min_dur},volume=0.08,afade=t=in:st=0:d=1,afade=t=out:st={min_dur-1}:d=1[a-music];[a-voice][a-music]amix=inputs=2:duration=first:dropout_transition=0[a-mix];[a-mix]alimiter=limit=0.95[a]
```
  map `[a]` instead of the current `[a]` chain; keep `-c:a aac -b:a 192k`, `-shortest`, subtitles, x264 settings identical. If music missing/unusable: exact current behavior.
  - Guard `min_dur - 1 > 0.5` else skip the out-fade (short videos).
- [ ] **Step 2: Extend `render-test.sh`.** After the passing 12s render, add: copy a 2s sine wav as `/data/music/test-bed.mp3`? MP3 needs libmp3lame — check availability in the renderer image first (`ffmpeg -encoders | grep mp3`); if absent, use `.wav` (renderer accepts wav; library allows both). Re-render the same manifest with `"music"` injected via a second manifest run? Simplest: `py3 -c` patch manifest adding music, re-run render_video.py, assert output duration still 12.0s and file larger than voice-only (music adds content) — plus extract one frame to prove video intact.
- [ ] **Step 3: Run `render-test.sh` in the renderer container, ALL PASSED.**
- [ ] **Step 4: Commit.**

---

### Task 4: Frontend library + picker (both modes)

**Files:**
- Modify: `frontend/src/features/settings/api/settingsService.ts` (add `listMusic`, `uploadMusic`, `deleteMusic`)
- Modify: `frontend/src/features/settings/pages/SettingsPage.tsx` (or ProviderConnectionCard area — add a Music section; read the file first and place beside credentials)
- Modify: `frontend/src/features/videos/types.ts` (`music_track?: string`)
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx` (picker for both modes)
- Modify: `frontend/src/features/videos/api/videoService.ts` (pass `music_track` through like `mode`/`story_text`)

- [ ] **Step 1: Types + service passthrough** (mirror the `mode`/`story_text` pattern exactly).
- [ ] **Step 2: Settings music section** with upload (accept `audio/mpeg,audio/wav`), list with durations, delete with confirm, error toasts. Reuse existing `request()` helper and `useQuery` patterns from SettingsPage.
- [ ] **Step 3: GenerateForm picker**: a Music select (`No music` + track names, fetched via the new settings API) rendered for BOTH creative and story modes, next to the voice/captions row.
- [ ] **Step 4: `pnpm build` passes.**
- [ ] **Step 5: Commit.**

---

### Task 5: Rebuild, deploy, verify

- [ ] **Step 1: Suites green** (`pytest backend/tests`, node tests, `pnpm build`).
- [ ] **Step 2: Recreate backend + renderer** (new volume mounts need recreation, not rebuild — but rebuild backend anyway for Task 1 code; renderer image unchanged, just recreate).
- [ ] **Step 3: Versioned WF08 deploy** (assert only `Build Manifest` differs; safe DB sequence with WAL cleanup).
- [ ] **Step 4: Upload a horror track** (user provides the MP3; verify listing shows duration).
- [ ] **Step 5: E2E with music** → completed; final MP4 has mixed audio (prove: extract audio, compare RMS energy vs voice-only render — music bed raises the noise floor between words); E2E without music renders byte-comparable behavior to before (duration match + frame check).
- [ ] **Step 6: Commit** any deploy-sync diffs; report.

---

## Self-review

- Spec coverage: library (§1) → Tasks 0–1; picker both modes (§2) → Task 4; render mix (§3) → Task 3; phase 2 excluded → not present.
- No placeholders: every step names files, code, commands.
- Type consistency: `music_track` (draft) → `musicTrack` (brief) → `music` (manifest, absolute job-external path) → renderer mix. `provider`/`retryable` patterns reused, not reinvented.
