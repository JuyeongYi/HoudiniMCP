# houdini_mcp_render

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_render.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 13 |
| Modules (`TOOL_MODULES`) | `settings`, `check`, `run`, `result` |

## Overview

```text
Pack that starts renders, tracks their progress and actually reads the result images to check them.

This pack exists for that last part. A tool that starts a render and returns "done" cannot tell
when pitch-black frames come out. When a render finishes, the tools here read the pixels with
OpenImageIO, compute per-channel statistics, and say so if the image is black or contains NaNs.

Modules:

    settings   reads render settings through the UsdRender schema
    check      checks what is missing before a render starts
    run        husk background renders and blocking ROP renders
    result     reads result images for statistics, thumbnails and comparisons

Modules starting with an underscore (_common, _usdrender, _image) are helpers and not listed here.
register_pack loads only the modules listed in TOOL_MODULES, each in isolation.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`render_settings`](#render_settings) | `settings` | Reads the render settings of the stage a LOP node produces, through the UsdRender schema. |  |
| [`list_renderers`](#list_renderers) | `settings` | Hydra render delegates actually usable on this installation. |  |
| [`validate_render`](#validate_render) | `check` | Scans a stage to check whether it is ready to render. |  |
| [`start_render`](#start_render) | `run` | Starts a background render with husk and returns a job handle. Houdini does not block. |  |
| [`render_status`](#render_status) | `run` | Progress of render jobs. For finished jobs, the result images are actually read and statistics returned. |  |
| [`render_log`](#render_log) | `run` | The tail of the husk log a render job wrote. |  |
| [`cancel_render`](#cancel_render) | `run` | Stops a running render. |  |
| [`render_rop`](#render_rop) | `run` | Renders a ROP and actually opens the produced files to return what was rendered. |  |
| [`image_info`](#image_info) | `result` | Opens a rendered image and reports resolution, channels (AOVs), bit depth and per-channel pixel statistics. |  |
| [`image_preview`](#image_preview) | `result` | Shrinks a rendered image to a thumbnail and returns it as a picture, for visual checks. |  |
| [`compare_images`](#compare_images) | `result` | Compares two renders pixel by pixel, to confirm that a fix really changed something. |  |
| [`image_sequence_report`](#image_sequence_report) | `result` | Scans a whole rendered sequence for missing frames, black frames and flicker. |  |
| [`list_aovs`](#list_aovs) | `result` | AOVs actually present in an image file, read from the result rather than the render settings. |  |

## Details by module

### `settings`

Tools that read render settings.

#### render_settings

```python
render_settings(path: str, settings_prim: str | None = None)
```

Reads the render settings of the stage a LOP node produces, through the UsdRender schema.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | LOP node path. Example: /stage/karma_settings |
| `settings_prim` | `str \| None` | `None` | RenderSettings prim path to read. Defaults to the stage default. |

#### list_renderers

```python
list_renderers()
```

Hydra render delegates actually usable on this installation.

### `check`

Tool that checks before a render starts.

#### validate_render

```python
validate_render(path: str, settings_prim: str | None = None)
```

Scans a stage to check whether it is ready to render.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | LOP node path, or a usdrender_rop / karma ROP path. Given a ROP, the LOP it points to is followed. |
| `settings_prim` | `str \| None` | `None` | RenderSettings prim to check. Defaults to the stage default. |

### `run`

Tools that actually start renders.

#### start_render

```python
start_render(target: str, output: str | None = None, frame: float | None = None, frame_count: int = 1, frame_inc: float = 1.0, resolution: list[int] | None = None, samples: int | None = None, renderer: str | None = None, settings_prim: str | None = None, snapshot_seconds: float | None = None, threads: int = 0, skip_validation: bool = False)
```

Starts a background render with husk and returns a job handle. Houdini does not block.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | LOP node path, or the path of a .usd file to render. |
| `output` | `str \| None` | `None` | Output image path override. If omitted, the one from RenderSettings is used. Frame variables such as $F4 can be used as is. |
| `frame` | `float \| None` | `None` | Start frame. Defaults to the USD startTimeCode. |
| `frame_count` | `int` | `1` | Number of frames to render. |
| `frame_inc` | `float` | `1.0` | Frame increment. |
| `resolution` | `list[int] \| None` | `None` | [width, height] override. |
| `samples` | `int \| None` | `None` | Samples per pixel. 4–16 is enough for check renders. |
| `renderer` | `str \| None` | `None` | Hydra delegate name. See `list_renderers`. |
| `settings_prim` | `str \| None` | `None` | RenderSettings prim path to use. |
| `snapshot_seconds` | `float \| None` | `None` | Save a partial image every this many seconds. Useful to preview a long render midway. |
| `threads` | `int` | `0` | Number of threads to use. 0 means all. |
| `skip_validation` | `bool` | `False` | Skip the pre-render check. |

#### render_status

```python
render_status(job: str | None = None, with_stats: bool = True)
```

Progress of render jobs. For finished jobs, the result images are actually read and statistics returned.

| Argument | Type | Default | Description |
|---|---|---|---|
| `job` | `str \| None` | `None` | Job id. If omitted, all jobs of this session are summarised. |
| `with_stats` | `bool` | `True` | Whether to open the result images of finished jobs and compute statistics. False keeps the response light for large sequences. |

#### render_log

```python
render_log(job: str, lines: int = 40)
```

The tail of the husk log a render job wrote.

| Argument | Type | Default | Description |
|---|---|---|---|
| `job` | `str` | required | Job id. |
| `lines` | `int` | `40` | Number of lines to return. Up to 200. |

#### cancel_render

```python
cancel_render(job: str)
```

Stops a running render.

| Argument | Type | Default | Description |
|---|---|---|---|
| `job` | `str` | required | Job id. |

#### render_rop

```python
render_rop(path: str, frame_range: list[float] | None = None, output_file: str | None = None, ignore_inputs: bool = False, inspect_outputs: bool = True)
```

Renders a ROP and actually opens the produced files to return what was rendered.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | ROP node path. Examples: /out/karma_beauty, /stage/usdrender_rop1 |
| `frame_range` | `list[float] \| None` | `None` | [start, end] or [start, end, increment]. If omitted, the ROP settings are used. |
| `output_file` | `str \| None` | `None` | Output path override. |
| `ignore_inputs` | `bool` | `False` | True renders only this ROP and skips its input ROPs. |
| `inspect_outputs` | `bool` | `True` | Whether to open the produced images and compute pixel statistics. |

### `result`

Tools that read render result images.

#### image_info

```python
image_info(path: str, frame: float | None = None, subimage: int = 0)
```

Opens a rendered image and reports resolution, channels (AOVs), bit depth and per-channel pixel statistics.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Image path. Houdini variables such as $HIP/$F4 are allowed. |
| `frame` | `float \| None` | `None` | Frame substituted when the path contains $F. |
| `subimage` | `int` | `0` | Subimage (AOV) index to inspect. |

#### image_preview

```python
image_preview(path: str, width: int = 512, frame: float | None = None, subimage: int = 0, exposure: float = 0.0)
```

Shrinks a rendered image to a thumbnail and returns it as a picture, for visual checks.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Image path. |
| `width` | `int` | `512` | Thumbnail width in pixels. Height follows the aspect ratio. |
| `frame` | `float \| None` | `None` | Frame substituted when the path contains $F. |
| `subimage` | `int` | `0` | Subimage (AOV) index to view. |
| `exposure` | `float` | `0.0` | Exposure adjustment in stops, e.g. +2 for a dark render. |

#### compare_images

```python
compare_images(a: str, b: str, frame: float | None = None, fail_threshold: float = 0.01, warn_threshold: float = 0.001)
```

Compares two renders pixel by pixel, to confirm that a fix really changed something.

| Argument | Type | Default | Description |
|---|---|---|---|
| `a` | `str` | required | First image path. |
| `b` | `str` | required | Second image path. |
| `frame` | `float \| None` | `None` | Frame substituted when both paths contain $F. |
| `fail_threshold` | `float` | `0.01` | Differences larger than this count as 'failing pixels'. |
| `warn_threshold` | `float` | `0.001` | Differences larger than this count as 'warning pixels'. |

#### image_sequence_report

```python
image_sequence_report(path: str, start: float, end: float, inc: float = 1.0)
```

Scans a whole rendered sequence for missing frames, black frames and flicker.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path containing a frame variable such as $F4. Example: $HIP/render/beauty.$F4.exr |
| `start` | `float` | required | Start frame. |
| `end` | `float` | required | End frame. |
| `inc` | `float` | `1.0` | Frame increment. |

#### list_aovs

```python
list_aovs(path: str, frame: float | None = None)
```

AOVs actually present in an image file, read from the result rather than the render settings.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Image path. |
| `frame` | `float \| None` | `None` | Frame substituted when the path contains $F. |
