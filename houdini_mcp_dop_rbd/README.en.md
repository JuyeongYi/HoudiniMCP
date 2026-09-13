# houdini_mcp_dop_rbd

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_dop_rbd.json` |
| requires | `houdini_mcp`, `houdini_mcp_base`, `houdini_mcp_dop` |
| Tools | 2 |
| Modules (`TOOL_MODULES`) | `diagnose` |

## Overview

```text
RBD pack for DOP - diagnoses pieces and rigid body simulations.

    diagnose  rbd_piece_stats (check pieces before simulating), rbd_sim_report (read a simulation frame by frame)

houdini_mcp_dop holds what is solver-independent; what only makes sense for RBD lives here (the
pack split rule in the project CLAUDE.md). RBD that runs without a dopnet, such as the RBD Bullet
Solver SOP, is accepted too.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`rbd_piece_stats`](#rbd_piece_stats) | `diagnose` | Checks RBD pieces before simulating. Finds pieces that will fall as soon as the simulation starts. |  |
| [`rbd_sim_report`](#rbd_sim_report) | `diagnose` | Reads an RBD simulation frame by frame and returns what moved and broke, and when. |  |

## Details by module

### `diagnose`

Diagnose RBD pieces and simulations - when things collapse, the numbers say why.

#### rbd_piece_stats

```python
rbd_piece_stats(path: str, constraints: str | None = None, constraints_output: int = 0, density: float = 1000.0, sliver_volume: float = 0.05, output: int = 0, limit: int = 10)
```

Checks RBD pieces before simulating. Finds pieces that will fall as soon as the simulation starts.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP that outputs the pieces. Examples: rbdmaterialfracture, voronoifracture, assemble |
| `constraints` | `str \| None` | `None` | SOP that outputs the constraint geometry. If given, glue constraints are counted per piece. Example: connectadjacentpieces |
| `constraints_output` | `int` | `0` | Output index of the constraints node. RBD Constraint Properties uses 1. |
| `density` | `float` | `1000.0` | Density (kg/m³) used to estimate mass. If the pieces carry a density attribute, that is used instead. |
| `sliver_volume` | `float` | `0.05` | Pieces with a smaller volume are counted as thin slivers (m³). |
| `output` | `int` | `0` | Output index of the path node. |
| `limit` | `int` | `10` | Number of pieces to include in lists. Up to 50. |

#### rbd_sim_report

```python
rbd_sim_report(path: str, frames: list[float] | None = None, start: float = 1, end: float = 24, exclude: str = '', quiet_until: float | None = None, constraints_output: int | None = None, moved_threshold: float = 0.1, output: int = 0, group_by: str = '', limit: int = 10)
```

Reads an RBD simulation frame by frame and returns what moved and broke, and when.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP that outputs the simulated pieces. Examples: rbdbulletsolver, dopimport |
| `frames` | `list[float] \| None` | `None` | Frames to inspect. If omitted, start..end is split into about 12 frames. |
| `start` | `float` | `1` | Start frame when frames is omitted. |
| `end` | `float` | `24` | End frame when frames is omitted. |
| `exclude` | `str` | `''` | Piece name patterns to leave out of the statistics, separated by spaces. Example: "projectile". Excluded pieces are reported by position only. |
| `quiet_until` | `float \| None` | `None` | Pieces must stay still up to this frame (usually just before impact). |
| `constraints_output` | `int \| None` | `None` | Constraint output index. If omitted, the output whose label contains Constraint is used (1 for RBD Bullet Solver). |
| `moved_threshold` | `float` | `0.1` | A piece that moves more than this counts as "moved" (m). |
| `output` | `int` | `0` | Output index to read pieces from. For RBD Bullet Solver, 3 (Simulation Points) has one point per piece and is the fastest. |
| `group_by` | `str` | `''` | Name of a per-piece string attribute. If given, the moved count is split by its values on every frame (read from output 0). Example: "part" - tells whether only the roof falls or the walls get pushed too. |
| `limit` | `int` | `10` | Number of pieces to include in lists. Up to 50. |
