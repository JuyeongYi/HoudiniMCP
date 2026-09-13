---
name: sop-procedural-modeling
description: Build and edit SOP geometry procedurally with the houdini_mcp_sop tools - primitives, curves, copy to points, bevel/extrude/boolean, remesh and triangulate, attributes, groups and UVs - checking measured results after each step. Use when modelling in SOPs, preparing geometry for simulation or export, or fixing topology, groups or UVs.
---

# Procedural SOP modelling

## Build in small measured steps

Every editing tool in this pack cooks the new node and returns before/after statistics. Read them after each call:

- Point/primitive counts that did not change mean the operation did not apply (wrong group, zero offset).
- A bounding box that jumped means a transform or pivot is wrong.
- `create_group` returns how many elements matched; zero means the pattern, bounding box or normal filter is wrong.

Name each node by role and give it an English `comment`. Chain nodes by passing the previous node's path as the next `path`.

## Tool choice

| Goal | Tools |
|---|---|
| Base shapes | `create_primitive`, `create_curve`, `revolve_profile`, `skin_sections` |
| Instancing | `copy_to_points` (`pack=True` for many copies) |
| Detail | `bevel`, `extrude_faces`, `bridge_edges`, `mirror_geometry`, `boolean_op` |
| Topology | `convert_geometry`, `triangulate`, `remesh_geometry`, `reduce_polygons`, `delete_geometry` |
| Placement | `transform_geometry` |
| Attributes | `create_attribute`, `add_normals`, `attrib_stats`, `export_attribute` |
| Groups | `create_group`, `group_members` |
| UVs | `uv_project`, `auto_uv`, `uv_report` |
| Queries | `nearest_point`, `nearest_prim`, `ray_intersect`, `prim_intrinsics`, `volume_info` |

## Rules that save time

- **Simulation meshes**: cloth and soft bodies want evenly distributed triangles. Use `remesh_geometry` with a `target_size`, then check the result with `geometry_stats` before building constraints.
- **Bevel offsets** that are large relative to the geometry flip polygons. Start small and look.
- **Large data**: never pull every point value into the conversation. Use `attrib_stats` for distributions, or `export_attribute` to write a `.npy` file.
- **UVs**: run `uv_report` after `uv_project` / `auto_uv`; it reports islands, overlaps and out-of-range UVs.
- **Normals**: `add_normals` warns before overwriting existing `N`. Point `N` on a remeshed surface changes shading; check with a snapshot.

## Verify

Finish with `geometry_stats` on the output node and a `viewport_snapshot`. For complex assemblies, `viewport_sequence` from several views (`set_viewport_direction`) catches flipped or hidden parts.
