---
name: usd-stage-debugging
description: Inspect and edit USD stages in Solaris with the houdini_mcp_lop tools - composed prims, attribute values and where they come from, layers, references, variants and lights. Use when geometry, materials or lights are missing or wrong on a LOP stage, when SOP data does not arrive in USD, or before rendering a stage.
---

# USD stages in Solaris

## Query the composed stage, not node parameters

These tools read the `pxr.Usd.Stage` a LOP node produces, after sublayers, references, payloads, variants and inherits have been applied. Node parameters can say one thing while the composed stage says another.

1. `stage_info(lop)` — prim counts by type, layers, up axis, time range.
2. `list_prims(lop, root, depth, limit)` / `find_prims(lop, pattern)` — always keep `limit`; stages are large.
3. `prim_info(lop, primpath)` — type, visibility, bounds, material binding, variants.
4. `get_usd_attribute(lop, primpath, name, frame)` — the resolved value.
5. **Wrong value?** `prim_origin(lop, primpath, attribute=...)` shows which layer and arc wins. `layer_contents(lop, identifier, primpath)` shows the USDA of that layer.

## Editing

`set_usd_attribute`, `set_variant`, `add_reference`, `add_sublayer`, `create_light`, `set_light` each insert a LOP node after the given node, with your English comment. Continue the chain from the node they return.

## SOP data that goes missing in USD

- **Loose points** (points without primitives) are skipped on import. Give them a particle system (for example an Add SOP creating points as a particle primitive) before importing.
- **Houdini volumes** do not import; convert to VDB first (`convertvdb`).
- **Pyro volumes** need a pyro shader (`kma_pyroshader`) inside a `collect` material node to render.
- Per-piece colors: a point `Cd` overrides primitive `Cd` for `displayColor` (see the materials skill).

Check the result with `prim_stats(lop, primpath, geometry_counts=True)` after import.

## Before rendering

`validate_stage(lop)` finds broken asset paths, empty prims and geometry without material bindings; `check_render=True` also checks render settings and camera. Rendering itself is the render pack's job.
