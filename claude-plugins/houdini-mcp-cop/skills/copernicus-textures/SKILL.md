---
name: copernicus-textures
description: Build procedural textures in Houdini Copernicus (copnet) and check them as images and statistics with the houdini_mcp_cop tools, then export them correctly. Use when creating or editing COP networks, when a texture looks wrong in a render, when single-channel maps look black, or before exporting COP results to image files.
---

# Copernicus textures

Only Copernicus networks (`copnet`) are supported, not legacy COP2 (`cop2net`).

## Look at every step

A COP network's result is an image; you cannot judge it from parameters.

- `cop_preview(nodes, frame, tile_size, columns)` — one or more COP outputs as a contact sheet. Pick an output with `path:output` (name or index), e.g. `/img/tex/worley1:dist2`. Up to 16 tiles; use it to compare stages side by side.
  - Display adapts to the layer type: IDs get hash colors, data layers are stretched per channel (`normalize="auto"`), color layers are shown in sRGB. Use `normalize="off"` to see clipping in 0..1.
- `cop_layer_info(path)` — per output: resolution, channels, storage type, value ranges. A height map with min = max is flat; a mask stuck at 0 or 1 is clipped.

Preview after every change. Texture quality problems found only in the render cost a render cycle.

## Building

- Create nodes with the base `create_node` inside the copnet; connect with `connect_nodes` (use output indices for multi-output nodes).
- Noise node types are specific: `fractalnoise`, `worleynoise`, `cellularnoise`, `curlnoise`, `phasornoise`... there is no plain `noise` type. Use `list_node_types(category="Cop", pattern="*noise*")`.
- A `file` COP has **no output connectors until it has cooked a valid file path**. Set the path and cook before wiring it.
- Copernicus `wrangle` runs VEX on pixels; `opencl` runs OpenCL kernels.

## Exporting

- Export through a `rop_image` ROP (`coppath`, `copoutput`, resolution, `colorconversion`).
- Data maps (height, roughness, normal, masks): no color conversion (raw). Color maps: sRGB.
- Background export needs a **saved scene** (`save_scene` first).
- Apprentice/Education licenses watermark exported images. Do not try to remove or bypass the watermark (for example by writing layer buffers directly).
- Check exported files with `texture_info` (materials pack) and attach them with `assign_texture` using the right color space.
