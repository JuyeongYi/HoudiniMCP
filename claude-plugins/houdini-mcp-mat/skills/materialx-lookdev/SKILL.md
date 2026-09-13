---
name: materialx-lookdev
description: Create and debug MaterialX (and Karma/USD Preview) materials with the houdini_mcp_mat tools - shader graphs, textures, color spaces, assignments and presets. Use when building or fixing materials, attaching textures, when renders show wrong colors or flat grey, or when an assignment does not seem to apply.
---

# MaterialX look development

## Build

1. `create_material(parent, name, comment, kind="materialx")` — comes with the surface shader and output wired.
2. Add nodes with base `create_node`, connect them by **input/output name** with `connect_shader`, set values with `set_material_parms`.
3. `shader_inputs(path)` before connecting — it lists the exact input names and types a node accepts.

## MaterialX node pitfalls

- Many MaterialX nodes have a **signature menu** that decides their types. The menu is dynamic; set it by token (for example `color3`, `vector2`, `color3FA`, `vector2FA`), then the inputs change to match.
- Math nodes name inputs `in1`, `in2` (multiply's second input is `in2`), not `a`/`b`.
- `validate_material` runs the MaterialX library's own validation. Run it after wiring.

## Textures and color spaces

- `texture_info(file, usage=...)` opens the file first: resolution, channels, bit depth, statistics. A "roughness" texture with three identical channels or a black normal map shows up here.
- `assign_texture` checks the file before attaching.
- Color maps are sRGB; **data maps (roughness, height, normal, masks) must be `Raw`/linear**. Read valid values with `list_color_spaces` / `texture_parm_colorspaces`, set them with `set_color_space`.
- After changing files on disk, `reload_textures`.

## Assignment

- `assign_material(target, material, comment)` works on SOP, OBJ and LOP targets and verifies the binding took effect.
- `list_assignments(path)` reads the result, not parameters.
- **Colors from geometry**: when a SOP is imported into USD, a point `Cd` attribute overrides a primitive `Cd` for `displayColor`. If per-piece colors disappear, delete the point `Cd`.

## Presets

`save_material` writes a `.mtlx` and reads it back; `load_material` rebuilds a material from one; `list_presets` scans a directory.

## Verify

A material is only right when it renders right: check with a viewport snapshot in a render delegate (`set_viewport_renderer`) or a small render (render pack).
