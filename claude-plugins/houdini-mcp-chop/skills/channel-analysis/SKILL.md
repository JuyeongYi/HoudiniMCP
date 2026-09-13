---
name: channel-analysis
description: Analyse, filter, transfer and bake animation channels in Houdini with the houdini_mcp_chop tools - channel statistics, loop and spike detection, filters with before/after comparison, CHOP to keyframes, channel files and audio waveforms. Use when checking whether an animation loops, finding pops or jitter, smoothing motion, baking expressions or CHOPs to keys, or driving animation from audio.
---

# Channel analysis

Treat channels as data to be judged, not lists of numbers to read. Setting a single key or expression is the base pack's `anim` tools; this pack is for analysis and bulk transfer.

## Look at channels

- `list_channels(path)` — names, sample counts, value ranges.
- `channel_stats(path, channels)` — the main analysis: ranges, velocity, stillness, loop check, spikes and a sparkline per channel.
- `channel_samples(path, channel, start_frame, end_frame, max_points)` — actual values over a window when you need them.

## Judge

- `check_loop(path, tolerance)` — whether the end joins the start (value and slope) within a fraction of the value range.
- `find_spikes(path, threshold)` — frames where a channel pops. Lower threshold is more sensitive.

## Change

- Create a network with `create_chop_network`, nodes with `create_chop_node(parent, node_type, comment, parms, inputs)`.
- `apply_chop_filter(path, filter, comment, strength)` — `lag`, `smooth`, `limit`, `shift`, `resample`, `spring`, `jiggle`; returns before/after statistics so you can see whether the spike or jitter is gone.

## Transfer

- `import_from_parms(parent, parms, comment)` — animated parameters into a Channel CHOP.
- `set_chop_export(path, enable)` — drive parameters live from the CHOP.
- `export_to_keyframes(path, targets)` — bake CHOP channels to keys and verify the values match.
- `bake_channels(parms, start_frame, end_frame, step)` — bake expressions on parameters to keys and verify.

## Files and audio

- `export_channels` / `import_channels` — Houdini clip files (`.clip`, `.bclip`).
- `export_parm_channels` / `import_parm_channels` — `.chan` / `.bchan` for other DCCs (column order = parameter order).
- `load_audio(parent, file_path, comment)` — reads audio (`.wav` verified) and returns a waveform envelope; `set_audio_flag=True` makes it the scene audio.
