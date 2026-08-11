# ClipCraft Frontend Design

## Goal

Create a standalone React 19/Vite frontend in `frontend/` that faithfully implements the four current Stitch screens using local mock services and local state.

## Scope

Included:

- Generate Video screen
- Library screen
- Rendering & Preview screen
- Settings screen
- React Router navigation
- Shared responsive layout and reusable UI components
- TanStack Query mock service layer
- Zustand local preferences and draft state
- Responsive desktop-first behavior

Excluded:

- Backend connections
- Authentication, accounts, teams, billing, analytics, notifications, or workspace management
- Changes to backend, n8n, Supabase, or renderer files

## Visual Source

The Stitch project `9190303229075515588` is authoritative. Preserve its Lumina Cinematic design: dark charcoal surfaces, violet/blue accents, Inter and Geist typography, rounded glass panels, generous gutters, and existing page hierarchy.

## Information Architecture

- `/generate` renders Generate Video and is the default route.
- `/library` renders Library.
- `/library/:videoId` renders Rendering & Preview for a selected mock video.
- `/settings` renders Settings.
- Unknown routes redirect to `/generate`.

The shared shell owns sidebar navigation, route-aware active state, mobile navigation, and the global visual background. Pages own their primary actions and content state.

## State And Services

`src/features/videos/api/videoService.ts` exposes `createVideo`, `getVideoStatus`, `getVideo`, and `listVideos`. All functions return typed mock data with small artificial delays. TanStack Query consumes read operations and invalidates the library after creation. Zustand stores the generate draft and local settings. No network requests are made.

## Component Boundaries

- `src/components/layout/AppShell.tsx`: shared responsive shell and navigation.
- `src/components/ui/*`: reusable buttons, panels, badges, progress, inputs, selects, and empty/loading states.
- `src/features/generate/*`: brief form and generation controls.
- `src/features/library/*`: video grid, filters, and video cards.
- `src/features/preview/*`: rendering status, preview frame, metadata, and actions.
- `src/features/settings/*`: local preference controls.

## Interaction States

- Generate: idle draft, submitting, rendering, completed, and error.
- Library: loading, populated, empty filter result, and error.
- Preview: queued, rendering progress, completed, and failed.
- Settings: immediate local updates with a saved indicator.

## Verification

- `pnpm install` completes in `frontend/`.
- `pnpm dev` starts the Vite app.
- Generate, Library, Library detail/Preview, and Settings routes render.
- Navigation works on desktop and mobile widths.
- TypeScript/build checks pass.
- Backend and workflow files remain untouched.
