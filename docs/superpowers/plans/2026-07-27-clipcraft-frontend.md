# ClipCraft Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone React 19/Vite/TypeScript frontend in `frontend/` that faithfully implements the four approved Stitch screens with local mock data.

**Architecture:** Use a shared AppShell with React Router routes for Generate, Library, Preview, and Settings. Keep page features isolated under `src/features`, shared primitives under `src/components`, and mock video operations behind a typed API service consumed through TanStack Query and Zustand.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind CSS, shadcn-style primitives, React Router, TanStack Query, Zustand, Framer Motion, Lucide React, pnpm.

---

### Task 1: Scaffold Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/vite-env.d.ts`

- [ ] Add the exact dependency set for React 19, Tailwind, Router, Query, Zustand, Motion, and Lucide.
- [ ] Configure strict TypeScript and Vite alias `@` to `src`.
- [ ] Configure Tailwind content scanning for `index.html` and `src/**/*.{ts,tsx}`.
- [ ] Add the QueryClient provider and router entrypoint.
- [ ] Run `pnpm install` in `frontend/` and verify the package lock is generated.

### Task 2: Build Design Tokens And Shared Components

**Files:**
- Create: `frontend/src/index.css`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/components/ui/Button.tsx`
- Create: `frontend/src/components/ui/Panel.tsx`
- Create: `frontend/src/components/ui/Badge.tsx`
- Create: `frontend/src/components/ui/Progress.tsx`
- Create: `frontend/src/components/ui/Input.tsx`
- Create: `frontend/src/components/ui/Select.tsx`
- Create: `frontend/src/components/ui/EmptyState.tsx`
- Create: `frontend/src/components/ui/LoadingState.tsx`
- Create: `frontend/src/components/layout/AppShell.tsx`

- [ ] Encode Stitch Lumina Cinematic colors, Inter/Geist font stacks, glass surfaces, 8px radius language, spacing, and responsive breakpoints in CSS/Tailwind.
- [ ] Implement accessible reusable primitives with focus-visible states and disabled/loading states.
- [ ] Implement desktop sidebar and mobile navigation with active route styling.
- [ ] Preserve Stitch hierarchy: dark canvas, elevated glass panels, violet/blue action gradient, compact technical metadata.

### Task 3: Add Mock Domain And State

**Files:**
- Create: `frontend/src/features/videos/types.ts`
- Create: `frontend/src/features/videos/api/videoService.ts`
- Create: `frontend/src/features/videos/api/queryKeys.ts`
- Create: `frontend/src/features/videos/store/useVideoStore.ts`
- Create: `frontend/src/features/settings/store/useSettingsStore.ts`

- [ ] Define strict `Video`, `VideoStatus`, `VideoDraft`, and settings types.
- [ ] Implement `createVideo()`, `getVideoStatus()`, `getVideo()`, and `listVideos()` with deterministic mock records and artificial delays.
- [ ] Store the generate draft and settings locally with Zustand.
- [ ] Ensure service functions do not import browser-only UI code or backend clients.

### Task 4: Implement Generate Screen

**Files:**
- Create: `frontend/src/features/generate/pages/GeneratePage.tsx`
- Create: `frontend/src/features/generate/components/GenerateForm.tsx`
- Create: `frontend/src/features/generate/components/GenerationProgress.tsx`

- [ ] Recreate the Stitch Generate Video hierarchy and spacing.
- [ ] Bind topic, duration, style, voice, captions, and aspect-ratio controls to Zustand draft state.
- [ ] Submit through `createVideo()` using a TanStack mutation, show rendering progress, and navigate to `/library/:videoId` on completion.
- [ ] Render idle, submitting, rendering, completed, and error states without backend calls.

### Task 5: Implement Library And Preview Screens

**Files:**
- Create: `frontend/src/features/library/pages/LibraryPage.tsx`
- Create: `frontend/src/features/library/components/VideoCard.tsx`
- Create: `frontend/src/features/library/components/LibraryFilters.tsx`
- Create: `frontend/src/features/preview/pages/PreviewPage.tsx`
- Create: `frontend/src/features/preview/components/PreviewCanvas.tsx`
- Create: `frontend/src/features/preview/components/RenderStatus.tsx`

- [ ] Recreate Stitch Library grid, filters, status badges, timestamps, and empty state.
- [ ] Load videos with `listVideos()` via TanStack Query and support local filter/search state.
- [ ] Link cards to `/library/:videoId`.
- [ ] Recreate Rendering & Preview with portrait preview, progress/status panel, metadata, and action controls.
- [ ] Support queued, rendering, completed, and failed mock states.

### Task 6: Implement Settings And Route Wiring

**Files:**
- Create: `frontend/src/features/settings/pages/SettingsPage.tsx`
- Create: `frontend/src/app/router.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] Recreate Stitch Settings sections and local preference controls.
- [ ] Add `/generate`, `/library`, `/library/:videoId`, and `/settings` routes.
- [ ] Redirect unknown paths to `/generate`.
- [ ] Ensure mobile navigation closes after route changes.

### Task 7: Verify Frontend And Scope Boundaries

**Files:**
- Modify only files under `frontend/` plus the approved design/plan docs.

- [ ] Run `pnpm build` in `frontend/`.
- [ ] Run `pnpm dev --host 127.0.0.1` and verify all four route families load.
- [ ] Verify desktop and narrow viewport layouts using the running app.
- [ ] Confirm no files under `clipcraft/workflows`, `clipcraft/supabase`, or `clipcraft/video-tools` changed.
