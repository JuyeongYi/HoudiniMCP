# houdini_mcp_dop

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_dop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 18 |
| Modules (`TOOL_MODULES`) | `setup`, `objects`, `fields`, `run`, `cache`, `check` |

## Overview

```text
Common DOP tool pack — build simulations, run them, and know what happened.

Solver-specific work (pyro source plumbing, FLIP whitewater, RBD fracturing) goes into sub-packs.
This pack holds only what is solver-independent.

    setup    dopnet creation, adding objects, adding forces — explains everything it builds
    objects  queries simulation objects, relationships and solver setup
    fields   volume field lists and statistics — voxels are never sent wholesale
    run      frame stepping, low-resolution test runs, reset, memory
    cache    writing .sim caches and their status
    check    finds what is missing before running

Tool-less helpers are split in two. `_common` touches the scene (recipe tables, node resolution
and assembly, dopnet structure); `_state` reads cooked results (object summaries, field
statistics, frame stepping and divergence detection).

The setup tools here are not black-box macros. For every node they build, they return its role,
the parameters set, and what to do next, because the model has to be able to keep working on it.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`create_dopnet`](#create_dopnet) | `setup` | Creates an empty DOP network wired with gravity, merge and output, and returns it. | ✓ |
| [`add_dop_object`](#add_dop_object) | `setup` | Brings /obj geometry into the simulation and returns an explanation of everything it built. | ✓ |
| [`add_dop_force`](#add_dop_force) | `setup` | Inserts a force acting on the whole simulation at the end of the chain and returns what changed. | ✓ |
| [`list_dop_objects`](#list_dop_objects) | `objects` | Objects in the cooked simulation and the state of each. |  |
| [`dop_object_info`](#dop_object_info) | `objects` | One simulation object in depth: records, subdata, creating node, solver. |  |
| [`dop_relationships`](#dop_relationships) | `objects` | Simulation relationships — what affects what, and which constraints exist. |  |
| [`simulation_info`](#simulation_info) | `objects` | The whole simulation setup — solvers, timestep, substeps, cache settings, current state. |  |
| [`dop_node_info`](#dop_node_info) | `objects` | Whether one DOP node inside a dopnet actually takes part in the simulation, and its connections. |  |
| [`list_dop_fields`](#list_dop_fields) | `fields` | Volume fields of a simulation object — kind, resolution, voxel count, memory. |  |
| [`field_stats`](#field_stats) | `fields` | Value statistics of one field. Voxels are never sent wholesale. |  |
| [`field_data_types`](#field_data_types) | `fields` | Splits an object's subdata by kind — fields, solvers, forces, other. |  |
| [`step_simulation`](#step_simulation) | `run` | Advances N frames from the current frame and returns the state of each frame. |  |
| [`test_simulation`](#test_simulation) | `run` | Runs N frames at low resolution and returns a per-frame report. |  |
| [`reset_simulation`](#reset_simulation) | `run` | Discards the simulation cache and returns to the initial state. Returns the memory freed. | ✓ |
| [`sim_memory`](#sim_memory) | `run` | Splits simulation memory by object and by subdata. |  |
| [`write_sim_cache`](#write_sim_cache) | `cache` | Runs the simulation over a frame range and bakes each frame to a .sim file. | ✓ |
| [`sim_cache_status`](#sim_cache_status) | `cache` | Cache status of this simulation — both the memory cache and the .sim files on disk. |  |
| [`validate_simulation`](#validate_simulation) | `check` | Checks a simulation setup before running and returns what is missing and how to fix it. |  |

## Details by module

### `setup`

Tools that build simulation networks.

#### create_dopnet

```python
create_dopnet(parent: str, name: str, comment: str, gravity: float = -9.81, start_frame: int | None = None, substeps: int | None = None, cache_size_mb: int | None = None)
```

Creates an empty DOP network wired with gravity, merge and output, and returns it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Network to hold the dopnet. Usually /obj |
| `name` | `str` | required | Dopnet name, showing what is simulated. Example: castle_collapse_sim |
| `comment` | `str` | required | What this simulation is for. Required. Stored in the scene, so write it in English. |
| `gravity` | `float` | `-9.81` | Y component of gravitational acceleration. 0 creates no gravity node. |
| `start_frame` | `int \| None` | `None` | Simulation start frame. Dopnet default (1) if omitted. |
| `substeps` | `int \| None` | `None` | Substeps per frame. 1 if omitted. Raise it if objects pass through each other. |
| `cache_size_mb` | `int \| None` | `None` | Simulation cache limit (MB). Default (5000) if omitted. |

#### add_dop_object

```python
add_dop_object(dopnet: str, source_object: str, object_type: str, comment: str, name: str | None = None, solver_type: str | None = None, parms: dict[str, Any] | None = None, create_import: bool = True)
```

Brings /obj geometry into the simulation and returns an explanation of everything it built.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. Example: /obj/castle_collapse_sim |
| `source_object` | `str` | required | geo node under /obj to put in the simulation. Example: /obj/falling_box |
| `object_type` | `str` | required | DOP object type: rbdobject (rigid body), staticobject (collider), rbdpackedobject (packed pieces), clothobject::2.0 (cloth), wireobject (wire), sandobject (sand), smokeobject (smoke container), popobject (particles), vellumobject (Vellum) and so on. |
| `comment` | `str` | required | The role of this object in the simulation. Required. In English. Example: "Tower blocks, active rigid bodies" |
| `name` | `str \| None` | `None` | DOP node name, showing its role. Example: tower_blocks_rbd |
| `solver_type` | `str \| None` | `None` | Only to choose the solver explicitly. Picked from the table if omitted. Example: bulletrbdsolver (to use Bullet instead of rigidbodysolver) |
| `parms` | `dict[str, Any] \| None` | `None` | Parameters for the DOP object node. Example: {"divsize": 0.05} |
| `create_import` | `bool` | `True` | Whether to create a DOP Import SOP in the source object. Turned off automatically for static colliders, which never need to read results back. |

#### add_dop_force

```python
add_dop_force(dopnet: str, force_type: str, comment: str, name: str | None = None, parms: dict[str, Any] | None = None, affect_objects: str | None = None)
```

Inserts a force acting on the whole simulation at the end of the chain and returns what changed.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `force_type` | `str` | required | DOP force node type: gravity, windforce, drag, fan, pointforce, vortexforce, magnetforce, uniformforce and so on. |
| `comment` | `str` | required | What this force does. Required. In English. Example: "Side wind pushing the smoke east" |
| `name` | `str \| None` | `None` | Node name. Example: side_wind |
| `parms` | `dict[str, Any] \| None` | `None` | Force node parameters. Vectors use separate component names — velx/vely/velz for windforce, forcex/forcey/forcez for uniformforce. Example: {"velx": 5.0}. A wrong name gets a list of what exists. |
| `affect_objects` | `str \| None` | `None` | Name pattern of the objects this force acts on. All if omitted. Example: "tower_*" |

### `objects`

Tools that look inside a simulation — objects, relationships, solver setup.

#### list_dop_objects

```python
list_dop_objects(dopnet: str, pattern: str = '*')
```

Objects in the cooked simulation and the state of each.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. Example: /obj/castle_collapse_sim |
| `pattern` | `str` | `'*'` | Object name pattern. Example: "tower_*". All by default. |

#### dop_object_info

```python
dop_object_info(dopnet: str, name: str)
```

One simulation object in depth: records, subdata, creating node, solver.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `name` | `str` | required | Object name, as shown by list_dop_objects. |

#### dop_relationships

```python
dop_relationships(dopnet: str)
```

Simulation relationships — what affects what, and which constraints exist.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |

#### simulation_info

```python
simulation_info(dopnet: str)
```

The whole simulation setup — solvers, timestep, substeps, cache settings, current state.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |

#### dop_node_info

```python
dop_node_info(path: str)
```

Whether one DOP node inside a dopnet actually takes part in the simulation, and its connections.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | DOP node path. Example: /obj/castle_collapse_sim/rbd_solver |

### `fields`

Tools that read volume fields as statistics.

#### list_dop_fields

```python
list_dop_fields(dopnet: str, name: str, include_temp: bool = False)
```

Volume fields of a simulation object — kind, resolution, voxel count, memory.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `name` | `str` | required | Object name. Example: smoke_container |
| `include_temp` | `bool` | `False` | Whether to include solver-internal temporary fields (__tempfield_*). |

#### field_stats

```python
field_stats(dopnet: str, name: str, field: str, deep: bool = False, bins: int = 16)
```

Value statistics of one field. Voxels are never sent wholesale.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `name` | `str` | required | Object name. Example: smoke_container |
| `field` | `str` | required | Field name. Examples: density, temperature, vel, pressure |
| `deep` | `bool` | `False` | Whether to read every voxel for a histogram and NaN count. |
| `bins` | `int` | `16` | Number of histogram bins when deep=True. |

#### field_data_types

```python
field_data_types(dopnet: str, name: str)
```

Splits an object's subdata by kind — fields, solvers, forces, other.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `name` | `str` | required | Object name. |

### `run`

Tools that actually run a simulation and return what happened.

#### step_simulation

```python
step_simulation(dopnet: str, frames: int = 1, deep_fields: bool = False, speed_limit: float = 100000.0)
```

Advances N frames from the current frame and returns the state of each frame.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `frames` | `int` | `1` | Number of frames to advance. 1 means just the next frame. |
| `deep_fields` | `bool` | `False` | Whether to read fields down to voxels for histograms and NaN counts. Slow for large fields. By default only cheap min/max/mean. |
| `speed_limit` | `float` | `100000.0` | Point speeds above this are flagged as divergence. |

#### test_simulation

```python
test_simulation(dopnet: str, start: int = 1, end: int = 10, resolution_factor: float = 2.0, substeps: int | None = None, deep_fields: bool = False, speed_limit: float = 100000.0)
```

Runs N frames at low resolution and returns a per-frame report.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `start` | `int` | `1` | Start frame. |
| `end` | `int` | `10` | End frame. The closer to start, the sooner it finishes. |
| `resolution_factor` | `float` | `2.0` | How many times to enlarge the voxel/particle spacing. 1 runs at the original resolution. |
| `substeps` | `int \| None` | `None` | Substeps to use during the test run. Unchanged if omitted. |
| `deep_fields` | `bool` | `False` | Whether to read fields down to voxels. Usually affordable at low resolution. |
| `speed_limit` | `float` | `100000.0` | Point speeds above this are flagged as divergence. |

#### reset_simulation

```python
reset_simulation(dopnet: str, cook_first_frame: bool = True)
```

Discards the simulation cache and returns to the initial state. Returns the memory freed.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `cook_first_frame` | `bool` | `True` | Whether to cook the start frame once after resetting, so the initial state can be checked right away. |

#### sim_memory

```python
sim_memory(dopnet: str, top: int = 15)
```

Splits simulation memory by object and by subdata.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `top` | `int` | `15` | How many of the largest subdata entries to show. |

### `cache`

Tools that bake simulation results to .sim files and read their status.

#### write_sim_cache

```python
write_sim_cache(dopnet: str, directory: str, start: int, end: int, comment: str, filename: str | None = None, compress: bool = True, deep_fields: bool = False)
```

Runs the simulation over a frame range and bakes each frame to a .sim file.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `directory` | `str` | required | Directory for the .sim files. Created if missing. Variables such as $HIP are kept as is - the raw string goes into the File DOP, so it still resolves if the scene moves. |
| `start` | `int` | required | Start frame. |
| `end` | `int` | required | End frame. |
| `comment` | `str` | required | Comment for the File DOP. Required. Stored in the scene, so write it in English. Example: "Bake tower collapse, frames 1-120" |
| `filename` | `str \| None` | `None` | File name pattern. Defaults to "<dopnet name>.$SF.sim". Must contain $SF (simulation frame) for the frame number. |
| `compress` | `bool` | `True` | Whether to compress .sim files. Uncompressed files are larger but read slightly faster. |
| `deep_fields` | `bool` | `False` | Whether to include field histograms in the frame report. |

#### sim_cache_status

```python
sim_cache_status(dopnet: str, start: int | None = None, end: int | None = None)
```

Cache status of this simulation — both the memory cache and the .sim files on disk.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
| `start` | `int \| None` | `None` | Start frame to check. Defaults to the playbar start. |
| `end` | `int \| None` | `None` | End frame to check. Defaults to the playbar end. |

### `check`

Tool that finds what is missing before running.

#### validate_simulation

```python
validate_simulation(dopnet: str)
```

Checks a simulation setup before running and returns what is missing and how to fix it.

| Argument | Type | Default | Description |
|---|---|---|---|
| `dopnet` | `str` | required | DOP network path. |
