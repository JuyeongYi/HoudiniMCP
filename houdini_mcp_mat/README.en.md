# houdini_mcp_mat

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_mat.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 20 |
| Modules (`TOOL_MODULES`) | `build`, `query`, `assign`, `texture`, `color`, `preset` |

## Overview

```text
Material and look development tool pack.

Holds creating, connecting and assigning shaders and attaching textures. It does not stop at
creating and wiring nodes: results are checked with the specialist libraries bundled with Houdini 22.

    MaterialX 1.39.5   shader graph validation and the preset file format
    OpenImageIO 2.5    actually opens texture files to check resolution, channels, statistics
    pxr (OpenUSD)      queries real bindings through UsdShade
    PyOpenColorIO 2.5  color space lists from the OCIO config

    build      authoring and connecting material and shader nodes
    query      material queries, graph structure, MaterialX validation
    assign     material assignment and checking the real binding (SOP attribute / LOP UsdShade)
    texture    attaching textures and OIIO inspection
    color      OCIO color space queries and assignment
    preset     saving and loading as MaterialX documents

Boundary with `houdini_mcp_lop`: **materials themselves belong here, the stage in general belongs
to lop.** This pack touches USD only through UsdShade (materials and bindings). Prim queries,
layer stacks, composition, lights and variants are handled by the lop pack.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`create_material`](#create_material) | `build` | Creates a material, complete with shader nodes and output wiring. | ✓ |
| [`connect_shader`](#connect_shader) | `build` | Connects a shader node output to another shader's input **by name**. | ✓ |
| [`disconnect_shader`](#disconnect_shader) | `build` | Disconnects one shader input by name. | ✓ |
| [`set_material_parms`](#set_material_parms) | `build` | Sets shader parameters. Colors and vectors are given as lists in one go. | ✓ |
| [`shader_inputs`](#shader_inputs) | `build` | Returns the inputs a shader node accepts and the outputs it provides, with types. |  |
| [`list_materials`](#list_materials) | `query` | Lists the materials in the scene, with comments and family. |  |
| [`material_info`](#material_info) | `query` | Everything about one material — shaders, connections, textures and the nodes that assign it. |  |
| [`shader_graph`](#shader_graph) | `query` | Structure of the shader graph inside a material — nodes and connections. |  |
| [`validate_material`](#validate_material) | `query` | Validates that a material is actually valid, judged by the MaterialX library. |  |
| [`assign_material`](#assign_material) | `assign` | Assigns a material to geometry and returns it **after confirming the assignment took effect**. | ✓ |
| [`list_assignments`](#list_assignments) | `assign` | Shows which material is assigned to what, reading the result rather than parameters. |  |
| [`texture_info`](#texture_info) | `texture` | Actually opens a texture file to read resolution, channels, bit depth and color space. |  |
| [`assign_texture`](#assign_texture) | `texture` | Attaches a texture to a shader input. **Opens the file to check it** first. | ✓ |
| [`reload_textures`](#reload_textures) | `texture` | Clears the texture cache. Use it after changing textures on disk. | ✓ |
| [`list_color_spaces`](#list_color_spaces) | `color` | Reads the usable color spaces from the OCIO config. |  |
| [`texture_parm_colorspaces`](#texture_parm_colorspaces) | `color` | The values a texture node's color space parameter actually accepts. |  |
| [`set_color_space`](#set_color_space) | `color` | Sets a texture node's color space. Values not in the menu are rejected. | ✓ |
| [`save_material`](#save_material) | `preset` | Saves a material as a MaterialX document (.mtlx) and validates it by reading the saved file back. |  |
| [`list_presets`](#list_presets) | `preset` | Lists the MaterialX documents in a directory, including what is inside them. |  |
| [`load_material`](#load_material) | `preset` | Reads a MaterialX document and builds a material from it. The reverse of save_material. | ✓ |

## Details by module

### `build`

Tools that create materials and shader graphs.

#### create_material

```python
create_material(parent: str, name: str, comment: str, kind: str = 'materialx')
```

Creates a material, complete with shader nodes and output wiring.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Network to hold the material. Examples: /mat, /stage/materiallibrary1 |
| `name` | `str` | required | Material name, showing its role. Example: wall_stone |
| `comment` | `str` | required | What this material is for. Required. In English. Example: "Weathered sandstone for the castle wall" |
| `kind` | `str` | `'materialx'` | One of materialx / karma / usdpreview / principled. |

#### connect_shader

```python
connect_shader(source: str, target: str, to_input: str, from_output: str = 'out')
```

Connects a shader node output to another shader's input **by name**.

| Argument | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | required | Node that provides the value. Example: /mat/wall_stone/base_color_tex |
| `target` | `str` | required | Node that receives the value. Example: /mat/wall_stone/mtlxstandard_surface |
| `to_input` | `str` | required | Input name on target. Examples: base_color, specular_roughness |
| `from_output` | `str` | `'out'` | Output name on source. For MaterialX nodes it is usually "out". |

#### disconnect_shader

```python
disconnect_shader(target: str, to_input: str)
```

Disconnects one shader input by name.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path whose input to disconnect. |
| `to_input` | `str` | required | Input name to disconnect. Example: base_color |

#### set_material_parms

```python
set_material_parms(path: str, parms: dict[str, Any])
```

Sets shader parameters. Colors and vectors are given as lists in one go.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Shader node path. Example: /mat/wall_stone/mtlxstandard_surface |
| `parms` | `dict[str, Any]` | required | Names and values. Example: {"base_color": [0.4, 0.25, 0.1], "specular_roughness": 0.55, "metalness": 0.0} |

#### shader_inputs

```python
shader_inputs(path: str)
```

Returns the inputs a shader node accepts and the outputs it provides, with types.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Shader node path. |

### `query`

Tools that inspect and validate materials.

#### list_materials

```python
list_materials(root: str = '/', lop: str = '', max_results: int = 100)
```

Lists the materials in the scene, with comments and family.

| Argument | Type | Default | Description |
|---|---|---|---|
| `root` | `str` | `'/'` | Where to start scanning. The whole scene by default. Examples: /mat, /obj/castle |
| `lop` | `str` | `''` | Given a LOP node path, reads USD materials instead. Example: /stage/assign_wood |
| `max_results` | `int` | `100` | Maximum number returned. |

#### material_info

```python
material_info(path: str)
```

Everything about one material — shaders, connections, textures and the nodes that assign it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Material node path. Example: /mat/wall_stone |

#### shader_graph

```python
shader_graph(path: str, max_nodes: int = 100)
```

Structure of the shader graph inside a material — nodes and connections.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Material node path. |
| `max_nodes` | `int` | `100` | Maximum number of nodes returned. |

#### validate_material

```python
validate_material(path: str)
```

Validates that a material is actually valid, judged by the MaterialX library.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Material node path. Example: /mat/wall_stone |

### `assign`

Tools that assign materials to geometry and confirm the assignment took effect.

#### assign_material

```python
assign_material(target: str, material: str, comment: str, group: str = '', prim_pattern: str = '')
```

Assigns a material to geometry and returns it **after confirming the assignment took effect**.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node to assign the material to. SOP / LOP / OBJ path. |
| `material` | `str` | required | Material path. Given a VOP node path, LOPs convert it to the USD prim path automatically. Examples: /mat/wall_stone, /materials/wall_stone |
| `comment` | `str` | required | Comment for the assignment node that gets created. Required. In English. Example: "Stone material on the wall body" |
| `group` | `str` | `''` | SOPs only. Primitive group or pattern. Empty means everything. |
| `prim_pattern` | `str` | `''` | LOPs only. Prim pattern. Empty means %type:Mesh. |

#### list_assignments

```python
list_assignments(path: str, max_prims: int = 200)
```

Shows which material is assigned to what, reading the result rather than parameters.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP or LOP node path. |
| `max_prims` | `int` | `200` | For LOPs, maximum number of prims to scan. |

### `texture`

Tools that attach textures and **actually open the file to check it** beforehand.

#### texture_info

```python
texture_info(file: str, usage: str = '', stats: bool = False)
```

Actually opens a texture file to read resolution, channels, bit depth and color space.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file` | `str` | required | Texture path. Houdini variables such as $HIP are allowed. Use the <UDIM> token for UDIMs. Example: $HIP/tex/wall_basecolor.<UDIM>.exr |
| `usage` | `str` | `''` | One of color / scalar / normal. Empty skips the judgement. |
| `stats` | `bool` | `False` | True also computes pixel statistics (min, max, mean). Slow for large files. |

#### assign_texture

```python
assign_texture(material: str, to_input: str, file: str, comment: str, usage: str = '', colorspace: str = '', name: str = '')
```

Attaches a texture to a shader input. **Opens the file to check it** first.

| Argument | Type | Default | Description |
|---|---|---|---|
| `material` | `str` | required | Material node path. Example: /mat/wall_stone |
| `to_input` | `str` | required | Input name to attach to. Examples: base_color, specular_roughness, normal |
| `file` | `str` | required | Texture path. Use the <UDIM> token for UDIMs. |
| `comment` | `str` | required | Comment for the texture node that gets created. Required. In English. Example: "Sandstone base color, 4K sRGB" |
| `usage` | `str` | `''` | color / scalar / normal. If given, judges whether the file suits the use. |
| `colorspace` | `str` | `''` | Value for mtlximage's filecolorspace. Empty leaves it untouched. See list_color_spaces for usable values. |
| `name` | `str` | `''` | Name of the texture node to create. Derived from the input name if empty. |

#### reload_textures

```python
reload_textures()
```

Clears the texture cache. Use it after changing textures on disk.

### `color`

Color management tools. Lists are read from the OCIO config, not hardcoded.

#### list_color_spaces

```python
list_color_spaces(pattern: str = '')
```

Reads the usable color spaces from the OCIO config.

| Argument | Type | Default | Description |
|---|---|---|---|
| `pattern` | `str` | `''` | Only names or aliases containing this string. Everything if empty. |

#### texture_parm_colorspaces

```python
texture_parm_colorspaces(path: str = '', parm: str = '')
```

The values a texture node's color space parameter actually accepts.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | `''` | Texture node path. If empty, a temporary mtlximage shows the default menu. |
| `parm` | `str` | `''` | Parameter name. If empty, filecolorspace and the like are found automatically. |

#### set_color_space

```python
set_color_space(path: str, colorspace: str, parm: str = '')
```

Sets a texture node's color space. Values not in the menu are rejected.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Texture node path. Example: /mat/wall_stone/base_color_tex |
| `colorspace` | `str` | required | Value to set. Examples: srgb_texture, lin_rec709, Raw |
| `parm` | `str` | `''` | Parameter name. If empty, filecolorspace and the like are found automatically. |

### `preset`

Tools that save materials to files and read them back. The format is **a MaterialX document**.

#### save_material

```python
save_material(material: str, file: str)
```

Saves a material as a MaterialX document (.mtlx) and validates it by reading the saved file back.

| Argument | Type | Default | Description |
|---|---|---|---|
| `material` | `str` | required | Material node path. Example: /mat/wall_stone |
| `file` | `str` | required | Path to save to. .mtlx is appended if there is no extension. Example: $HIP/materials/wall_stone.mtlx |

#### list_presets

```python
list_presets(directory: str = '$HIP/materials')
```

Lists the MaterialX documents in a directory, including what is inside them.

| Argument | Type | Default | Description |
|---|---|---|---|
| `directory` | `str` | `'$HIP/materials'` | Directory to scan. Example: $HIP/materials |

#### load_material

```python
load_material(file: str, parent: str, name: str, comment: str, nodegraph: str = '')
```

Reads a MaterialX document and builds a material from it. The reverse of save_material.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file` | `str` | required | MaterialX document to read. Example: $HIP/materials/wall_stone.mtlx |
| `parent` | `str` | required | Network to create the material in. Example: /mat |
| `name` | `str` | required | Name of the material to create, showing its role. In English. |
| `comment` | `str` | required | What this material is. Required. In English. |
| `nodegraph` | `str` | `''` | Name to pick when the document has several node graphs. The first one if empty. |
