# houdini_mcp_cop

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_cop.json` |
| requires | `houdini_mcp` |
| Tools | 2 |
| Modules (`TOOL_MODULES`) | `preview` |

## Overview

```text
COP (Copernicus) pack - look at the results of image networks.

    preview  cop_preview (node outputs as pictures), cop_layer_info (layer statistics)

Why it exists (2026-09-13, castle destruction scene): stone and ground textures were built in COP,
but there was no way to see the result, so they were exported and turned into PNGs with an
external tool. Single-channel maps came out black, so they were attached to materials without
really being checked, and the spongy quality only showed up in the render. The model needs to see
the equivalent of the COP composite view directly.

Legacy COP2 (cop2net) is not handled. Only Copernicus (copnet), available since Houdini 20.5, is accepted.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`cop_preview`](#cop_preview) | `preview` | Shows the images a COP node produces as pictures. Replaces the composite view. |  |
| [`cop_layer_info`](#cop_layer_info) | `preview` | Returns layer information for each output of a COP node as numbers. |  |

## Details by module

### `preview`

See the images COP nodes produce and read them as numbers.

#### cop_preview

```python
cop_preview(nodes: list[str], frame: float | None = None, tile_size: int = 384, columns: int = 4, normalize: str = 'auto')
```

Shows the images a COP node produces as pictures. Replaces the composite view.

| Argument | Type | Default | Description |
|---|---|---|---|
| `nodes` | `list[str]` | required | COP node paths. To pick an output, append its name or index after ":". Up to 16. Example: ["/img/tex/noise1", "/img/tex/worley1:dist2"] |
| `frame` | `float \| None` | `None` | Frame to view. Defaults to the current frame. |
| `tile_size` | `int` | `384` | Side length of one tile in pixels. The image aspect ratio is kept. |
| `columns` | `int` | `4` | Number of tiles per row. |
| `normalize` | `str` | `'auto'` | "auto", "on" (always stretch to the value range), "off" (always clamp to 0..1). |

#### cop_layer_info

```python
cop_layer_info(path: str, frame: float | None = None)
```

Returns layer information for each output of a COP node as numbers.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | COP node path. Example: "/img/tex/worley1" |
| `frame` | `float \| None` | `None` | Frame to view. Defaults to the current frame. |
