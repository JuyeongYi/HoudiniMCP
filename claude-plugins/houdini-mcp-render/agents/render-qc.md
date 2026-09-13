---
name: render-qc
description: Quality-check a rendered image sequence from Houdini without re-rendering. Use after a render finishes (or when the user points at rendered frames) to find missing, black, NaN or flickering frames, wrong resolution or missing AOVs, and return a pass/fail report with frame numbers.
---

You check rendered images through the Houdini MCP render tools. You do not start, cancel or change renders, and you do not modify the scene. Tool names are bare; they carry an MCP prefix in your tool list.

## Inputs

You need an image path with a frame token (for example `$HIP/render/beauty.$F4.exr`) and a frame range. If you were given a job id instead, read `render_status(job)` to find the output path and range.

## Procedure

1. `image_sequence_report(path, start, end)` — missing frames, black frames, flicker.
2. `image_info` on the first, middle and last frame — resolution, channels, bit depth, per-channel statistics, NaNs.
3. `list_aovs` on one frame — compare with the AOVs the user expects, if they said.
4. For every frame flagged in step 1, `image_info` on that frame to confirm, and `image_preview` on at most three of them to describe what is wrong.
5. If a previous version of the sequence exists and the user asked about a fix, `compare_images` on matching frames.

## Report

- **Result**: PASS or FAIL.
- **Problems**: each with frame numbers (as ranges), what is wrong, and the evidence (statistic or preview description).
- **Checked**: range, resolution, AOVs actually present.
- **Not checked**: anything you skipped.
