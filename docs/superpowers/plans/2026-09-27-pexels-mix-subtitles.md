# Pexels Mix + Narration Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pexels jobs can mix photos and clips per AI-chosen scene tags, and on-screen text shows chunked narration subtitles instead of short captions.

**Architecture:** Backend accepts `pexels_media_type: 'both'` end to end; WF04 prompts for and normalizes a per-scene `mediaType` tag (stored in `script_json`, no schema change); WF05 resolves each scene's tag and routes the stock call per scene; WF07 splits narration into timed chunks; renderer and manifest already branch per scene and stay untouched.

**Tech Stack:** Python/FastAPI backend, n8n Code-node JavaScript, Pexels REST, ffmpeg ASS subtitles.

**Environment notes (read first):** Work on branch `feature/pexels-mix-subtitles` (create from `main`). Docker Desktop must be running for any n8n DB deploy or E2E step — if the daemon is unreachable, do all code/test steps first and stop before the deploy task. The live n8n database is the source of truth for workflow code: always diff live vs repo before editing a workflow file, and deploy via the versioned pattern (new `workflow_history` row + repoint `versionId`/`activeVersionId`, checkpoint, verify join resolves), never `n8n import:workflow` (known FK failure + deactivation in this image).

---

## File structure

- Modify: `backend/app/services/ai/provider_registry.py` — add `"both"` to `SUPPORTED_PEXELS_MEDIA_TYPES`.
- Modify: `backend/tests/test_api.py`, `backend/tests/test_preferences.py` — `both` coverage.
- Modify: `clipcraft/workflows/04-generate-script-and-scenes.json` — prompt tag request + validate normalization.
- Modify: `clipcraft/workflows/05-generate-scene-images.json` — tag resolution + per-scene stock media type.
- Modify: `clipcraft/workflows/07-build-captions.json` — Get Scenes adds `narration`; Generate ASS File chunks narration.
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx` — "Mix photos & videos" option + type.
- Modify: `frontend/src/features/videos/types.ts` — `pexels_media_type` gains `'both'`.

---

### Task 1: Backend accepts `both`

**Files:**
- Modify: `backend/app/services/ai/provider_registry.py:9`
- Modify: `backend/tests/test_api.py`, `backend/tests/test_preferences.py`

- [ ] **Step 1: Write the failing test**

Append to the pexels brief test area in `backend/tests/test_api.py`:
```python
def test_create_video_brief_carries_pexels_mix_selection(tmp_path):
    workflow = FakeWorkflowClient()
    database = FakeDatabaseClient()
    client = make_client(tmp_path, workflow=workflow, database=database)

    response = client.post(
        "/api/videos",
        json={
            "title": "Rainy windows mix",
            "prompt": "Morning rain on city windows.",
            "duration": "30",
            "style": "Cinematic",
            "voice": "Warm narrator",
            "captions": "Clean",
            "aspectRatio": "9:16",
            "text_provider": "cloudflare",
            "text_model": "@cf/meta/llama-3.1-8b-instruct",
            "visual_source": "pexels",
            "pexels_media_type": "both",
            "pexels_orientation": "portrait",
            "credential_source": "stored",
            "provider_configuration_version": "1",
        },
    )

    assert response.status_code == 202
    brief = database.rows[0]["brief_json"]
    assert brief["visualSource"] == "pexels"
    assert brief["pexelsMediaType"] == "both"
    assert brief["pexelsOrientation"] == "portrait"
```
(`FakeWorkflowClient`, `FakeDatabaseClient`, `make_client` already exist in that file — same imports as the neighboring pexels brief test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest backend/tests/test_api.py -q -p no:warnings -k 'both'`
Expected: FAIL with `unsupported_pexels_media_type` (422, not 202).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/ai/provider_registry.py:9`, change:
```python
SUPPORTED_PEXELS_MEDIA_TYPES = {"photo", "video"}
```
to:
```python
SUPPORTED_PEXELS_MEDIA_TYPES = {"photo", "video", "both"}
```
Nothing else: snapshot, brief, and preferences code already passes the value through; `both` only ever reaches the stock call site, which WF05 resolves per scene (Task 3).

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest backend/tests/test_api.py backend/tests/test_preferences.py -q -p no:warnings`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/provider_registry.py backend/tests/test_api.py
git commit -m "feat: accept pexels both media type"
```

---

### Task 2: WF04 tags each scene photo/video

**Files:**
- Modify: `clipcraft/workflows/04-generate-script-and-scenes.json` (Build Prompt + Validate Output nodes)

- [ ] **Step 1: Verify live anchors before editing**

The live workflow is the source of truth. Confirm both anchors exist verbatim (search the live `Build Prompt` and `Validate Output` jsCode):
- Anchor A: `Each scene needs narration, caption, imagePrompt, motion, and transition.`
- Anchor B (scene normalization return object): `transition: transitions.includes(scene.transition) ? scene.transition : 'crossfade'`
If either anchor is absent, STOP and re-derive the edit from the live code — do not guess.

- [ ] **Step 2: Request the tag in the prompt**

In `Build Prompt` jsCode, change Anchor A to:
```
Each scene needs narration, caption, imagePrompt, motion, and transition. Tag each scene "mediaType": "photo" or "video" by what suits its visuals best.
```
(Exact match on the Anchor A sentence; leave surrounding prompt text untouched.)

- [ ] **Step 3: Normalize the tag in Validate Output**

In the scenes `.map()` normalization return object, add after the `transition:` line:
```js
mediaType: scene.mediaType === 'video' ? 'video' : 'photo',
```
So a scene becomes `{ index, narration, caption, imagePrompt, durationSeconds, motion, transition, mediaType, ...(delivery...) }`. Missing/unknown tags default to `photo`. The tag persists inside `script_json` (no schema change — the scenes table has no media column and needs none). Revision loop, word-count, and duration logic untouched.

- [ ] **Step 4: Syntax-check both nodes**

Extract each modified jsCode into `function __check() { ... }` wrappers and run `node --check` on both files.
Expected: silent (valid).

- [ ] **Step 5: Commit**

```bash
git add clipcraft/workflows/04-generate-script-and-scenes.json
git commit -m "feat: tag script scenes photo or video for pexels mix"
```
(Deploy happens in Task 5 with the other workflows, single n8n restart.)

---

### Task 3: WF05 routes per scene tag

**Files:**
- Modify: `clipcraft/workflows/05-generate-scene-images.json` (Prepare Items + Call Stock Media params)

Background (verified): the orchestrator's claim payload carries `script_json`, and WF05 `Validate` passes its input through, so `Prepare Items` can read `job.script_json.scenes`. `Call Stock Media` currently sends `mediaType` from `=$json.pexelsMediaType`.

- [ ] **Step 1: Resolve tags in Prepare Items**

In `Prepare Items` jsCode, after the existing `pexelsMediaType`/`pexelsOrientation` resolution, add:
```js
const scriptScenes = Array.isArray(brief.script_json?.scenes) ? brief.script_json.scenes : (Array.isArray(job.script_json?.scenes) ? job.script_json.scenes : []);
const tagByIndex = {};
for (const scene of scriptScenes) {
  const key = Number(scene.scene_index ?? scene.index);
  if (Number.isFinite(key)) tagByIndex[key] = scene.mediaType === 'video' ? 'video' : 'photo';
}
```
(`brief` and `job` variables already exist in that node — read the current code and use its exact names; the fields above match the live node.) Then extend the emitted per-scene object with:
```js
sceneMediaType: tagByIndex[Number(s.scene_index)] ?? null,
```
so each item carries its AI tag (null when the script predates tags).

- [ ] **Step 2: Prefer the tag in the stock call**

In `Call Stock Media` parameters, change the mediaType expression from `={{ $json.pexelsMediaType }}` to:
```
={{ $json.sceneMediaType ?? $json.pexelsMediaType }}
```
Job-level type remains the fallback (pure photo/video jobs behave exactly as today; pre-tag scripts fall back too).

- [ ] **Step 3: Syntax-check**

Extract the modified `Prepare Items` jsCode into a `function __check()` wrapper and run `node --check`.
Expected: silent.

- [ ] **Step 4: Commit**

```bash
git add clipcraft/workflows/05-generate-scene-images.json
git commit -m "feat: route pexels stock calls per scene tag"
```

---

### Task 4: WF07 chunked narration subtitles

**Files:**
- Modify: `clipcraft/workflows/07-build-captions.json` (Get Scenes select + Generate ASS File events)

Background (verified live): `Generate ASS File` builds one Dialogue event per scene from `(s.narration || s.caption)` but `Get Scenes` never selects `narration`, so it always falls back to the short caption. Style stays `Arial 48, MarginV 290`; `formatTime` and the backslash/brace/newline escaping stay exactly as they are.

- [ ] **Step 1: Fetch narration in Get Scenes**

In the `Get Scenes` HTTP node URL, extend the select list with `narration`:
```
&select=id,scene_index,caption,narration,duration_seconds,video_jobs!inner(audio_mode,effective_duration,brief_json)
```
(Keep every existing selected field in place; append `,narration` after `caption`. Verify by reading the live node URL first — if its select list differs, append `narration` to whatever is there.)

- [ ] **Step 2: Replace the event loop with chunking**

Replace the `for (const s of scenes)` event loop body with per-scene chunking. Insert this helper before the loop (after `formatTime`):
```js
function chunkNarration(text, maxChars) {
  const words = String(text || '').trim().split(/\s+/).filter(Boolean);
  const chunks = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? current + ' ' + word : word;
    if (candidate.length > maxChars && current) {
      chunks.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) chunks.push(current);
  return chunks.length ? chunks : [''];
}
function escapeAss(text) {
  return String(text).replace(/\\/g, '\\\\').replace(/{/g, '\\{').replace(/}/g, '\\}').replace(/\n/g, '\\N');
}
```
Replace the single `ass += 'Dialogue...'` line with:
```js
const chunks = chunkNarration(s.narration || s.caption || '', 42);
const totalWords = String(s.narration || s.caption || '').trim().split(/\s+/).filter(Boolean).length || 1;
let cursor = currentTime;
chunks.forEach((chunk, chunkIndex) => {
  const chunkWords = chunk.trim().split(/\s+/).filter(Boolean).length;
  const isLast = chunkIndex === chunks.length - 1;
  const chunkDur = isLast
    ? Math.round((currentTime + dur - cursor) * 100) / 100
    : Math.round((dur * chunkWords / totalWords) * 100) / 100;
  ass += 'Dialogue: 0,' + formatTime(cursor) + ',' + formatTime(cursor + chunkDur) + ',Default,,0,0,0,,' + escapeAss(chunk) + '\n';
  cursor = Math.round((cursor + chunkDur) * 100) / 100;
});
currentTime += dur;
```
(`dur`, `start`/`end` variables from the old loop are superseded — remove them; keep `currentTime` accumulation and everything after the loop untouched, including the return payload shape.)

- [ ] **Step 3: Unit-test the chunking offline**

Save the helper functions to a scratch file with these assertions (plain `node:assert/strict`):
- 25 words over a 5s scene produce ≥2 chunks, each ≤42 chars, no broken words;
- chunk durations sum exactly to the scene duration (to the cent);
- empty narration yields one empty event (never throws).
Run with `node <file>`; all assertions must pass.

- [ ] **Step 4: Syntax-check the full node**

Extract the modified `Generate ASS File` jsCode into a `function __check()` wrapper and run `node --check`.
Expected: silent.

- [ ] **Step 5: Commit**

```bash
git add clipcraft/workflows/07-build-captions.json
git commit -m "feat: chunk narration into timed subtitle events"
```

---

### Task 5: Frontend Mix option + build

**Files:**
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx`
- Modify: `frontend/src/features/videos/types.ts`

- [ ] **Step 1: Add the option**

In the Pexels media type `<Select>` (next to the existing `photo`/`video` options), add `<option value="both">Mix photos & videos</option>`.

- [ ] **Step 2: Widen the type**

In `VideoDraft`, change `pexels_media_type?: 'photo' | 'video'` to `pexels_media_type?: 'photo' | 'video' | 'both'`.

- [ ] **Step 3: Build to verify**

Run: `pnpm build` from `frontend/`
Expected: `tsc -b` clean + `vite build` success.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/generate/components/GenerateForm.tsx frontend/src/features/videos/types.ts
git commit -m "feat: add pexels mix option"
```

---

### Task 6: Versioned deploy (04/05/07)

Requires Docker Desktop running. Never use `n8n import:workflow` (known FK failure + deactivation in this image).

- [ ] **Step 1: Stop n8n, copy the live DB out**

```bash
docker stop clipcraft-n8n
docker cp clipcraft-n8n:/root/.n8n/database.sqlite <tmp>/database.sqlite
docker cp clipcraft-n8n:/root/.n8n/database.sqlite-wal <tmp>/database.sqlite-wal
```

- [ ] **Step 2: Verify repo==live except intended diffs**

For each of `dWTF2UGXX3R73PDW`, `gazJuTcoSGqYdGze`, `dNgYGCqkbwr552EW`: node-name sets identical; every shared node byte-identical except the nodes this plan changed. Abort on any unexpected diff.

- [ ] **Step 3: Insert one history version + repoint per workflow**

For each workflow: `INSERT INTO workflow_history` with the repo nodes/connections (new uuid versionId, author `Admin User`, name = workflow name, autosaved 0), then `UPDATE workflow_entity SET nodes, connections, versionId, activeVersionId, versionCounter+1`. Assert rowcount 1 each, then verify the `activeVersionId` join resolves and carries the new code. Checkpoint + integrity check.

- [ ] **Step 4: Copy back, neutralize WAL/SHM with zero-byte files, start, verify runner**

Poller success events must resume in `n8nEventLog.log` before any E2E.

---

### Task 7: Verification gate (Docker required)

- [ ] **Step 1: E2E mix video**

Create a 30s `visual_source=pexels`, `pexels_media_type=both`, `pexels_orientation=portrait` video via the public API (same payload shape as the photo/clip E2Es plus `"pexels_media_type": "both"`). Expect: completed.

- [ ] **Step 2: Assert the mix + subtitles**

Manifest scenes contain at least one photo scene (empty `clip`) and one clip scene (non-empty `clip`); `captions.ass` has more Dialogue events than scenes; each event ≤42 visible chars; event times tile scenes exactly with no gaps.

- [ ] **Step 3: Frame check**

Extract a mid-narration frame: expect a mid-sentence phrase (not the old short caption) burned in over full-bleed footage.

## Self-Review

**1. Spec coverage:** §1 subtitle chunking → Task 4; §2 media tags (WF04) → Task 2; §3 mix plumbing → Task 1 (backend `both`), Task 3 (WF05 per-scene routing), Task 5 (frontend option); §4 errors → Tasks 2/3/4 preserve existing failure paths; §5 tests → per-task tests + full-suite runs; §6 verification → Task 7. Renderer/manifest need no changes per spec (already per-scene). Covered.
**2. Placeholder scan:** every step names exact files, code, commands, expected outputs. The two deliberate live-verify-first guards (Task 2 Step 1, Task 4 Get Scenes select) include exact fallback behavior.
**3. Type consistency:** `mediaType` photo|video in WF04 tags; `pexels_media_type` photo|video|both at job level; `sceneMediaType` per item; manifest `clip` string ('' when absent); ASS chunk fields consistent. `duration_seconds` flows scene→stock call as before.
