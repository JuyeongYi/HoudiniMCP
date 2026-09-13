# houdini_mcp_lop

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_lop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 22 |
| Modules (`TOOL_MODULES`) | `stage`, `attrs`, `layers`, `composition`, `lights`, `check` |

## Overview

```text
LOPs / Solaris / USD tool pack.

This pack treats USD **as the composed stage, not as LOP node parameters**. It queries the
`pxr.Usd.Stage` returned by `hou.LopNode.stage()` directly, so it sees the **actual values** after
sublayers, references, payloads, variants and inherits have been layered. Reading node parameters
ignores composition and gives wrong answers.

    stage        stage queries - summary, hierarchy, search, prim details
    attrs        reading and writing USD attributes
    layers       layer stack and tracing where values come from (prim_origin)
    composition  composition arcs - references, payloads, sublayers, variants
    lights       UsdLux lights
    check        stage validation

usdcommon is a shared helper without tools, so it is not in TOOL_MODULES.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`stage_info`](#stage_info) | `stage` | Stage summary - prim count, distribution by type, layer count, up axis, units, time range. |  |
| [`list_prims`](#list_prims) | `stage` | Walks the hierarchy with depth and count limits. |  |
| [`find_prims`](#find_prims) | `stage` | Finds prims with a Houdini prim pattern. |  |
| [`prim_info`](#prim_info) | `stage` | Everything about one prim - type, schemas, visibility, bounds, material binding, variants. |  |
| [`prim_stats`](#prim_stats) | `stage` | Statistics under a prim - counts by type, amount of geometry, kind, payload load state. |  |
| [`list_usd_attributes`](#list_usd_attributes) | `attrs` | Attribute list of a prim - name, type, whether a value is authored, whether it varies over time. |  |
| [`get_usd_attribute`](#get_usd_attribute) | `attrs` | Reads an attribute value as it is after composition. |  |
| [`set_usd_attribute`](#set_usd_attribute) | `attrs` | Sets a value on an attribute by inserting a `pythonscript` LOP. | ✓ |
| [`layer_stack`](#layer_stack) | `layers` | The stage's root layer stack - which layers are stacked in what order. |  |
| [`layer_contents`](#layer_contents) | `layers` | Shows the actual content of a layer as USDA text. |  |
| [`prim_origin`](#prim_origin) | `layers` | **Which arc of which layer** the value of this prim (or attribute) comes from. |  |
| [`composition_arcs`](#composition_arcs) | `composition` | Every composition arc on this prim - what was pulled in from where. |  |
| [`list_variants`](#list_variants) | `composition` | A prim's variant sets, their choices and the current selection. |  |
| [`set_variant`](#set_variant) | `composition` | Selects a variant by inserting a `setvariant` LOP. | ✓ |
| [`add_reference`](#add_reference) | `composition` | Adds a reference, payload, inherit or specialize by inserting a `reference` LOP. | ✓ |
| [`add_sublayer`](#add_sublayer) | `composition` | Lays a USD file in as a sublayer by inserting a `sublayer` LOP. | ✓ |
| [`list_lights`](#list_lights) | `lights` | Every light on the stage - type, intensity, color, position. |  |
| [`light_info`](#light_info) | `lights` | Everything about one light - intensity, color, shape, shaping, shadows, transform. |  |
| [`create_light`](#create_light) | `lights` | Creates a UsdLux light. | ✓ |
| [`create_light_rig`](#create_light_rig) | `lights` | Creates three-point lighting (key / fill / rim) and an environment dome at once. | ✓ |
| [`set_light`](#set_light) | `lights` | Changes properties of an existing light prim by inserting a `pythonscript` LOP. | ✓ |
| [`validate_stage`](#validate_stage) | `check` | Scans a stage for common problems - broken asset paths, empty prims, missing bindings. |  |

## Details by module

### `stage`

Tools that query the composed USD stage.

#### stage_info

```python
stage_info(lop: str = DEFAULT_LOP, frame: float | None = None)
```

Stage summary - prim count, distribution by type, layer count, up axis, units, time range.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node path. Given a LOP network (default /stage), the display node's stage is used. |
| `frame` | `float \| None` | `None` | Look at the stage cooked at this frame. Defaults to the current frame. |

#### list_prims

```python
list_prims(lop: str = DEFAULT_LOP, root: str = '/', depth: int = 2, limit: int = 200, include_inactive: bool = False, frame: float | None = None)
```

Walks the hierarchy with depth and count limits.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `root` | `str` | `'/'` | Prim path to start from. "/" is the whole stage. |
| `depth` | `int` | `2` | How many levels below root to descend. 1 means direct children only. |
| `limit` | `int` | `200` | Maximum number of prims returned. Stages are large, so always set it. |
| `include_inactive` | `bool` | `False` | True also includes inactive prims. |
| `frame` | `float \| None` | `None` | Look at the stage cooked at this frame. |

#### find_prims

```python
find_prims(lop: str = DEFAULT_LOP, pattern: str = '/**', limit: int = 200, traversal: str = 'default')
```

Finds prims with a Houdini prim pattern.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `pattern` | `str` | `'/**'` | Prim pattern. |
| `limit` | `int` | `200` | Maximum number of prims returned. |
| `traversal` | `str` | `'default'` | Traversal condition. One of "default" (active, defined, loaded), "all" (everything), "defined", "active", "loaded". |

#### prim_info

```python
prim_info(lop: str = DEFAULT_LOP, primpath: str = '/', include_attributes: bool = True, frame: float | None = None)
```

Everything about one prim - type, schemas, visibility, bounds, material binding, variants.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path. Example: /world/ball |
| `include_attributes` | `bool` | `True` | True also returns attribute names and whether they have values. Read the values themselves with get_attribute. |
| `frame` | `float \| None` | `None` | Look at the stage cooked at this frame. |

#### prim_stats

```python
prim_stats(lop: str = DEFAULT_LOP, primpath: str = '/', geometry_counts: bool = True, frame: float | None = None)
```

Statistics under a prim - counts by type, amount of geometry, kind, payload load state.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path to compute statistics for. "/" is the whole stage. |
| `geometry_counts` | `bool` | `True` | True also counts points and polygons. Turn it off if it is heavy. |
| `frame` | `float \| None` | `None` | Look at the stage cooked at this frame. |

### `attrs`

Read and write USD attributes.

#### list_usd_attributes

```python
list_usd_attributes(lop: str = DEFAULT_LOP, primpath: str = '/', authored_only: bool = True, frame: float | None = None)
```

Attribute list of a prim - name, type, whether a value is authored, whether it varies over time.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path. |
| `authored_only` | `bool` | `True` | True returns only attributes with authored values. False returns everything the schemas define (dozens). |
| `frame` | `float \| None` | `None` | Look at the stage cooked at this frame. |

#### get_usd_attribute

```python
get_usd_attribute(lop: str = DEFAULT_LOP, primpath: str = '/', name: str = '', frame: float | None = None, max_array: int = 16)
```

Reads an attribute value as it is after composition.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path. |
| `name` | `str` | `''` | Attribute name. Examples: radius, points, inputs:intensity |
| `frame` | `float \| None` | `None` | Read the value at this time. The default value if omitted. |
| `max_array` | `int` | `16` | Maximum number of elements returned for array values. |

#### set_usd_attribute

```python
set_usd_attribute(lop: str, primpath: str, name: str, value: UsdValue, comment: str, type_name: str | None = None, frame: float | None = None, node_name: str | None = None)
```

Sets a value on an attribute by inserting a `pythonscript` LOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path that feeds the edit. Given a network, its display node. |
| `primpath` | `str` | required | Prim path to set the value on. |
| `name` | `str` | required | Attribute name. Examples: radius, inputs:intensity, visibility |
| `value` | `UsdValue` | required | Value to set. Vectors and arrays as lists. Examples: 2.5, [1,0,0], [[0,0,0],[1,1,1]] |
| `comment` | `str` | required | Why this edit is needed. Kept as the node comment. Write it in English. |
| `type_name` | `str \| None` | `None` | USD type when creating a new attribute. Examples: double, float3, token, float3[], asset |
| `frame` | `float \| None` | `None` | Set the value as a time sample at this time. The default value if omitted. |
| `node_name` | `str \| None` | `None` | Name of the node to create. Derived from the attribute name if omitted. |

### `layers`

The layer stack and **where values come from**.

#### layer_stack

```python
layer_stack(lop: str = DEFAULT_LOP, include_session: bool = False)
```

The stage's root layer stack - which layers are stacked in what order.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `include_session` | `bool` | `False` | True also returns the session layer (viewport overrides, solo, visibility toggles and so on). Usually not needed. |

#### layer_contents

```python
layer_contents(lop: str = DEFAULT_LOP, identifier: str = '', primpath: str | None = None, max_chars: int = MAX_LAYER_CHARS)
```

Shows the actual content of a layer as USDA text.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `identifier` | `str` | `''` | Layer identifier, exactly as returned by layer_stack or prim_origin. Empty means that LOP node's active layer. |
| `primpath` | `str \| None` | `None` | Show only this prim spec. The whole layer if omitted. |
| `max_chars` | `int` | `MAX_LAYER_CHARS` | Maximum length of the returned text. |

#### prim_origin

```python
prim_origin(lop: str = DEFAULT_LOP, primpath: str = '/', attribute: str | None = None, frame: float | None = None)
```

**Which arc of which layer** the value of this prim (or attribute) comes from.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path. |
| `attribute` | `str \| None` | `None` | Given an attribute name, shows that attribute's opinion stack. Otherwise the prim's own spec stack. |
| `frame` | `float \| None` | `None` | Evaluate attribute opinions at this time. |

### `composition`

Composition arcs - references, payloads, sublayers, variants, inherits.

#### composition_arcs

```python
composition_arcs(lop: str = DEFAULT_LOP, primpath: str = '/', arc_types: list[str] | None = None, include_ancestral: bool = True)
```

Every composition arc on this prim - what was pulled in from where.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path. |
| `arc_types` | `list[str] \| None` | `None` | Only these kinds. Example: ["reference", "payload", "variant"]. All if omitted. |
| `include_ancestral` | `bool` | `True` | False leaves out arcs inherited from ancestors, to see only those authored directly on this prim. |

#### list_variants

```python
list_variants(lop: str = DEFAULT_LOP, primpath: str = '/')
```

A prim's variant sets, their choices and the current selection.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `'/'` | Prim path. |

#### set_variant

```python
set_variant(lop: str, primpath: str, variant_set: str, variant: str, comment: str, node_name: str | None = None)
```

Selects a variant by inserting a `setvariant` LOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path used as input. |
| `primpath` | `str` | required | Path of the prim that has the variant set. |
| `variant_set` | `str` | required | Variant set name. |
| `variant` | `str` | required | Variant name to select. |
| `comment` | `str` | required | Why this variant. Kept as the node comment. Write it in English. |
| `node_name` | `str \| None` | `None` | Name of the node to create. Derived from the variant name if omitted. |

#### add_reference

```python
add_reference(lop: str, primpath: str, comment: str, file_path: str | None = None, reference_type: str = 'file', source_prim: str | None = None, create_prims: bool = True, node_name: str | None = None)
```

Adds a reference, payload, inherit or specialize by inserting a `reference` LOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path used as input. |
| `primpath` | `str` | required | Prim path to add the arc on. Example: /world/props/chair |
| `comment` | `str` | required | What this arc is. Kept as the node comment. Write it in English. |
| `file_path` | `str \| None` | `None` | USD file path to pull in. Only for file / payload. |
| `reference_type` | `str` | `'file'` | "file" (reference), "payload" (deferred load), "prim" (prim in the same stage), "inherit", "specialize". |
| `source_prim` | `str \| None` | `None` | For file / payload, the prim path inside the file to pull in (defaultPrim if omitted). For prim / inherit / specialize, the source prim path in the same stage, which is required. |
| `create_prims` | `bool` | `True` | Create the target prim if it does not exist. |
| `node_name` | `str \| None` | `None` | Name of the node to create. Derived from the target prim name if omitted. |

#### add_sublayer

```python
add_sublayer(lop: str, file_path: str, comment: str, node_name: str | None = None)
```

Lays a USD file in as a sublayer by inserting a `sublayer` LOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path used as input. |
| `file_path` | `str` | required | USD file path to lay in. |
| `comment` | `str` | required | What this layer is. Kept as the node comment. Write it in English. |
| `node_name` | `str \| None` | `None` | Name of the node to create. Derived from the file name if omitted. |

### `lights`

UsdLux lights.

#### list_lights

```python
list_lights(lop: str = DEFAULT_LOP, limit: int = 200)
```

Every light on the stage - type, intensity, color, position.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `limit` | `int` | `200` | Maximum number of lights returned. |

#### light_info

```python
light_info(lop: str = DEFAULT_LOP, primpath: str = '')
```

Everything about one light - intensity, color, shape, shaping, shadows, transform.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `primpath` | `str` | `''` | Light prim path. Find it with list_lights. |

#### create_light

```python
create_light(lop: str, light_type: str, primpath: str, comment: str, intensity: float | None = None, exposure: float | None = None, color: list[float] | None = None, translate: list[float] | None = None, rotate: list[float] | None = None, texture: str | None = None, node_name: str | None = None)
```

Creates a UsdLux light.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path used as input. Given a network, the light goes after the display node. |
| `light_type` | `str` | required | One of distant, sphere, point, disk, rect, cylinder, dome. |
| `primpath` | `str` | required | Light prim path to create. Example: /world/lights/key |
| `comment` | `str` | required | What this light does. Kept as the node comment. Write it in English. |
| `intensity` | `float \| None` | `None` | Intensity. |
| `exposure` | `float \| None` | `None` | Exposure (stops). Intensity is multiplied by 2^exposure. |
| `color` | `list[float] \| None` | `None` | RGB. Example: [1.0, 0.95, 0.9] |
| `translate` | `list[float] \| None` | `None` | Position [x, y, z]. |
| `rotate` | `list[float] \| None` | `None` | Rotation [rx, ry, rz] (degrees). |
| `texture` | `str \| None` | `None` | Texture (HDRI) file path for dome/rect lights. |
| `node_name` | `str \| None` | `None` | Name of the node to create. Derived from the prim name if omitted. |

#### create_light_rig

```python
create_light_rig(lop: str, comment: str, root: str = '/lights', key_intensity: float = 3.0, fill_intensity: float = 1.0, rim_intensity: float = 2.0, dome_texture: str | None = None, dome_intensity: float = 0.3)
```

Creates three-point lighting (key / fill / rim) and an environment dome at once.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path used as input. |
| `comment` | `str` | required | What this rig lights. Kept as the node comment. Write it in English. |
| `root` | `str` | `'/lights'` | Prim path to hold the lights. Example: /world/lights |
| `key_intensity` | `float` | `3.0` | Key light intensity. |
| `fill_intensity` | `float` | `1.0` | Fill light intensity. |
| `rim_intensity` | `float` | `2.0` | Rim light intensity. |
| `dome_texture` | `str \| None` | `None` | HDRI file path for the environment dome. A uniform color if missing. |
| `dome_intensity` | `float` | `0.3` | Environment dome intensity. |

#### set_light

```python
set_light(lop: str, primpath: str, comment: str, properties: dict[str, Any] | None = None, node_name: str | None = None)
```

Changes properties of an existing light prim by inserting a `pythonscript` LOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | required | LOP node path used as input. |
| `primpath` | `str` | required | Light prim path to change. |
| `comment` | `str` | required | Why it is changed this way. Kept as the node comment. Write it in English. |
| `properties` | `dict[str, Any] \| None` | `None` | Property names and values. Example: {"intensity": 5.0, "color": [1, 0.9, 0.8]} |
| `node_name` | `str \| None` | `None` | Name of the node to create. Derived from the prim name if omitted. |

### `check`

Stage validation - finds what is missing before a render.

#### validate_stage

```python
validate_stage(lop: str = DEFAULT_LOP, check_materials: bool = True, check_render: bool = True)
```

Scans a stage for common problems - broken asset paths, empty prims, missing bindings.

| Argument | Type | Default | Description |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP node or LOP network path. |
| `check_materials` | `bool` | `True` | Finds geometry without material bindings. Creating and fixing materials themselves is the job of houdini_mcp_mat. |
| `check_render` | `bool` | `True` | Checks that render settings and a camera exist. Actually rendering is the job of houdini_mcp_render. |
