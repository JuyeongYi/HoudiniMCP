# houdini_mcp_sop

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_sop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 30 |
| Modules (`TOOL_MODULES`) | `create`, `polyedit`, `topology`, `attribs`, `groups`, `uv`, `query` |

## Overview

```text
SOP tool pack — creates, edits and reads geometry.

Context-independent queries (`geometry_stats`, `list_attributes`, `sample_points` and others) live
in the geometry module of `houdini_mcp_base`. This pack holds what only makes sense in SOPs.

    create     primitive and curve creation, copying to points
    polyedit   polygon editing — bevel, extrude, bridge, mirror, revolve, skin, boolean
    topology   topology changes — convert, triangulate, remesh, reduce, transform, delete
    attribs    attributes — numpy bulk statistics, normals, attribute creation
    groups     group creation and member queries
    uv         UV projection, auto UVs, UV quality reports
    query      proximity queries, ray intersection, intrinsics, volumes, file export

The editing tools in this pack do not stop at creating a node. They always cook it and return a
before/after comparison of statistics, so the model does not have to ask again whether the bevel
took effect.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`create_primitive`](#create_primitive) | `create` | Creates a basic shape SOP, cooks it and returns the resulting statistics. | ✓ |
| [`create_curve`](#create_curve) | `create` | Creates a curve from a list of points. | ✓ |
| [`copy_to_points`](#copy_to_points) | `create` | Copies source geometry onto each point of a target. | ✓ |
| [`bevel`](#bevel) | `polyedit` | Bevels edges or points (PolyBevel). Returns a before/after comparison of point and primitive counts. | ✓ |
| [`extrude_faces`](#extrude_faces) | `polyedit` | Extrudes faces (PolyExtrude). For an inset only, give distance=0 and inset>0. | ✓ |
| [`bridge_edges`](#bridge_edges) | `polyedit` | Creates faces between two edge loops (PolyBridge). | ✓ |
| [`mirror_geometry`](#mirror_geometry) | `polyedit` | Reflects geometry across a plane. | ✓ |
| [`revolve_profile`](#revolve_profile) | `polyedit` | Revolves a profile curve around an axis to make a surface of revolution (lathe). | ✓ |
| [`skin_sections`](#skin_sections) | `polyedit` | Skins faces between section curves (Skin/loft). | ✓ |
| [`boolean_op`](#boolean_op) | `polyedit` | Performs a boolean operation on two meshes (Boolean SOP). | ✓ |
| [`convert_geometry`](#convert_geometry) | `topology` | Changes primitive types (Convert SOP). | ✓ |
| [`triangulate`](#triangulate) | `topology` | Splits polygons into triangles (or up to a given number of sides) (Divide SOP). | ✓ |
| [`remesh_geometry`](#remesh_geometry) | `topology` | Rebuilds the mesh with evenly sized triangles (Remesh SOP). | ✓ |
| [`reduce_polygons`](#reduce_polygons) | `topology` | Reduces the polygon count (PolyReduce SOP). | ✓ |
| [`transform_geometry`](#transform_geometry) | `topology` | Moves, rotates and scales geometry or part of it (Transform SOP). | ✓ |
| [`delete_geometry`](#delete_geometry) | `topology` | Deletes what a group or pattern matches (Blast SOP). | ✓ |
| [`attrib_stats`](#attrib_stats) | `attribs` | Returns statistics about the distribution of a whole attribute. |  |
| [`export_attribute`](#export_attribute) | `attribs` | Writes all values of an attribute to a .npy file and returns the path. |  |
| [`add_normals`](#add_normals) | `attribs` | Creates normals (Normal SOP). Warns before overwriting existing ones. | ✓ |
| [`create_attribute`](#create_attribute) | `attribs` | Creates an attribute filled with a constant value (AttribCreate SOP). | ✓ |
| [`create_group`](#create_group) | `groups` | Creates a group and returns **how many elements actually matched** (GroupCreate SOP). | ✓ |
| [`group_members`](#group_members) | `groups` | Returns what a group contains. Large groups are folded into ranges. |  |
| [`uv_report`](#uv_report) | `uv` | Checks whether UVs are laid out properly. |  |
| [`uv_project`](#uv_project) | `uv` | Creates UVs by projection (UVProject SOP) and returns a check of UV quality afterwards. | ✓ |
| [`auto_uv`](#auto_uv) | `uv` | Automatically flattens UVs and lays them out in 0–1, returning a check of the result quality. | ✓ |
| [`nearest_point`](#nearest_point) | `query` | Finds the points closest to a given position. |  |
| [`nearest_prim`](#nearest_prim) | `query` | Finds the primitive closest to a given position and the closest point on it. |  |
| [`ray_intersect`](#ray_intersect) | `query` | Casts a ray at geometry and finds where it hits. |  |
| [`prim_intrinsics`](#prim_intrinsics) | `query` | Reads a primitive's intrinsics. |  |
| [`volume_info`](#volume_info) | `query` | Returns resolution, voxel size and value range of volume/VDB primitives. |  |

## Details by module

### `create`

Tools that create geometry from scratch.

#### create_primitive

```python
create_primitive(parent: str, shape: str, comment: str, name: str | None = None, size: Sequence[float] | None = None, center: Sequence[float] | None = None, rotate: Sequence[float] | None = None, divisions: Sequence[int] | None = None, prim_type: str = 'poly', platonic_solid: str = 'cube')
```

Creates a basic shape SOP, cooks it and returns the resulting statistics.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Network to hold the SOP. Example: /obj/castle |
| `shape` | `str` | required | box / sphere / tube / grid / torus / circle / platonic |
| `comment` | `str` | required | What this node is for. Required. Stored in the scene, so write it in English. Example: "Wall body, 20 x 4 x 1.2" |
| `name` | `str \| None` | `None` | Node name, showing its role. Examples: wall_body, tower_shaft |
| `size` | `Sequence[float] \| None` | `None` | Three size values per shape. box=(x,y,z), sphere=(rx,ry,rz), tube=(rad_bottom, rad_top, height), grid=(x,y), torus=(major,minor), circle=(rx,ry), platonic=(radius,). Node defaults if omitted. |
| `center` | `Sequence[float] \| None` | `None` | Center position (x,y,z). Origin if omitted. |
| `rotate` | `Sequence[float] \| None` | `None` | Rotation (rx,ry,rz) in degrees. No rotation if omitted. |
| `divisions` | `Sequence[int] \| None` | `None` | Division counts. box=(x,y,z), others=(rows,cols), circle=(divs,). |
| `prim_type` | `str` | `'poly'` | poly / polysoup / mesh / nurbs / bezier / prim / points. If the shape does not support the value, the usable values are listed. |
| `platonic_solid` | `str` | `'cube'` | Only when shape="platonic". tetrahedron / cube / octahedron / icosahedron / dodecahedron / soccerball / teapot. |

#### create_curve

```python
create_curve(parent: str, points: Sequence[Sequence[float]], comment: str, name: str | None = None, closed: bool = False, curve_type: str = 'poly')
```

Creates a curve from a list of points.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Network to hold the SOP. Example: /obj/castle |
| `points` | `Sequence[Sequence[float]]` | required | List of point coordinates. Example: [[0,0,0], [1,2,0], [3,0,0]] |
| `comment` | `str` | required | What this curve is. Required. In English. |
| `name` | `str \| None` | `None` | Node name, showing its role. Examples: tower_profile, path_spine |
| `closed` | `bool` | `False` | Whether to join the start and end points. |
| `curve_type` | `str` | `'poly'` | poly / nurbs / bezier. |

#### copy_to_points

```python
copy_to_points(source: str, target: str, comment: str, name: str | None = None, target_group: str = '', pack: bool = False, pivot: str = 'centroid', use_target_orientation: bool = True)
```

Copies source geometry onto each point of a target.

| Argument | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | required | SOP path of the geometry to copy. |
| `target` | `str` | required | SOP path whose points are the copy locations. |
| `comment` | `str` | required | What is copied and why. Required. In English. |
| `name` | `str \| None` | `None` | Node name. Example: copy_merlons |
| `target_group` | `str` | `''` | Group/pattern when only some target points are used. Example: "@type==1" |
| `pack` | `bool` | `False` | True packs the copies. Saves a lot of memory for large counts. |
| `pivot` | `str` | `'centroid'` | origin / centroid. Which part of the source is placed on the point. |
| `use_target_orientation` | `bool` | `True` | Whether to rotate by the target points' N/up/orient attributes. |

### `polyedit`

Tools that edit polygons — bevel, extrude, bridge, mirror, revolve, skin, boolean.

#### bevel

```python
bevel(path: str, comment: str, offset: float = 0.05, group: str = '*', group_type: str = 'edges', divisions: int = 1, shape: str = 'round', name: str | None = None)
```

Bevels edges or points (PolyBevel). Returns a before/after comparison of point and primitive counts.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is bevelled and why. Required. In English. Example: "Soften wall top edges, 0.05" |
| `offset` | `float` | `0.05` | Bevel width. Too large relative to the geometry flips polygons. |
| `group` | `str` | `'*'` | Target pattern. Edges as "*" or "p0-1 p1-2", points/prims as number ranges. |
| `group_type` | `str` | `'edges'` | edges / points / prims / guess. |
| `divisions` | `int` | `1` | Fillet divisions. 1 gives a sharp chamfer; more makes it rounder. |
| `shape` | `str` | `'round'` | round / chamfer / crease / solid / none. |
| `name` | `str \| None` | `None` | Node name, showing its role. Example: bevel_wall_top |

#### extrude_faces

```python
extrude_faces(path: str, comment: str, distance: float = 0.1, inset: float = 0.0, group: str = '', divisions: int = 1, split_type: str = 'elements', output_front: bool = True, output_side: bool = True, output_back: bool = False, name: str | None = None)
```

Extrudes faces (PolyExtrude). For an inset only, give distance=0 and inset>0.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is extruded and why. Required. In English. Example: "Extrude merlon tops 0.4 up" |
| `distance` | `float` | `0.1` | Extrusion distance. Negative values cut inward. |
| `inset` | `float` | `0.0` | How much the extruded face shrinks inward. Positive values make it narrower. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `divisions` | `int` | `1` | Side face divisions. |
| `split_type` | `str` | `'elements'` | elements (one face at a time) / components (connected pieces together). |
| `output_front` | `bool` | `True` | Whether to keep the extruded front faces. |
| `output_side` | `bool` | `True` | Whether to create side faces. |
| `output_back` | `bool` | `False` | Whether to keep the back faces in the original place. Turn on when hollowing out. |
| `name` | `str \| None` | `None` | Node name. Example: extrude_merlon_tops |

#### bridge_edges

```python
bridge_edges(path: str, comment: str, source_group: str, destination_group: str, divisions: int = 1, keep_input: bool = True, name: str | None = None)
```

Creates faces between two edge loops (PolyBridge).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. Both loops must be in this geometry. |
| `comment` | `str` | required | What is bridged. Required. In English. |
| `source_group` | `str` | required | Edge/primitive group name or pattern of the start loop. |
| `destination_group` | `str` | required | Edge/primitive group name or pattern of the end loop. |
| `divisions` | `int` | `1` | Divisions along the bridged span. |
| `keep_input` | `bool` | `True` | Whether to keep the original geometry as well. |
| `name` | `str \| None` | `None` | Node name. Example: bridge_tower_to_wall |

#### mirror_geometry

```python
mirror_geometry(path: str, comment: str, direction: Sequence[float] | None = None, origin: Sequence[float] | None = None, keep_original: bool = True, consolidate: bool = True, group: str = '', name: str | None = None)
```

Reflects geometry across a plane.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is mirrored and why. Required. In English. |
| `direction` | `Sequence[float] \| None` | `None` | Normal of the reflection plane (x,y,z). Default (1,0,0) — symmetric across the YZ plane. |
| `origin` | `Sequence[float] \| None` | `None` | Point the reflection plane passes through (x,y,z). Default origin. |
| `keep_original` | `bool` | `True` | Whether to keep the original. False keeps only the reflection. |
| `consolidate` | `bool` | `True` | Whether to fuse overlapping points on the plane, removing the seam of symmetric modelling. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: mirror_wall_east |

#### revolve_profile

```python
revolve_profile(path: str, comment: str, axis: Sequence[float] | None = None, origin: Sequence[float] | None = None, divisions: int = 16, begin_angle: float = 0.0, end_angle: float = 360.0, cap: bool = False, name: str | None = None)
```

Revolves a profile curve around an axis to make a surface of revolution (lathe).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP path that outputs the profile curve. |
| `comment` | `str` | required | What is being made. Required. In English. Example: "Revolve tower profile into cone roof" |
| `axis` | `Sequence[float] \| None` | `None` | Rotation axis direction (x,y,z). Default (0,1,0) — the Y axis. |
| `origin` | `Sequence[float] \| None` | `None` | Point the axis passes through (x,y,z). Default origin. |
| `divisions` | `int` | `16` | Divisions around. More is smoother. |
| `begin_angle` | `float` | `0.0` | Start angle (degrees), for partial revolutions. |
| `end_angle` | `float` | `360.0` | End angle (degrees). 360 is a full turn. |
| `cap` | `bool` | `False` | Whether to cap the ends of a partial revolution. |
| `name` | `str \| None` | `None` | Node name. Example: revolve_tower_roof |

#### skin_sections

```python
skin_sections(path: str, comment: str, close_along_sections: bool = False, name: str | None = None)
```

Skins faces between section curves (Skin/loft).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP path that outputs the section curves. They are joined in primitive order. |
| `comment` | `str` | required | What is skinned. Required. In English. |
| `close_along_sections` | `bool` | `False` | Whether to join the last section to the first. |
| `name` | `str \| None` | `None` | Node name. Example: skin_roof_sections |

#### boolean_op

```python
boolean_op(path_a: str, path_b: str, comment: str, operation: str = 'union', subtract_order: str = 'aminusb', a_is_solid: bool = True, b_is_solid: bool = True, name: str | None = None)
```

Performs a boolean operation on two meshes (Boolean SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path_a` | `str` | required | SOP path of input A. |
| `path_b` | `str` | required | SOP path of input B. |
| `comment` | `str` | required | What is cut and why. Required. In English. Example: "Cut window openings out of wall body" |
| `operation` | `str` | `'union'` | union / intersect / subtract / shatter / seam. |
| `subtract_order` | `str` | `'aminusb'` | When operation="subtract": aminusb / bminusa / both. |
| `a_is_solid` | `bool` | `True` | Whether to treat A as a solid volume. False treats it as a surface. |
| `b_is_solid` | `bool` | `True` | Whether to treat B as a solid volume. |
| `name` | `str \| None` | `None` | Node name. Example: cut_windows |

### `topology`

Tools that change topology — convert, triangulate, remesh, reduce, transform, delete.

#### convert_geometry

```python
convert_geometry(path: str, comment: str, to_type: str, from_type: str = 'all', group: str = '', name: str | None = None)
```

Changes primitive types (Convert SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is converted and why. Required. In English. |
| `to_type` | `str` | required | poly / polySoup / mesh / nurbCurve / nurbSurf / bezCurve / bezSurf / volume / vdb and so on. A wrong value gets the list of usable values. |
| `from_type` | `str` | `'all'` | Type to convert. all means everything. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: convert_sphere_to_poly |

#### triangulate

```python
triangulate(path: str, comment: str, max_sides: int = 3, avoid_slivers: bool = True, group: str = '', name: str | None = None)
```

Splits polygons into triangles (or up to a given number of sides) (Divide SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is triangulated and why. Required. In English. |
| `max_sides` | `int` | `3` | Maximum sides per polygon. 3 means full triangulation. |
| `avoid_slivers` | `bool` | `True` | Whether to avoid long thin triangles. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: triangulate_for_export |

#### remesh_geometry

```python
remesh_geometry(path: str, comment: str, target_size: float = 0.1, iterations: int = 3, smoothing: float = 0.2, group: str = '', name: str | None = None)
```

Rebuilds the mesh with evenly sized triangles (Remesh SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is remeshed and why. Required. In English. |
| `target_size` | `float` | `0.1` | Target edge length. Smaller is denser and heavier. |
| `iterations` | `int` | `3` | Number of iterations. More is more even but slower. |
| `smoothing` | `float` | `0.2` | Smoothing amount 0–1. High values soften the shape. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: remesh_rock_surface |

#### reduce_polygons

```python
reduce_polygons(path: str, comment: str, target: float, mode: str = 'poly_percent', group: str = '', name: str | None = None)
```

Reduces the polygon count (PolyReduce SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is reduced and why. Required. In English. |
| `target` | `float` | required | A percentage (0–100) for the percent modes, a count for the count modes. |
| `mode` | `str` | `'poly_percent'` | poly_percent / pt_percent / poly_count / pt_count. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: reduce_rock_lod1 |

#### transform_geometry

```python
transform_geometry(path: str, comment: str, translate: Sequence[float] | None = None, rotate: Sequence[float] | None = None, scale: Sequence[float] | None = None, pivot: Sequence[float] | None = None, group: str = '', group_type: str = 'guess', name: str | None = None)
```

Moves, rotates and scales geometry or part of it (Transform SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is moved and why. Required. In English. |
| `translate` | `Sequence[float] \| None` | `None` | Translation (x,y,z). |
| `rotate` | `Sequence[float] \| None` | `None` | Rotation (rx,ry,rz) in degrees. |
| `scale` | `Sequence[float] \| None` | `None` | Scale (sx,sy,sz). |
| `pivot` | `Sequence[float] \| None` | `None` | Pivot for rotation and scale (x,y,z). |
| `group` | `str` | `''` | Target pattern. Everything if empty. |
| `group_type` | `str` | `'guess'` | guess / points / prims / edges / breakpoints. |
| `name` | `str \| None` | `None` | Node name. Example: place_tower_northwest |

#### delete_geometry

```python
delete_geometry(path: str, comment: str, group: str, group_type: str = 'guess', keep_selected: bool = False, delete_unused_points: bool = True, name: str | None = None)
```

Deletes what a group or pattern matches (Blast SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What is deleted and why. Required. In English. |
| `group` | `str` | required | Group name or pattern to delete. Examples: "@name=debris*", "0-5" |
| `group_type` | `str` | `'guess'` | guess / points / prims / edges / breakpoints. |
| `keep_selected` | `bool` | `False` | True keeps only the matches and deletes the rest. |
| `delete_unused_points` | `bool` | `True` | Whether to also delete points left orphaned after deleting primitives. |
| `name` | `str \| None` | `None` | Node name. Example: remove_inner_faces |

### `attribs`

Tools that read and create attributes.

#### attrib_stats

```python
attrib_stats(path: str, name: str, owner: str = 'point', bins: int = 16)
```

Returns statistics about the distribution of a whole attribute.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `name` | `str` | required | Attribute name. Examples: P, N, Cd, pscale |
| `owner` | `str` | `'point'` | point / prim / vertex / detail. |
| `bins` | `int` | `16` | Number of histogram bins. Up to 64. |

#### export_attribute

```python
export_attribute(path: str, name: str, file_path: str, owner: str = 'point')
```

Writes all values of an attribute to a .npy file and returns the path.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `name` | `str` | required | Attribute name. |
| `file_path` | `str` | required | .npy path to save to. The extension is added if missing. Variables such as $HIP are kept as is. |
| `owner` | `str` | `'point'` | point / prim / vertex. |

#### add_normals

```python
add_normals(path: str, comment: str, owner: str = 'point', cusp_angle: float = 60.0, weighting: str = 'angle', group: str = '', name: str | None = None)
```

Creates normals (Normal SOP). Warns before overwriting existing ones.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | Why normals are needed. Required. In English. |
| `owner` | `str` | `'point'` | point / vertex / prim / detail. Where N goes. |
| `cusp_angle` | `float` | `60.0` | Bends sharper than this angle (degrees) stay hard. |
| `weighting` | `str` | `'angle'` | angle (corner angle) / area / uniform. |
| `group` | `str` | `''` | Target pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: smooth_wall_normals |

#### create_attribute

```python
create_attribute(path: str, comment: str, attrib_name: str, owner: str = 'point', attrib_type: str = 'float', value: Sequence[float] | float | str | None = None, group: str = '', name: str | None = None)
```

Creates an attribute filled with a constant value (AttribCreate SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | Why this attribute is needed. Required. In English. |
| `attrib_name` | `str` | required | Name of the attribute to create. Examples: pscale, variant, lod |
| `owner` | `str` | `'point'` | point / prim / vertex / detail. |
| `attrib_type` | `str` | `'float'` | float / int / vector / string. |
| `value` | `Sequence[float] \| float \| str \| None` | `None` | Value to fill. One number for float/int, three values for vector, a string for string. |
| `group` | `str` | `''` | Target pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: set_merlon_scale |

### `groups`

Tools that create and inspect groups.

#### create_group

```python
create_group(path: str, comment: str, group_name: str, group_type: str = 'point', pattern: str = '', bounding_box: Sequence[float] | None = None, normal_direction: Sequence[float] | None = None, normal_angle: float = 180.0, keep_by_normals: bool = False, name: str | None = None)
```

Creates a group and returns **how many elements actually matched** (GroupCreate SOP).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What this group is for. Required. In English. Example: "Top faces of wall, for merlon placement" |
| `group_name` | `str` | required | Name of the group to create, showing its role, in English. Example: wall_top_faces |
| `group_type` | `str` | `'point'` | point / prim / edge / vertex. |
| `pattern` | `str` | `''` | Number range or expression. Can be left empty to use only bounding_box or normal_direction. |
| `bounding_box` | `Sequence[float] \| None` | `None` | Six values (center x, center y, center z, size x, size y, size z). |
| `normal_direction` | `Sequence[float] \| None` | `None` | Reference direction (x,y,z). |
| `normal_angle` | `float` | `180.0` | How many degrees away from normal_direction are accepted. |
| `keep_by_normals` | `bool` | `False` | Whether to use normal_direction. Turned on automatically when normal_direction is given. |
| `name` | `str \| None` | `None` | Node name. Example: group_wall_top |

#### group_members

```python
group_members(path: str, group_name: str, group_type: str = 'point', max_ranges: int = 50)
```

Returns what a group contains. Large groups are folded into ranges.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `group_name` | `str` | required | Group name. |
| `group_type` | `str` | `'point'` | point / prim / edge / vertex. |
| `max_ranges` | `int` | `50` | Maximum number of ranges returned. Up to 100. |

### `uv`

Tools that create UVs and check their quality.

#### uv_report

```python
uv_report(path: str, uv_attrib: str = 'uv')
```

Checks whether UVs are laid out properly.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `uv_attrib` | `str` | `'uv'` | UV attribute name. Default uv. |

#### uv_project

```python
uv_project(path: str, comment: str, projection: str = 'texture', uv_attrib: str = 'uv', fit_to_bounds: bool = True, translate: Sequence[float] | None = None, rotate: Sequence[float] | None = None, scale: Sequence[float] | None = None, group: str = '', name: str | None = None)
```

Creates UVs by projection (UVProject SOP) and returns a check of UV quality afterwards.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What gets UVs and why. Required. In English. |
| `projection` | `str` | `'texture'` | texture (orthographic) / polar / cylin (cylindrical) / torus / wrap. |
| `uv_attrib` | `str` | `'uv'` | Name of the UV attribute to create. |
| `fit_to_bounds` | `bool` | `True` | Whether to fit the projection to the input bounding box so UVs fall in 0–1. Explicit translate/scale win. |
| `translate` | `Sequence[float] \| None` | `None` | Translation of the projection frame (x,y,z). |
| `rotate` | `Sequence[float] \| None` | `None` | Rotation of the projection frame (rx,ry,rz) in degrees. Turns the orthographic direction. |
| `scale` | `Sequence[float] \| None` | `None` | Scale of the projection frame (sx,sy,sz). |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: uv_wall_front |

#### auto_uv

```python
auto_uv(path: str, comment: str, method: str = 'flatten', uv_attrib: str = 'uv', pack_scale: float = 1.0, padding: int = 2, group: str = '', name: str | None = None)
```

Automatically flattens UVs and lays them out in 0–1, returning a check of the result quality.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Input SOP path. |
| `comment` | `str` | required | What gets UVs and why. Required. In English. |
| `method` | `str` | `'flatten'` | flatten (flatten + layout) / unwrap (box projection). |
| `uv_attrib` | `str` | `'uv'` | Name of the UV attribute to create. |
| `pack_scale` | `float` | `1.0` | Overall scale after layout. 1.0 fills 0–1. |
| `padding` | `int` | `2` | Margin between islands in texture pixels. UVLayout takes pixels as is; UVUnwrap takes only a UV fraction, so the value is divided by 1024. |
| `group` | `str` | `''` | Target primitive pattern. Everything if empty. |
| `name` | `str \| None` | `None` | Node name. Example: uv_rock_auto |

### `query`

Tools that ask geometry questions — proximity, rays, intrinsics, volumes, file export.

#### nearest_point

```python
nearest_point(path: str, position: Sequence[float], count: int = 1, max_radius: float | None = None, point_group: str | None = None)
```

Finds the points closest to a given position.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `position` | `Sequence[float]` | required | Reference position (x,y,z). |
| `count` | `int` | `1` | How many to find. Up to 100. |
| `max_radius` | `float \| None` | `None` | Nothing outside this radius is considered. No limit if omitted. |
| `point_group` | `str \| None` | `None` | Search only inside this group. Group name or pattern. |

#### nearest_prim

```python
nearest_prim(path: str, position: Sequence[float])
```

Finds the primitive closest to a given position and the closest point on it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `position` | `Sequence[float]` | required | Reference position (x,y,z). |

#### ray_intersect

```python
ray_intersect(path: str, origin: Sequence[float], direction: Sequence[float], max_distance: float | None = None)
```

Casts a ray at geometry and finds where it hits.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `origin` | `Sequence[float]` | required | Ray origin (x,y,z). |
| `direction` | `Sequence[float]` | required | Ray direction (x,y,z). Need not be normalised. |
| `max_distance` | `float \| None` | `None` | Only up to this distance. No limit if omitted. |

#### prim_intrinsics

```python
prim_intrinsics(path: str, prim_number: int = 0, names: Sequence[str] | None = None)
```

Reads a primitive's intrinsics.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `prim_number` | `int` | `0` | Primitive number to inspect. |
| `names` | `Sequence[str] \| None` | `None` | Intrinsic names to read. All (up to 60) if omitted. |

#### volume_info

```python
volume_info(path: str, prim_number: int | None = None)
```

Returns resolution, voxel size and value range of volume/VDB primitives.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `prim_number` | `int \| None` | `None` | Primitive number to inspect. All volume primitives if omitted. |
