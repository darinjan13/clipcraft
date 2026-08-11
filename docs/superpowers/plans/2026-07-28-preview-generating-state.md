# Preview Generating State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove non-functional controls from the Preview frame until a completed video is available.

**Architecture:** Keep `PreviewCanvas`'s existing completed-video branch unchanged. Simplify its generating branch to show a preview image when present or the current dark gradient plus a small loading indicator when absent.

**Tech Stack:** React, TypeScript, Tailwind CSS, Lucide React.

---

### Task 1: Simplify Generating Preview State

**Files:**
- Modify: `frontend/src/features/preview/components/PreviewCanvas.tsx`

- [ ] **Step 1: Verify the current non-video branch contains inactive controls**

Read `PreviewCanvas.tsx` and confirm the `video.videoUrl ?` false branch renders the centered `Play` button, `Preview frame` label, and bottom action bar.

- [ ] **Step 2: Replace the non-video branch with display-only content**

Keep the existing `<video controls playsInline>` branch unchanged. Replace the false branch with the existing gradient layers, an optional preview image when `video.thumbnail` is available, and a non-interactive loading indicator:

```tsx
<>
  {video.thumbnail ? (
    <img
      className="absolute inset-0 size-full object-cover"
      src={video.thumbnail}
      alt="Generated video preview"
    />
  ) : (
    <div className="absolute inset-0 bg-aurora" />
  )}
  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/10" />
  <div className="relative size-5 rounded-full border-2 border-white/20 border-t-white/70 animate-spin" aria-label="Generating preview" />
</>
```

Remove the `Play`, `Volume2`, and `Maximize2` imports because the generating state no longer uses them.

- [ ] **Step 3: Build the frontend**

Run: `npm run build`

Expected: Vite completes successfully without TypeScript errors.
