---
name: dop-simulation-setup
description: Build, test, cache and debug Houdini simulations as DOP networks with the houdini_mcp_dop tools - objects, solvers, forces, fields, low-resolution test runs, stepping, .sim caches and setup validation. Use when setting up any simulation (rigid bodies, cloth/Vellum, pyro, particles), when a simulation explodes, is empty or behaves unexpectedly, or when caching a simulation.
---

# DOP simulations

## Build the DOP network directly

Set simulations up as an explicit DOP network (dopnet → objects → solver → forces), not as SOP-level solver shortcuts, so every object, relationship and force is visible and inspectable.

1. `create_dopnet(parent, name, comment, gravity, substeps)` — gravity, merge and output come wired.
2. `add_dop_object(dopnet, source_object, object_type, comment)` — picks the solver, wires it, optionally creates a DOP Import in the source object. Read what it returns: every node it created, parameters set and next steps.
3. `add_dop_force(dopnet, force_type, comment, parms)` — vector parms use component names (`velx`, `forcex`); a wrong name returns the valid ones.
4. `validate_simulation(dopnet)` before running.

## Run cheaply first

- `test_simulation(dopnet, start, end, resolution_factor)` — low-resolution run with a per-frame report (divergence, empty objects, field ranges).
- `step_simulation(dopnet, frames)` — advance from the current frame and see each frame's state.
- `reset_simulation(dopnet, cook_first_frame=True)` — discard the cache and check the initial state.
- Look at motion with `viewport_sequence` over several frames, not a single snapshot. Make sure the viewport displays your import node, not the raw DOP object.

## Inspect

`list_dop_objects`, `dop_object_info`, `dop_relationships`, `simulation_info`, `dop_node_info` (is this node actually part of the sim?), `list_dop_fields`, `field_stats(deep=True)` for NaNs, `sim_memory`.

## Cache

`write_sim_cache(dopnet, directory, start, end, comment)` bakes `.sim` files frame by frame through a File DOP; `sim_cache_status` compares memory and disk. Long bakes block the main thread; split long ranges.

## Cloth (Vellum)

Cloth meshes need evenly distributed triangles, and Vellum in DOPs has several non-obvious parameters and wiring rules. For cloth, flags and seamless loops read [vellum-cloth.md](vellum-cloth.md).
