---
name: visual-review
description: Check Houdini results visually - viewport snapshots, multi-frame sheets, flipbook videos and A/B comparison videos. Use after building or changing geometry, simulations or materials, when the user asks to see a result, or to compare before/after versions of a fix.
---

# Visual review

## Make sure you capture the right thing

Captures show exactly what the viewport shows. Before capturing:

- Check which node has the display flag (`node_flags`, `network_graph`). A user's node may be displayed instead of yours, or a DOP object may be displaying the raw simulation.
- Do not move the user's display flag without asking. If you move one temporarily, restore it.
- Use `set_viewport_camera` to see what a render camera sees, `frame_node` / `frame_all` to fit the view.

## Still images

- `viewport_snapshot` — one frame, returned as an image.
- `viewport_sequence` — up to 16 frames on one sheet with frame numbers. Use it for anything that changes over time (simulations, loops). Later frames of an uncached simulation take long on first capture.

## Videos (needs `FFMPEG_BIN_PATH`)

Both tools stop immediately if the `FFMPEG_BIN_PATH` environment variable (bin directory with ffmpeg and ffprobe) is not set in Houdini's environment; tell the user to set it and restart Houdini.

- `make_video` — omit `source` to capture the viewport over `start`–`end`; or pass an image sequence (`$F4`, `%04d`) or a video file. Missing frames are filled with the previous frame and reported. Linear EXR/HDR get `exposure` and an sRGB transform.
- `compare_videos` — two sources side by side (`layout="horizontal"`) or stacked (`"vertical"`), each with its own label. The shorter one holds its last frame.
- If a source video already has a label baked in by `make_video`, pass `label_a=None` / `label_b=None` for it, or the labels overlap.
- Both tools read the result back with ffprobe; check `frames`, `width`, `height` and `warnings` in the response.
- The user cannot see files you write unless you tell them the path (or send the file).

## When a picture is not enough

Pair images with numbers: `geometry_stats`, `attrib_stats`, `volume_info`, `image_info`. A picture can hide a flipped normal or an empty group; numbers can hide a wrong look.
