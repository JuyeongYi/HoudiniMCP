---
name: render-and-verify
description: Render Houdini scenes safely and verify the images with the houdini_mcp_render tools - pre-render validation, background husk renders, ROP renders, progress, logs and pixel-level checks of the results. Use whenever you start, monitor or check a render, or when a render is black, missing frames, blocked or taking over Houdini.
---

# Render and verify

## Before rendering

1. `validate_render(path)` on the LOP node or the usdrender/karma ROP — missing camera, render settings, broken assets.
2. `render_settings(path)` — resolution, products, delegate as the stage says.
3. Do a small check render first (few samples, one frame) before a sequence.

## Choosing how to render

| Situation | Use |
|---|---|
| Long render, Houdini must stay usable | `start_render` (husk in the background) |
| Short ROP render where you need the result now | `render_rop` (blocking) |

- `render_rop` runs on Houdini's main thread. A render longer than 120 s makes later tool calls fail with `MainThreadTimeout`. Keep blocking renders short.
- For ROP background rendering, **save the scene first** (`save_scene`). An unsaved scene opens a modal dialog that blocks Houdini.
- On a usdrender ROP, "render in background" is a **button** parameter; press it, do not set it.
- The ROP frame range parms (`f1`, `f2`) carry `$FSTART`/`$FEND` expressions by default. Remove the expressions/keys before setting numbers, or your values are ignored.

## While rendering

`render_status(job)` — progress; finished jobs are opened and pixel statistics are computed. `render_log(job, lines)` for husk errors. `cancel_render(job)` to stop.

## Verify the output

- `image_info(path, frame)` — resolution, AOVs, per-channel statistics; black or NaN images are flagged.
- `image_sequence_report(path, start, end)` — missing frames, black frames, flicker across the sequence.
- `image_preview(path, exposure=...)` — look at a frame.
- `compare_images(a, b)` — confirm a fix actually changed pixels.
- `list_aovs(path)` — AOVs really present in the file.
- For review, turn the sequence into a video with `make_video` (base pack) and send or point the user to it.

Apprentice/Education licenses watermark renders. Do not try to remove or work around the watermark.
