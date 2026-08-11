# Preview Generating State

## Goal

Remove non-functional video controls from the Preview frame until a completed
video is available.

## Behavior

- A completed video continues to render in the existing native HTML5 `video`
  element with browser-provided controls.
- During generation, the frame renders no play buttons, scrubber, volume
  control, or fullscreen control.
- When a preview image exists, it fills the phone frame.
- Without a preview image, the frame shows the existing dark gradient and a
  subtle loading indicator.

## Scope

Only `PreviewCanvas` changes. No backend, API, workflow, or routing changes.
