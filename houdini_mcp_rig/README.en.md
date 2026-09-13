# houdini_mcp_rig

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_rig.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 19 |
| Modules (`TOOL_MODULES`) | `skeleton`, `skin`, `apexgraph`, `check` |

## Overview

```text
Rigging tool pack — skeletons · skin weights · APEX rig graphs · rig validation.

    skeleton   creates joints, reads the hierarchy, sets poses
    skin       creates skin weights, analyses them with numpy, deforms
    apexgraph  reads APEX rig graphs and turns them back into code. Queries 2,286 callbacks
    check      validate_rig — checks whether a rig is correct

This pack departs from existing implementations in two ways.

1. **It validates.** None of the five existing MCP implementations surveyed checks whether a rig
   is correct. `validate_rig` checks hierarchy, names, joint orientation, weight sums and bind pose
   with numpy in one pass, and says what to do next for every finding.
2. **It uses APEX.** All five existing implementations stop at placing KineFX SOP nodes.
   `apex_rig_script` decompiles a rig graph into APEX Script code and returns it.

**Boundary** — motion data does not belong to this pack. MotionClips, CHOP channels and keyframes
are handled by `houdini_mcp_chop`. This pack goes only as far as **a single pose** (one state of a
skeleton). Once values flow along the time axis, it is the chop pack's job.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`create_skeleton`](#create_skeleton) | `skeleton` | Creates a KineFX skeleton from a list of joints. | ✓ |
| [`skeleton_info`](#skeleton_info) | `skeleton` | The whole skeleton at a glance — joint count, roots, depth, bone lengths, attributes. |  |
| [`list_joints`](#list_joints) | `skeleton` | Lists joints with hierarchy information. |  |
| [`joint_info`](#joint_info) | `skeleton` | One joint in detail — hierarchy path, world position, rotation matrix, children, bone length. |  |
| [`pose_joints`](#pose_joints) | `skeleton` | Rotates or moves joints. Descendants follow along. | ✓ |
| [`compare_poses`](#compare_poses) | `skeleton` | Compares how far same-named joints of two skeletons are apart. |  |
| [`joint_attributes`](#joint_attributes) | `skeleton` | Shows the joint attributes a skeleton actually carries, with example values. |  |
| [`capture_skin`](#capture_skin) | `skin` | Attaches a mesh to a skeleton and returns statistics about the result. | ✓ |
| [`weight_stats`](#weight_stats) | `skin` | Returns statistics about the distribution of all skin weights. |  |
| [`find_unweighted_points`](#find_unweighted_points) | `skin` | Finds points not attached to anything. These points stay in place when deforming. |  |
| [`joint_influence`](#joint_influence) | `skin` | Shows which points one joint pulls and by how much. |  |
| [`deform_skin`](#deform_skin) | `skin` | Deforms the skin to a pose and returns a measurement of whether it actually moved. | ✓ |
| [`apex_graph_info`](#apex_graph_info) | `apexgraph` | Summarises the structure of an APEX rig graph — node, wire and port counts, callback distribution, errors. |  |
| [`apex_graph_nodes`](#apex_graph_nodes) | `apexgraph` | Lists the nodes of an APEX graph with callbacks, tags and parameters. |  |
| [`apex_rig_script`](#apex_rig_script) | `apexgraph` | Decompiles an APEX graph into APEX Script code and returns it. |  |
| [`apex_callbacks`](#apex_callbacks) | `apexgraph` | Searches the APEX callback registry — the list of operations usable in rig graphs. |  |
| [`apex_callback_info`](#apex_callback_info) | `apexgraph` | Signature of one APEX callback — input and output names and types, parameter defaults. |  |
| [`build_fk_rig`](#build_fk_rig) | `apexgraph` | Builds an APEX FK rig graph from a skeleton. | ✓ |
| [`validate_rig`](#validate_rig) | `check` | Checks whether a rig is correct. The flagship of this pack. |  |

## Details by module

### `skeleton`

Create skeletons, read them and set poses.

#### create_skeleton

```python
create_skeleton(parent: str, joints: Sequence[dict[str, Any]], comment: str, name: str | None = None)
```

Creates a KineFX skeleton from a list of joints.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Parent network to create the skeleton in. Usually a geo node under /obj. |
| `joints` | `Sequence[dict[str, Any]]` | required | List of joints, each with the following keys. name     - joint name (English). Must be unique. position - world position [x, y, z]. parent   - parent joint name. Omit or null for the root. |
| `comment` | `str` | required | What this skeleton is, in English. Example: Three joint test skeleton |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |

#### skeleton_info

```python
skeleton_info(path: str)
```

The whole skeleton at a glance — joint count, roots, depth, bone lengths, attributes.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the skeleton. |

#### list_joints

```python
list_joints(path: str, pattern: str = '*', limit: int = 200)
```

Lists joints with hierarchy information.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the skeleton. |
| `pattern` | `str` | `'*'` | Name pattern, using Houdini globs. Examples: arm_*, *_L |
| `limit` | `int` | `200` | Maximum number of joints returned. Up to 400. |

#### joint_info

```python
joint_info(path: str, joint: str)
```

One joint in detail — hierarchy path, world position, rotation matrix, children, bone length.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the skeleton. |
| `joint` | `str` | required | Joint name. Check it with list_joints. |

#### pose_joints

```python
pose_joints(path: str, poses: Sequence[dict[str, Any]], comment: str, name: str | None = None)
```

Rotates or moves joints. Descendants follow along.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the skeleton. |
| `poses` | `Sequence[dict[str, Any]]` | required | List of poses, each with the following keys. joint     - joint name. rotate    - [rx, ry, rz] in degrees. 0 if omitted. translate - [tx, ty, tz]. 0 if omitted. |
| `comment` | `str` | required | What this pose is, in English. Example: Bend elbow 45 degrees |
| `name` | `str \| None` | `None` | Node name prefix. Houdini picks one if omitted. |

#### compare_poses

```python
compare_poses(path: str, reference: str, limit: int = 20)
```

Compares how far same-named joints of two skeletons are apart.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Skeleton SOP path to compare. |
| `reference` | `str` | required | Skeleton SOP path to compare against. Usually the bind pose. |
| `limit` | `int` | `20` | How many of the most-moved joints to show. Up to 100. |

#### joint_attributes

```python
joint_attributes(path: str, limit: int = 12)
```

Shows the joint attributes a skeleton actually carries, with example values.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the skeleton. |
| `limit` | `int` | `12` | Number of joints shown per attribute. Up to 40. |

### `skin`

Create, read and apply skin weights.

#### capture_skin

```python
capture_skin(mesh: str, skeleton: str, comment: str, name: str | None = None, method: str = 'proximity', max_influences: int = 4, dropoff: float | None = None, normalize: bool = True)
```

Attaches a mesh to a skeleton and returns statistics about the result.

| Argument | Type | Default | Description |
|---|---|---|---|
| `mesh` | `str` | required | Mesh SOP path that becomes the skin. |
| `skeleton` | `str` | required | Skeleton SOP path. Must be in the bind pose. |
| `comment` | `str` | required | What is being captured, in English. Example: Capture body mesh to spine joints |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |
| `method` | `str` | `'proximity'` | proximity or biharmonic. |
| `max_influences` | `int` | `4` | Maximum number of joints attached to one point. |
| `dropoff` | `float \| None` | `None` | Distance falloff. Node default if omitted. |
| `normalize` | `bool` | `True` | Whether to make the weights sum to 1. |

#### weight_stats

```python
weight_stats(path: str, top: int = 12)
```

Returns statistics about the distribution of all skin weights.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path with boneCapture. |
| `top` | `int` | `12` | How many of the most influential joints to show. Up to 100. |

#### find_unweighted_points

```python
find_unweighted_points(path: str, limit: int = 20)
```

Finds points not attached to anything. These points stay in place when deforming.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path with boneCapture. |
| `limit` | `int` | `20` | How many points to show. Up to 100. |

#### joint_influence

```python
joint_influence(path: str, joint: str, limit: int = 20)
```

Shows which points one joint pulls and by how much.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path with boneCapture. |
| `joint` | `str` | required | Joint name. Check it in top_joints from weight_stats. |
| `limit` | `int` | `20` | How many of the highest-weighted points to show. Up to 100. |

#### deform_skin

```python
deform_skin(rest: str, capture_pose: str, animated_pose: str, comment: str, name: str | None = None)
```

Deforms the skin to a pose and returns a measurement of whether it actually moved.

| Argument | Type | Default | Description |
|---|---|---|---|
| `rest` | `str` | required | Captured mesh SOP path (the one with boneCapture). |
| `capture_pose` | `str` | required | Bind pose skeleton SOP path. |
| `animated_pose` | `str` | required | Target pose skeleton SOP path. |
| `comment` | `str` | required | What is being deformed, in English. Example: Deform body to bent elbow pose |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |

### `apexgraph`

Read APEX rig graphs.

#### apex_graph_info

```python
apex_graph_info(path: str)
```

Summarises the structure of an APEX rig graph — node, wire and port counts, callback distribution, errors.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the APEX graph. |

#### apex_graph_nodes

```python
apex_graph_nodes(path: str, pattern: str = '*', limit: int = 50, parms: bool = True)
```

Lists the nodes of an APEX graph with callbacks, tags and parameters.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the APEX graph. |
| `pattern` | `str` | `'*'` | Node name pattern, using APEX matching syntax as is. Examples: arm_*, *ik* |
| `limit` | `int` | `50` | Maximum number of nodes returned. Up to 200. |
| `parms` | `bool` | `True` | Whether to include parameter and port names. |

#### apex_rig_script

```python
apex_rig_script(path: str)
```

Decompiles an APEX graph into APEX Script code and returns it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path that outputs the APEX graph. |

#### apex_callbacks

```python
apex_callbacks(pattern: str = '*', limit: int = 50, include_hidden: bool = False)
```

Searches the APEX callback registry — the list of operations usable in rig graphs.

| Argument | Type | Default | Description |
|---|---|---|---|
| `pattern` | `str` | `'*'` | Name pattern. Examples: *ik*, fbik::*, Transform* |
| `limit` | `int` | `50` | Maximum number returned. Up to 200. |
| `include_hidden` | `bool` | `False` | Whether to include callbacks hidden for internal use. |

#### apex_callback_info

```python
apex_callback_info(name: str)
```

Signature of one APEX callback — input and output names and types, parameter defaults.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Callback name, exactly as found with apex_callbacks. |

#### build_fk_rig

```python
build_fk_rig(skeleton: str, comment: str, name: str | None = None)
```

Builds an APEX FK rig graph from a skeleton.

| Argument | Type | Default | Description |
|---|---|---|---|
| `skeleton` | `str` | required | Skeleton SOP path. Must have the transform attribute (produced by create_skeleton or kinefx::rigdoctor). |
| `comment` | `str` | required | What this rig is, in English. Example: FK rig for test tube character |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |

### `check`

Validate whether a rig is correct.

#### validate_rig

```python
validate_rig(skeleton: str, skin: str | None = None, max_influences: int = 4)
```

Checks whether a rig is correct. The flagship of this pack.

| Argument | Type | Default | Description |
|---|---|---|---|
| `skeleton` | `str` | required | Skeleton SOP path. |
| `skin` | `str \| None` | `None` | Skin mesh SOP path with boneCapture. If omitted, only the skeleton is checked. |
| `max_influences` | `int` | `4` | Allowed number of influencing joints per point. Game engines usually use 4. |
