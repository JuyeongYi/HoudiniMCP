# houdini_mcp_base

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_base.json` |
| requires | `houdini_mcp` |
| Tools | 102 |
| Modules (`TOOL_MODULES`) | `info`, `edit`, `parms`, `parmedit`, `transform`, `context`, `explain`, `analyze`, `geometry`, `cache`, `viewport`, `visualize`, `nodetypes`, `scene`, `deps`, `portability`, `takes`, `diagnose`, `anim`, `execute` |

## Overview

```text
The tool pack every task builds on.

Holds what is used regardless of context or task. Split into modules only.

    info       scene, node and graph queries
    edit       node creation, manipulation and wiring for any network type
    parms      parameter queries
    parmedit   changes parameters themselves - add spares, link, lock, revert
    transform  node transforms and the OBJ hierarchy - world/parm/local/pre shown separately
    context    node trees and dependencies - indirect references as well as direct connections
    explain    a combined explanation of one node - one call instead of five
    analyze    scans a whole network - summary, cook order, expensive nodes, snapshot comparison
    geometry   geometry statistics and attributes - needed in DOPs and elsewhere, not just SOPs
    cache      disk caches - write them, check they are current, delete them
    viewport   viewport capture and framing - see the result with your own eyes
    visualize  attribute visualizers - see how values are distributed as colors
    nodetypes  node type catalogue - see what can be created first
    scene      saving and opening scene files, frame range
    deps       the scene's file references - listing, collecting, path remapping. Obtained from hou.fileReferences()
    portability  decides whether a scene can move to another machine - missing files, baked-in paths
    takes      takes - keep parameter variations apart and switch between them
    diagnose   error/warning queries and cooking - find out what went wrong
    anim       parameter expressions and keyframes
    execute    escape hatch for what the tools cannot do. A last resort

Modules without tools are not in TOOL_MODULES.

    parmtemplate  shared helper that builds hou.ParmTemplate. Used by both parmedit and
                  houdini_mcp_hda
    paths         path expansion, keeping raw strings, sequences, $HFS. Every pack that handles
                  paths uses this and keeps no helper of its own

Tools that only make sense in a specific context are split into dedicated packs (houdini_mcp_sop and so on).

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`houdini_version`](#houdini_version) | `info` | Version string of the running Houdini. |  |
| [`scene_info`](#scene_info) | `info` | Path, saved state, FPS and frame range of the current scene. |  |
| [`list_children`](#list_children) | `info` | Lists the child nodes under a network. |  |
| [`node_info`](#node_info) | `info` | Type, parent, child count, flags and connections of one node. |  |
| [`node_flags`](#node_flags) | `info` | display/render/bypass/lock flags of a node. |  |
| [`find_nodes`](#find_nodes) | `info` | Finds nodes by pattern. |  |
| [`network_graph`](#network_graph) | `info` | Scans the nodes and connections of a network in one pass. |  |
| [`get_parms`](#get_parms) | `info` | Reads node parameter values together with the node's comment. |  |
| [`create_node`](#create_node) | `edit` | Creates a node inside a network. Parameters can be set at the same time. | ✓ |
| [`set_comment`](#set_comment) | `edit` | Changes a node's comment. | ✓ |
| [`delete_node`](#delete_node) | `edit` | Deletes a node. | ✓ |
| [`rename_node`](#rename_node) | `edit` | Renames a node. | ✓ |
| [`set_parms`](#set_parms) | `edit` | Sets node parameters. | ✓ |
| [`connect_nodes`](#connect_nodes) | `edit` | Connects an output of source to an input of target. | ✓ |
| [`disconnect_input`](#disconnect_input) | `edit` | Disconnects one input of a node. | ✓ |
| [`set_flags`](#set_flags) | `edit` | Sets node flags. Only the given ones change. | ✓ |
| [`layout_children`](#layout_children) | `edit` | Arranges the nodes inside a network neatly. | ✓ |
| [`copy_node`](#copy_node) | `edit` | Duplicates a node, including parameters and the network inside it. | ✓ |
| [`reorder_inputs`](#reorder_inputs) | `edit` | Changes the order of a node's inputs. | ✓ |
| [`set_node_appearance`](#set_node_appearance) | `edit` | Sets a node's color, position and shape in the network view. | ✓ |
| [`get_selection`](#get_selection) | `edit` | The nodes the user currently has selected in the network view. |  |
| [`select_by_pattern`](#select_by_pattern) | `edit` | Selects nodes in bulk by pattern or type. | ✓ |
| [`set_selection`](#set_selection) | `edit` | Changes the selection in the network view. | ✓ |
| [`list_parms`](#list_parms) | `parms` | Lists a node's parameters with name, label, type and current value. Also returns the node comment. |  |
| [`parm_info`](#parm_info) | `parms` | Looks at one parameter in detail: default, range, menu items, help. |  |
| [`add_spare_parm`](#add_spare_parm) | `parmedit` | Adds a spare parameter to a node. | ✓ |
| [`remove_spare_parm`](#remove_spare_parm) | `parmedit` | Removes a spare parameter. | ✓ |
| [`link_parms`](#link_parms) | `parmedit` | Sets an expression so the target parameter follows the source parameter. | ✓ |
| [`lock_parm`](#lock_parm) | `parmedit` | Locks or unlocks parameters. | ✓ |
| [`revert_parm`](#revert_parm) | `parmedit` | Reverts parameters to their defaults, returning the values before reverting. | ✓ |
| [`spare_parms`](#spare_parms) | `parmedit` | Lists the spare parameters on a node. |  |
| [`get_transform`](#get_transform) | `transform` | Shows a node's transform in all four spaces. |  |
| [`set_transform`](#set_transform) | `transform` | Sets a node's transform. Only the given parts change. | ✓ |
| [`set_pivot`](#set_pivot) | `transform` | Sets the center point for rotation and scale. | ✓ |
| [`parent_node`](#parent_node) | `transform` | Parents an OBJ node to another OBJ node. The child follows when the parent moves. | ✓ |
| [`unparent_node`](#unparent_node) | `transform` | Removes the parent in the OBJ hierarchy. | ✓ |
| [`set_node_lock`](#set_node_lock) | `transform` | Freezes a node's cook result. Hard locks and soft locks differ. | ✓ |
| [`node_references`](#node_references) | `context` | Shows in one call what this node depends on. |  |
| [`scene_context`](#scene_context) | `context` | Scans a network including nodes and dependencies in one pass and builds context from it. |  |
| [`find_referencing_nodes`](#find_referencing_nodes) | `context` | Finds who references this node. |  |
| [`explain_node`](#explain_node) | `explain` | Explains one node comprehensively. Call this first to understand a node. |  |
| [`network_overview`](#network_overview) | `analyze` | Shows at a glance what a network looks like. Call it when first looking at a scene. |  |
| [`cook_chain`](#cook_chain) | `analyze` | Shows what gets cooked, in what order, to produce this node. |  |
| [`find_expensive_nodes`](#find_expensive_nodes) | `analyze` | Finds which nodes eat up time, **from measured values**. |  |
| [`scene_snapshot`](#scene_snapshot) | `analyze` | Captures the current state. Later, `diff_scene` shows what changed. |  |
| [`diff_scene`](#diff_scene) | `analyze` | Compares a snapshot with now (or another snapshot) to show what changed. |  |
| [`geometry_stats`](#geometry_stats) | `geometry` | Point, primitive and vertex counts and bounding box of a SOP. |  |
| [`list_attributes`](#list_attributes) | `geometry` | Lists the attributes of geometry by class. |  |
| [`list_groups`](#list_groups) | `geometry` | Lists the groups of geometry by class. |  |
| [`sample_points`](#sample_points) | `geometry` | Samples a few point positions. |  |
| [`attribute_values`](#attribute_values) | `geometry` | Reads a few attribute values. |  |
| [`write_cache`](#write_cache) | `cache` | Bakes geometry to a disk cache and confirms the files were created. | ✓ |
| [`list_caches`](#list_caches) | `cache` | Finds every cache node in the scene. |  |
| [`cache_status`](#cache_status) | `cache` | Shows whether a cache exists and whether it is stale. |  |
| [`clear_cache`](#clear_cache) | `cache` | Clears caches. Memory and disk are handled separately. |  |
| [`viewport_snapshot`](#viewport_snapshot) | `viewport` | Captures the current viewport and returns it as a picture. |  |
| [`viewport_sequence`](#viewport_sequence) | `viewport` | Captures several frames onto one sheet, to see what happens over time. |  |
| [`frame_all`](#frame_all) | `viewport` | Fits the viewport so the whole scene is visible. |  |
| [`frame_node`](#frame_node) | `viewport` | Fits the viewport to a specific node's geometry. |  |
| [`viewport_info`](#viewport_info) | `viewport` | Name, size and camera state of the current viewport. |  |
| [`set_viewport_camera`](#set_viewport_camera) | `viewport` | Looks through a camera in the viewport, to check what a render actually captures. |  |
| [`set_viewport_direction`](#set_viewport_direction) | `viewport` | Makes the viewport look from a fixed direction. |  |
| [`set_viewport_display`](#set_viewport_display) | `viewport` | Sets how the viewport draws geometry. |  |
| [`set_viewport_renderer`](#set_viewport_renderer) | `viewport` | Changes the viewport renderer. Without a name, lists the available ones. |  |
| [`list_panes`](#list_panes) | `viewport` | The pane tabs currently open. Shows what the user is looking at. |  |
| [`set_current_network`](#set_current_network) | `viewport` | Changes the network the network editor shows. |  |
| [`visualize_attribute`](#visualize_attribute) | `visualize` | Displays an attribute as colors in the viewport. | ✓ |
| [`list_visualizers`](#list_visualizers) | `visualize` | Lists attached visualizers. |  |
| [`set_visualizer_active`](#set_visualizer_active) | `visualize` | Turns a visualizer on or off. | ✓ |
| [`remove_visualizer`](#remove_visualizer) | `visualize` | Deletes a visualizer. | ✓ |
| [`list_node_types`](#list_node_types) | `nodetypes` | Finds the node types available in a category. |  |
| [`node_type_info`](#node_type_info) | `nodetypes` | Shows a type's parameters, inputs and outputs before creating the node. |  |
| [`node_type_help`](#node_type_help) | `nodetypes` | Built-in help text of a node type. |  |
| [`scene_path`](#scene_path) | `scene` | Current scene file path and saved state. |  |
| [`save_scene`](#save_scene) | `scene` | Saves the scene. |  |
| [`load_scene`](#load_scene) | `scene` | Opens a scene file. |  |
| [`new_scene`](#new_scene) | `scene` | Clears the scene and starts fresh. |  |
| [`set_frame_range`](#set_frame_range) | `scene` | Sets the playbar frame range. |  |
| [`list_dependencies`](#list_dependencies) | `deps` | Lists every external file the scene references and checks whether it actually exists. |  |
| [`collect_dependencies`](#collect_dependencies) | `deps` | Gathers the files the scene uses into one directory. Optionally makes the scene point there. | ✓ |
| [`remap_paths`](#remap_paths) | `deps` | Replaces part of file reference paths. Used when moving a scene to another machine. | ✓ |
| [`validate_scene`](#validate_scene) | `portability` | Decides whether a scene can move to another machine. Catches missing files and baked-in paths. |  |
| [`list_takes`](#list_takes) | `takes` | Lists every take in the scene and which one is currently active. |  |
| [`create_take`](#create_take) | `takes` | Creates a take. | ✓ |
| [`set_current_take`](#set_current_take) | `takes` | Changes the active take. | ✓ |
| [`delete_take`](#delete_take) | `takes` | Deletes a take. Parameter values that existed only in that take are lost. | ✓ |
| [`take_include`](#take_include) | `takes` | Decides which parameters vary separately in this take. | ✓ |
| [`take_includes`](#take_includes) | `takes` | Shows which parameters this take includes. |  |
| [`node_errors`](#node_errors) | `diagnose` | Reads the errors and warnings of one node. |  |
| [`find_error_nodes`](#find_error_nodes) | `diagnose` | Finds nodes with errors or warnings in a scope. |  |
| [`cook_node`](#cook_node) | `diagnose` | Cooks a node to confirm it actually computes. |  |
| [`cook_status`](#cook_status) | `diagnose` | Whether a node has cooked, how long it took, and whether it is time dependent. |  |
| [`delete_unused`](#delete_unused) | `diagnose` | Deletes nodes that do not lead to an output. | ✓ |
| [`get_expression`](#get_expression) | `anim` | Reads the expression on a parameter. |  |
| [`set_expression`](#set_expression) | `anim` | Sets an expression on a parameter. | ✓ |
| [`clear_expression`](#clear_expression) | `anim` | Removes a parameter's expression and returns it to a plain value. | ✓ |
| [`set_keyframe`](#set_keyframe) | `anim` | Sets a keyframe on a parameter. | ✓ |
| [`get_keyframes`](#get_keyframes) | `anim` | Keyframe list of a parameter. |  |
| [`delete_keyframes`](#delete_keyframes) | `anim` | Deletes keyframes. Only that span if a range is given. | ✓ |
| [`list_animated_parms`](#list_animated_parms) | `anim` | Finds parameters on a node that have keyframes or expressions. |  |
| [`run_python`](#run_python) | `execute` | Runs Python inside Houdini. Use only when no dedicated tool can do it. | ✓ |
| [`run_hscript`](#run_hscript) | `execute` | Runs HScript commands. |  |

## Details by module

### `info`

Tools that read information about the scene and the node graph.

#### houdini_version

```python
houdini_version()
```

Version string of the running Houdini.

#### scene_info

```python
scene_info()
```

Path, saved state, FPS and frame range of the current scene.

#### list_children

```python
list_children(path: str = '/obj')
```

Lists the child nodes under a network.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | `'/obj'` | Parent node path. Default /obj. |

#### node_info

```python
node_info(path: str, include_parameters: bool = False)
```

Type, parent, child count, flags and connections of one node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. Example: /obj/geo1 |
| `include_parameters` | `bool` | `False` | True also returns the list of parameter names. Some nodes have hundreds, so the default is False. |

#### node_flags

```python
node_flags(path: str)
```

display/render/bypass/lock flags of a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |

#### find_nodes

```python
find_nodes(pattern: str, root: str = '/obj')
```

Finds nodes by pattern.

| Argument | Type | Default | Description |
|---|---|---|---|
| `pattern` | `str` | required | Examples: "*geo*", "**/*box*" |
| `root` | `str` | `'/obj'` | Network path to start searching from. |

#### network_graph

```python
network_graph(path: str = '/obj', depth: int = 1)
```

Scans the nodes and connections of a network in one pass.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | `'/obj'` | Network path. |
| `depth` | `int` | `1` | How many levels of sub-networks to follow. 1 means only directly below. |

#### get_parms

```python
get_parms(path: str, names: list[str] | None = None)
```

Reads node parameter values together with the node's comment.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `names` | `list[str] \| None` | `None` | Parameter names to read. If omitted, only those that differ from their defaults are returned (nodes have hundreds of parameters, so all of them would be useless). |

### `edit`

Node creation, manipulation and wiring tools used regardless of network type.

#### create_node

```python
create_node(parent: str, node_type: str, comment: str, name: str | None = None, parms: dict[str, ParmValue] | None = None)
```

Creates a node inside a network. Parameters can be set at the same time.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Parent network path. Examples: /obj, /obj/geo1 |
| `node_type` | `str` | required | Node type name. Examples: geo, box, merge, copytopoints |
| `comment` | `str` | required | What this node is for. Required. Stored in the scene file and read by other tools, so write it in English. Example: "Wall body, 20 x 4 x 1.2" |
| `name` | `str \| None` | `None` | Node name, showing its role. Houdini picks one if omitted. |
| `parms` | `dict[str, ParmValue] \| None` | `None` | Parameters to set right after creation. Example: {"sizex": 2.0, "ty": 1.5} |

#### set_comment

```python
set_comment(path: str, comment: str)
```

Changes a node's comment.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `comment` | `str` | required | New comment. Stored in the scene, so write it in English. |

#### delete_node

```python
delete_node(path: str)
```

Deletes a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the node to delete. |

#### rename_node

```python
rename_node(path: str, name: str)
```

Renames a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | New name, showing its role, in English. |

#### set_parms

```python
set_parms(path: str, parms: dict[str, ParmValue])
```

Sets node parameters.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `parms` | `dict[str, ParmValue]` | required | Names and values. Example: {"sizex": 2.0, "ty": 1.5, "group": "0-3"} |

#### connect_nodes

```python
connect_nodes(source: str, target: str, input_index: int = 0, output_index: int = 0)
```

Connects an output of source to an input of target.

| Argument | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | required | Path of the node on the output side. |
| `target` | `str` | required | Path of the node on the input side. |
| `input_index` | `int` | `0` | Which input of target to connect to. |
| `output_index` | `int` | `0` | Which output of source to take from. |

#### disconnect_input

```python
disconnect_input(path: str, input_index: int = 0)
```

Disconnects one input of a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `input_index` | `int` | `0` | Input index to disconnect. |

#### set_flags

```python
set_flags(path: str, display: bool | None = None, render: bool | None = None, bypass: bool | None = None)
```

Sets node flags. Only the given ones change.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `display` | `bool \| None` | `None` | Viewport display flag. |
| `render` | `bool \| None` | `None` | Render flag. |
| `bypass` | `bool \| None` | `None` | Bypass flag. |

#### layout_children

```python
layout_children(path: str)
```

Arranges the nodes inside a network neatly.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Network path. |

#### copy_node

```python
copy_node(path: str, parent: str | None = None, name: str | None = None)
```

Duplicates a node, including parameters and the network inside it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the node to copy. |
| `parent` | `str \| None` | `None` | Network to paste into. Same parent as the original if omitted. |
| `name` | `str \| None` | `None` | New name. Houdini picks one if omitted. |

#### reorder_inputs

```python
reorder_inputs(path: str, order: list[int])
```

Changes the order of a node's inputs.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `order` | `list[int]` | required | New order: the current input indices in the desired order. |

#### set_node_appearance

```python
set_node_appearance(path: str, color: list[float] | None = None, position: list[float] | None = None, shape: str | None = None)
```

Sets a node's color, position and shape in the network view.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `color` | `list[float] \| None` | `None` | Three RGB values 0–1. Example: [0.9, 0.3, 0.3] |
| `position` | `list[float] \| None` | `None` | Two network view coordinates. Example: [3.0, -2.0] |
| `shape` | `str \| None` | `None` | Node shape name. Examples: circle, oval, box |

#### get_selection

```python
get_selection()
```

The nodes the user currently has selected in the network view.

#### select_by_pattern

```python
select_by_pattern(pattern: str = '*', root: str = '/obj', node_type: str | None = None, clear_existing: bool = True)
```

Selects nodes in bulk by pattern or type.

| Argument | Type | Default | Description |
|---|---|---|---|
| `pattern` | `str` | `'*'` | Node name pattern. `*` matches one level, `**` recurses. Examples: "*wall*", "**/*merlon*" |
| `root` | `str` | `'/obj'` | Network path to start searching from. |
| `node_type` | `str \| None` | `None` | Further filter by type. Examples: box, copytopoints |
| `clear_existing` | `bool` | `True` | Clear the existing selection and select anew. |

#### set_selection

```python
set_selection(paths: list[str], clear_existing: bool = True)
```

Changes the selection in the network view.

| Argument | Type | Default | Description |
|---|---|---|---|
| `paths` | `list[str]` | required | Node paths to select. |
| `clear_existing` | `bool` | `True` | Clear the existing selection and select anew. |

### `parms`

Tools that inspect parameters.

#### list_parms

```python
list_parms(path: str, pattern: str = '*', changed_only: bool = False)
```

Lists a node's parameters with name, label, type and current value. Also returns the node comment.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `pattern` | `str` | `'*'` | Name pattern. Examples: "size*", "t?", "*color*" |
| `changed_only` | `bool` | `False` | True returns only those that differ from their defaults. |

#### parm_info

```python
parm_info(path: str, name: str)
```

Looks at one parameter in detail: default, range, menu items, help.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. Examples: sizex, type |

### `parmedit`

Tools that change parameters. They handle the parameters themselves, not values.

#### add_spare_parm

```python
add_spare_parm(path: str, kind: str, name: str, label: str, size: int = 1, default: Any = None, min_value: float | None = None, max_value: float | None = None, menu_items: list[str] | None = None, menu_labels: list[str] | None = None, string_type: str = 'regular', help_text: str | None = None, folder: list[str] | None = None)
```

Adds a spare parameter to a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `kind` | `str` | required | float / int / string / toggle / menu / button / ramp_float / ramp_color / separator. |
| `name` | `str` | required | Internal name. Example: wall_height |
| `label` | `str` | required | Name shown in the UI, in English. Example: "Wall Height" |
| `size` | `int` | `1` | Number of components. Only meaningful for float/int/string. |
| `default` | `Any` | `None` | Default value. For vectors, give a list or one value to fill every component. |
| `min_value` | `float \| None` | `None` | Slider minimum. |
| `max_value` | `float \| None` | `None` | Slider maximum. |
| `menu_items` | `list[str] \| None` | `None` | Values to choose from for the menu kind. |
| `menu_labels` | `list[str] \| None` | `None` | Display names of those values. |
| `string_type` | `str` | `'regular'` | For the string kind: regular / file / node / node_list. |
| `help_text` | `str \| None` | `None` | Parameter tooltip, in English. |
| `folder` | `list[str] \| None` | `None` | Folder path to put it in. Example: ["Controls"]. Created if missing. |

#### remove_spare_parm

```python
remove_spare_parm(path: str, name: str)
```

Removes a spare parameter.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Name of the parameter to remove. Give the tuple name for vectors. |

#### link_parms

```python
link_parms(source: str, source_parm: str, target: str, target_parm: str, relative: bool = True)
```

Sets an expression so the target parameter follows the source parameter.

| Argument | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | required | Path of the node providing the value. |
| `source_parm` | `str` | required | Parameter name on that node. |
| `target` | `str` | required | Path of the node receiving the value. |
| `target_parm` | `str` | required | Parameter name on that node. |
| `relative` | `bool` | `True` | True uses a relative path. |

#### lock_parm

```python
lock_parm(path: str, names: list[str], locked: bool = True)
```

Locks or unlocks parameters.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `names` | `list[str]` | required | Parameter names. Use component names for vectors. Example: ["tx", "ty"] |
| `locked` | `bool` | `True` | True locks, False unlocks. |

#### revert_parm

```python
revert_parm(path: str, names: list[str] | None = None)
```

Reverts parameters to their defaults, returning the values before reverting.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `names` | `list[str] \| None` | `None` | Parameter names to revert. All non-default parameters if omitted. |

#### spare_parms

```python
spare_parms(path: str)
```

Lists the spare parameters on a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |

### `transform`

Tools for node transforms and hierarchy.

#### get_transform

```python
get_transform(path: str)
```

Shows a node's transform in all four spaces.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | OBJ node path. Example: /obj/castle |

#### set_transform

```python
set_transform(path: str, translate: list[float] | None = None, rotate: list[float] | None = None, scale: list[float] | None = None, space: str = 'parm')
```

Sets a node's transform. Only the given parts change.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | OBJ node path. |
| `translate` | `list[float] \| None` | `None` | Three position values. Example: [0, 2, 0] |
| `rotate` | `list[float] \| None` | `None` | Three rotation values (degrees). Example: [0, 45, 0] |
| `scale` | `list[float] \| None` | `None` | Three scale values. Example: [1, 2, 1] |
| `space` | `str` | `'parm'` | parm or world. |

#### set_pivot

```python
set_pivot(path: str, pivot: list[float] | None = None, pivot_rotate: list[float] | None = None)
```

Sets the center point for rotation and scale.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | OBJ node path. |
| `pivot` | `list[float] \| None` | `None` | Three pivot values. Example: [0, 0, -1] |
| `pivot_rotate` | `list[float] \| None` | `None` | Three values for the pivot's reference rotation (degrees). |

#### parent_node

```python
parent_node(path: str, parent: str, keep_position: bool = True)
```

Parents an OBJ node to another OBJ node. The child follows when the parent moves.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the node that becomes the child. |
| `parent` | `str` | required | Path of the node that becomes the parent. |
| `keep_position` | `bool` | `True` | Keep the visible position after parenting. |

#### unparent_node

```python
unparent_node(path: str, keep_position: bool = True)
```

Removes the parent in the OBJ hierarchy.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the node to detach. |
| `keep_position` | `bool` | `True` | Keep the visible position after detaching. |

#### set_node_lock

```python
set_node_lock(path: str, hard: bool | None = None, soft: bool | None = None)
```

Freezes a node's cook result. Hard locks and soft locks differ.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. Locks are mostly supported by SOPs. |
| `hard` | `bool \| None` | `None` | Set or clear the hard lock. |
| `soft` | `bool \| None` | `None` | Set or clear the soft lock. |

### `context`

Tools that read node trees and dependencies in one pass and build context from them.

#### node_references

```python
node_references(path: str)
```

Shows in one call what this node depends on.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |

#### scene_context

```python
scene_context(path: str = '/obj', depth: int = 2)
```

Scans a network including nodes and dependencies in one pass and builds context from it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | `'/obj'` | Starting network path. |
| `depth` | `int` | `2` | How many levels of sub-networks to follow. |

#### find_referencing_nodes

```python
find_referencing_nodes(path: str, root: str = '/obj', depth: int = 3)
```

Finds who references this node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the referenced node. |
| `root` | `str` | `'/obj'` | Scope to scan. |
| `depth` | `int` | `3` | How many levels to descend. |

### `explain`

Tool that explains one node in one call.

#### explain_node

```python
explain_node(path: str, max_help_chars: int = MAX_HELP)
```

Explains one node comprehensively. Call this first to understand a node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. Example: /obj/castle/wall_body |
| `max_help_chars` | `int` | `MAX_HELP` | How many characters of type help to include. |

### `analyze`

Tools that scan a whole network to find out what is going on.

#### network_overview

```python
network_overview(path: str = '/obj', depth: int = 1)
```

Shows at a glance what a network looks like. Call it when first looking at a scene.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | `'/obj'` | Network path. Examples: /obj, /obj/castle |
| `depth` | `int` | `1` | How many levels of sub-networks to follow. |

#### cook_chain

```python
cook_chain(path: str)
```

Shows what gets cooked, in what order, to produce this node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the resulting node. Example: /obj/castle/OUT |

#### find_expensive_nodes

```python
find_expensive_nodes(root: str = '/obj', depth: int = 3, top: int = 15)
```

Finds which nodes eat up time, **from measured values**.

| Argument | Type | Default | Description |
|---|---|---|---|
| `root` | `str` | `'/obj'` | Path to start scanning from. |
| `depth` | `int` | `3` | How many levels of sub-networks to follow. |
| `top` | `int` | `15` | How many of the slowest to show. |

#### scene_snapshot

```python
scene_snapshot(label: str, root: str = '/obj', depth: int = 3)
```

Captures the current state. Later, `diff_scene` shows what changed.

| Argument | Type | Default | Description |
|---|---|---|---|
| `label` | `str` | required | Name to call this snapshot by. Example: "before_bevel" |
| `root` | `str` | `'/obj'` | Scope to capture. |
| `depth` | `int` | `3` | How many levels of sub-networks to follow. |

#### diff_scene

```python
diff_scene(label: str, other: str | None = None)
```

Compares a snapshot with now (or another snapshot) to show what changed.

| Argument | Type | Default | Description |
|---|---|---|---|
| `label` | `str` | required | Name of the baseline snapshot. |
| `other` | `str \| None` | `None` | Name of the snapshot to compare with. The current scene if omitted. |

### `geometry`

Tools that inspect geometry.

#### geometry_stats

```python
geometry_stats(path: str, output: int = 0)
```

Point, primitive and vertex counts and bounding box of a SOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. Example: /obj/castle/castle_wall |
| `output` | `int` | `0` | Output port index to read. Default 0. Used on nodes with several outputs (RBD solver constraints are 1). |

#### list_attributes

```python
list_attributes(path: str, output: int = 0)
```

Lists the attributes of geometry by class.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `output` | `int` | `0` | Output port index to read. Default 0. Used on nodes with several outputs (RBD solver constraints are 1). |

#### list_groups

```python
list_groups(path: str, output: int = 0)
```

Lists the groups of geometry by class.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `output` | `int` | `0` | Output port index to read. Default 0. Used on nodes with several outputs (RBD solver constraints are 1). |

#### sample_points

```python
sample_points(path: str, count: int = 10, start: int = 0, output: int = 0)
```

Samples a few point positions.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `count` | `int` | `10` | Number to sample. Up to 200. |
| `start` | `int` | `0` | Point index to start from. |
| `output` | `int` | `0` | Output port index to read. Default 0. Used on nodes with several outputs (RBD solver constraints are 1). |

#### attribute_values

```python
attribute_values(path: str, name: str, owner: str = 'point', count: int = 10, start: int = 0, output: int = 0)
```

Reads a few attribute values.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path. |
| `name` | `str` | required | Attribute name. Examples: P, Cd, name |
| `owner` | `str` | `'point'` | One of point / prim / vertex / detail. UVs are usually vertex. |
| `count` | `int` | `10` | Number to read. Up to 200. Ignored for detail, which has only one. |
| `start` | `int` | `0` | Index to start from. |
| `output` | `int` | `0` | Output port index to read. Default 0. Used on nodes with several outputs (RBD solver constraints are 1). |

### `cache`

Tools that write disk caches, check their status and clear them.

#### write_cache

```python
write_cache(source: str, comment: str, file_path: str | None = None, frame_start: float | None = None, frame_end: float | None = None, name: str | None = None)
```

Bakes geometry to a disk cache and confirms the files were created.

| Argument | Type | Default | Description |
|---|---|---|---|
| `source` | `str` | required | SOP path to bake, or the path of an existing cache node. |
| `comment` | `str` | required | What this cache is. Required. Stored in the scene, so write it in English. Example: "Baked wall geometry, 1.2M points" |
| `file_path` | `str \| None` | `None` | File path to write. If omitted, Houdini chooses one under $HIP/geo. |
| `frame_start` | `float \| None` | `None` | Start frame. Only the current frame if omitted. |
| `frame_end` | `float \| None` | `None` | End frame. |
| `name` | `str \| None` | `None` | Node name when creating a new one, showing its role, in English. |

#### list_caches

```python
list_caches(root: str = '/obj', depth: int = 4)
```

Finds every cache node in the scene.

| Argument | Type | Default | Description |
|---|---|---|---|
| `root` | `str` | `'/obj'` | Path to start scanning from. |
| `depth` | `int` | `4` | How many levels of sub-networks to follow. |

#### cache_status

```python
cache_status(path: str)
```

Shows whether a cache exists and whether it is stale.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Cache node path. |

#### clear_cache

```python
clear_cache(path: str | None = None, memory: bool = True, delete_files: bool = False)
```

Clears caches. Memory and disk are handled separately.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str \| None` | `None` | Path of the cache node whose disk files to delete. Used with delete_files. |
| `memory` | `bool` | `True` | Clear Houdini's memory cache. |
| `delete_files` | `bool` | `False` | **Permanently deletes** the disk files of the cache that path points to. |

### `viewport`

Tools that look at and control the viewport.

#### viewport_snapshot

```python
viewport_snapshot(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, frame: float | None = None, crop_to_camera: bool = False)
```

Captures the current viewport and returns it as a picture.

| Argument | Type | Default | Description |
|---|---|---|---|
| `width` | `int` | `DEFAULT_WIDTH` | Width in pixels. |
| `height` | `int` | `DEFAULT_HEIGHT` | Height in pixels. |
| `frame` | `float \| None` | `None` | Frame to capture. Defaults to the current frame. |
| `crop_to_camera` | `bool` | `False` | Crops outside the camera mask. Only meaningful when looking through a camera. |

#### viewport_sequence

```python
viewport_sequence(frames: list[float], columns: int = 4, tile_width: int = 480, tile_height: int = 270)
```

Captures several frames onto one sheet, to see what happens over time.

| Argument | Type | Default | Description |
|---|---|---|---|
| `frames` | `list[float]` | required | Frames to capture. Up to 16. Example: [1, 12, 20, 24, 36, 48] |
| `columns` | `int` | `4` | Number of tiles per row. |
| `tile_width` | `int` | `480` | Width of one tile in pixels. |
| `tile_height` | `int` | `270` | Height of one tile in pixels. |

#### frame_all

```python
frame_all()
```

Fits the viewport so the whole scene is visible.

#### frame_node

```python
frame_node(path: str)
```

Fits the viewport to a specific node's geometry.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. Example: /obj/castle/castle_wall |

#### viewport_info

```python
viewport_info()
```

Name, size and camera state of the current viewport.

#### set_viewport_camera

```python
set_viewport_camera(path: str | None = None, lock: bool = False)
```

Looks through a camera in the viewport, to check what a render actually captures.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str \| None` | `None` | Camera node path. Example: /obj/shot_cam |
| `lock` | `bool` | `False` | True locks the view to the camera so the viewpoint does not move by accident. |

#### set_viewport_direction

```python
set_viewport_direction(direction: str = 'persp')
```

Makes the viewport look from a fixed direction.

| Argument | Type | Default | Description |
|---|---|---|---|
| `direction` | `str` | `'persp'` | top / bottom / front / back / left / right / persp / uv |

#### set_viewport_display

```python
set_viewport_display(shading: str = 'smooth_wire', ghost_others: bool = False)
```

Sets how the viewport draws geometry.

| Argument | Type | Default | Description |
|---|---|---|---|
| `shading` | `str` | `'smooth_wire'` | wire / wire_ghost / hidden_line / hidden_line_ghost / flat / flat_wire / smooth / smooth_wire / bbox |
| `ghost_others` | `bool` | `False` | Draw objects not being worked on semi-transparent. |

#### set_viewport_renderer

```python
set_viewport_renderer(name: str | None = None)
```

Changes the viewport renderer. Without a name, lists the available ones.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str \| None` | `None` | Renderer name. If omitted, only the current one and the available ones are returned. |

#### list_panes

```python
list_panes()
```

The pane tabs currently open. Shows what the user is looking at.

#### set_current_network

```python
set_current_network(path: str)
```

Changes the network the network editor shows.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Network path to open. Example: /obj/castle |

### `visualize`

Tools for attribute visualizers.

#### visualize_attribute

```python
visualize_attribute(node: str, attribute: str, label: str, name: str | None = None, geometry_class: str = 'point', color_mode: str = 'attribramped', range_mode: str = 'auto', min_value: float | None = None, max_value: float | None = None)
```

Displays an attribute as colors in the viewport.

| Argument | Type | Default | Description |
|---|---|---|---|
| `node` | `str` | required | Node path to attach the visualizer to. Usually a geo object. |
| `attribute` | `str` | required | Attribute name to display. Examples: Cd, density, P |
| `label` | `str` | required | Name shown in the viewport toolbar. Write it in English. |
| `name` | `str \| None` | `None` | Internal name. The attribute name if omitted. |
| `geometry_class` | `str` | `'point'` | vertex / point / primitive / detail / auto |
| `color_mode` | `str` | `'attribramped'` | attribasis (vectors as colors) / attribramped (ramp) / constant / random / attribrandom |
| `range_mode` | `str` | `'auto'` | auto / min-max / center-width |
| `min_value` | `float \| None` | `None` | Lower bound when range_mode is min-max. |
| `max_value` | `float \| None` | `None` | Upper bound when range_mode is min-max. |

#### list_visualizers

```python
list_visualizers(node: str | None = None)
```

Lists attached visualizers.

| Argument | Type | Default | Description |
|---|---|---|---|
| `node` | `str \| None` | `None` | Node path. If given, only those on that node; otherwise the scene-wide ones. |

#### set_visualizer_active

```python
set_visualizer_active(node: str, name: str, active: bool = True)
```

Turns a visualizer on or off.

| Argument | Type | Default | Description |
|---|---|---|---|
| `node` | `str` | required | Path of the node the visualizer is attached to. |
| `name` | `str` | required | Visualizer name. |
| `active` | `bool` | `True` | Whether to turn it on or off. |

#### remove_visualizer

```python
remove_visualizer(node: str, name: str)
```

Deletes a visualizer.

| Argument | Type | Default | Description |
|---|---|---|---|
| `node` | `str` | required | Path of the node the visualizer is attached to. |
| `name` | `str` | required | Visualizer name. |

### `nodetypes`

Tools that look into node types before creating nodes.

#### list_node_types

```python
list_node_types(category: str = 'Sop', pattern: str = '*', include_hidden: bool = False)
```

Finds the node types available in a category.

| Argument | Type | Default | Description |
|---|---|---|---|
| `category` | `str` | `'Sop'` | Sop / Object / Dop / Cop / Top / Chop / Driver / Lop / Vop and so on. |
| `pattern` | `str` | `'*'` | Wildcard over names or labels. Examples: "copy*", "*scatter*" |
| `include_hidden` | `bool` | `False` | Include hidden and deprecated nodes. |

#### node_type_info

```python
node_type_info(category: str, type_name: str, parm_pattern: str = '*', detailed: bool = False)
```

Shows a type's parameters, inputs and outputs before creating the node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `category` | `str` | required | Sop / Object / Dop and so on. |
| `type_name` | `str` | required | Node type name. Examples: tube, copytopoints::2.0 |
| `parm_pattern` | `str` | `'*'` | Parameter name wildcard. Several can be given separated by spaces. Example: "rad* height cols". All by default. |
| `detailed` | `bool` | `False` | True also returns menu items and conditional enable expressions (DisableWhen). |

#### node_type_help

```python
node_type_help(category: str, type_name: str, max_chars: int = 4000)
```

Built-in help text of a node type.

| Argument | Type | Default | Description |
|---|---|---|---|
| `category` | `str` | required | Sop / Object / Dop and so on. |
| `type_name` | `str` | required | Node type name. |
| `max_chars` | `int` | `4000` | Length to truncate at. |

### `scene`

Tools that save and open scene files.

#### scene_path

```python
scene_path()
```

Current scene file path and saved state.

#### save_scene

```python
save_scene(path: str | None = None, overwrite: bool = False)
```

Saves the scene.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str \| None` | `None` | Path to save to. The current scene path if omitted. |
| `overwrite` | `bool` | `False` | True to overwrite an existing file. |

#### load_scene

```python
load_scene(path: str, discard_changes: bool = False)
```

Opens a scene file.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the .hip / .hipnc / .hiplc to open. |
| `discard_changes` | `bool` | `False` | Discard unsaved changes and open. |

#### new_scene

```python
new_scene(discard_changes: bool = False)
```

Clears the scene and starts fresh.

| Argument | Type | Default | Description |
|---|---|---|---|
| `discard_changes` | `bool` | `False` | Discard unsaved changes. |

#### set_frame_range

```python
set_frame_range(start: float, end: float, current: float | None = None)
```

Sets the playbar frame range.

| Argument | Type | Default | Description |
|---|---|---|---|
| `start` | `float` | required | Start frame. |
| `end` | `float` | required | End frame. |
| `current` | `float \| None` | `None` | Current frame. Left unchanged if omitted. |

### `deps`

What the scene depends on — listing, collecting, path remapping.

#### list_dependencies

```python
list_dependencies(kinds: Sequence[str] | None = None, missing_only: bool = False, include_outputs: bool = False, limit: int = MAX_LISTED)
```

Lists every external file the scene references and checks whether it actually exists.

| Argument | Type | Default | Description |
|---|---|---|---|
| `kinds` | `Sequence[str] \| None` | `None` | Filter by hou.fileType name: Geometry / Image / Otl / Usd / Alembic / Fbx / Hip / Directory / Any and so on. All if omitted. ["Image"] for textures only. |
| `missing_only` | `bool` | `False` | True returns only missing files. |
| `include_outputs` | `bool` | `False` | True also reports output path parameters. |
| `limit` | `int` | `MAX_LISTED` | Maximum number of entries in the list. Totals cover everything. |

#### collect_dependencies

```python
collect_dependencies(target_dir: str, kinds: Sequence[str] | None = None, overwrite: bool = False, relink: bool = False, dry_run: bool = True)
```

Gathers the files the scene uses into one directory. Optionally makes the scene point there.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target_dir` | `str` | required | Directory to gather into. Created if missing. |
| `kinds` | `Sequence[str] \| None` | `None` | Filter by hou.fileType name. If omitted, all input references such as images, geometry and HDAs. |
| `overwrite` | `bool` | `False` | Overwrite when the same name already exists in the target directory. |
| `relink` | `bool` | `False` | True rewrites the scene's parameters to the new paths after copying. Sequence tokens ($F4, <UDIM>) are preserved. |
| `dry_run` | `bool` | `True` | True (default) returns only the plan without copying. |

#### remap_paths

```python
remap_paths(find: str, replace: str, kinds: Sequence[str] | None = None, dry_run: bool = True)
```

Replaces part of file reference paths. Used when moving a scene to another machine.

| Argument | Type | Default | Description |
|---|---|---|---|
| `find` | `str` | required | String to find. Part of a path is enough. |
| `replace` | `str` | required | String to put in its place. Houdini variables such as $HIP can be used as is. |
| `kinds` | `Sequence[str] \| None` | `None` | Filter by hou.fileType name. All if omitted. |
| `dry_run` | `bool` | `True` | True (default) returns only the plan without changing anything. |

### `portability`

What to check before handing a scene over — portability checks.

#### validate_scene

```python
validate_scene(include_outputs: bool = False, limit: int = MAX_LISTED)
```

Decides whether a scene can move to another machine. Catches missing files and baked-in paths.

| Argument | Type | Default | Description |
|---|---|---|---|
| `include_outputs` | `bool` | `False` | True also judges output path parameters. |
| `limit` | `int` | `MAX_LISTED` | Maximum number of entries in the problem list. |

### `takes`

Tools for takes.

#### list_takes

```python
list_takes()
```

Lists every take in the scene and which one is currently active.

#### create_take

```python
create_take(name: str, parent: str | None = None, set_current: bool = True)
```

Creates a take.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | New take name, in English. Example: "night_lighting" |
| `parent` | `str \| None` | `None` | Parent take name. The current take if omitted. |
| `set_current` | `bool` | `True` | Switch to this take after creating it. |

#### set_current_take

```python
set_current_take(name: str)
```

Changes the active take.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Name of the take to switch to. |

#### delete_take

```python
delete_take(name: str, recurse: bool = False)
```

Deletes a take. Parameter values that existed only in that take are lost.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Name of the take to delete. |
| `recurse` | `bool` | `False` | Also delete child takes. |

#### take_include

```python
take_include(name: str, path: str, parms: list[str] | None = None, include: bool = True)
```

Decides which parameters vary separately in this take.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Take name. |
| `path` | `str` | required | Node path. |
| `parms` | `list[str] \| None` | `None` | Parameter names to include. All non-default parameters if omitted. |
| `include` | `bool` | `True` | False removes what was included. |

#### take_includes

```python
take_includes(name: str)
```

Shows which parameters this take includes.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Take name. |

### `diagnose`

Tools that find out what went wrong.

#### node_errors

```python
node_errors(path: str)
```

Reads the errors and warnings of one node.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |

#### find_error_nodes

```python
find_error_nodes(root: str = '/obj', depth: int = 3)
```

Finds nodes with errors or warnings in a scope.

| Argument | Type | Default | Description |
|---|---|---|---|
| `root` | `str` | `'/obj'` | Path to start scanning from. |
| `depth` | `int` | `3` | How many levels of sub-networks to follow. |

#### cook_node

```python
cook_node(path: str, force: bool = False)
```

Cooks a node to confirm it actually computes.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `force` | `bool` | `False` | Recook even nodes that are already cooked. |

#### cook_status

```python
cook_status(path: str)
```

Whether a node has cooked, how long it took, and whether it is time dependent.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |

#### delete_unused

```python
delete_unused(parent: str, keep: list[str] | None = None)
```

Deletes nodes that do not lead to an output.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Network path to clean up. |
| `keep` | `list[str] \| None` | `None` | Node names to always keep. |

### `anim`

Tools that put expressions and keyframes on parameters.

#### get_expression

```python
get_expression(path: str, name: str)
```

Reads the expression on a parameter.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. |

#### set_expression

```python
set_expression(path: str, name: str, expression: str, language: str = 'hscript')
```

Sets an expression on a parameter.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. |
| `expression` | `str` | required | Expression string. |
| `language` | `str` | `'hscript'` | hscript or python. |

#### clear_expression

```python
clear_expression(path: str, name: str, keep_value: bool = True)
```

Removes a parameter's expression and returns it to a plain value.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. |
| `keep_value` | `bool` | `True` | Keep the value the expression last produced. |

#### set_keyframe

```python
set_keyframe(path: str, name: str, frame: float, value: float | None = None, expression: str | None = None, interpolation: str = 'cubic')
```

Sets a keyframe on a parameter.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. |
| `frame` | `float` | required | Frame number. |
| `value` | `float \| None` | `None` | Key value. |
| `expression` | `str \| None` | `None` | Expression to set instead of a value. |
| `interpolation` | `str` | `'cubic'` | constant / linear / cubic / bezier / ease and so on. |

#### get_keyframes

```python
get_keyframes(path: str, name: str)
```

Keyframe list of a parameter.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. |

#### delete_keyframes

```python
delete_keyframes(path: str, name: str, start: float | None = None, end: float | None = None)
```

Deletes keyframes. Only that span if a range is given.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |
| `name` | `str` | required | Parameter name. |
| `start` | `float \| None` | `None` | Start frame of the span to delete. All if omitted. |
| `end` | `float \| None` | `None` | End frame of the span to delete. |

#### list_animated_parms

```python
list_animated_parms(path: str)
```

Finds parameters on a node that have keyframes or expressions.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path. |

### `execute`

Escape hatch for what the tools cannot do.

#### run_python

```python
run_python(code: str, comment: str)
```

Runs Python inside Houdini. Use only when no dedicated tool can do it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `code` | `str` | required | Python code to run. |
| `comment` | `str` | required | What is done and why. Logged together with the code. Required. |

#### run_hscript

```python
run_hscript(command: str)
```

Runs HScript commands.

| Argument | Type | Default | Description |
|---|---|---|---|
| `command` | `str` | required | One or more lines of HScript. |
