---
name: rbd-destruction
description: Set up and diagnose rigid-body destruction in Houdini with the houdini_mcp_dop_rbd tools - fractured or stacked pieces, glue constraints, density and mass, pinned foundations, and frame-by-frame simulation reports. Use when building an RBD destruction, when pieces fall apart at frame one, the whole structure slides, nothing breaks, or you need to know what moved and broke when.
---

# RBD destruction

## Check pieces before simulating

`rbd_piece_stats(path, constraints=..., constraints_output=1)` on the fractured/assembled output:

- slivers (tiny volume) that explode or jitter;
- estimated mass per piece (uses the `density` attribute when present);
- glue constraints per piece — pieces with zero glue fall immediately.

Fix the pieces before the simulation, not after.

## Structures built from pieces

- Stacked blocks (bricks) make believable collapses; each block is a piece. Mortar is glue between neighbouring pieces.
- **Pin the foundation**: set `active = 0` on the bottom row / ground-contact pieces, or the whole structure slides as one.
- Use a string attribute such as `part` (`wall`, `roof`, `tower`) on every piece so reports can be split by it.

## Density and mass pitfalls

- The solver ignores a `density` attribute on **unpacked** pieces. Packed fragments from RBD Configure honor it.
- RBD Configure moves `name` to **points**; merging its output with geometry that has primitive `name` gives a name class mismatch. Match the class before merging.
- RBD Pack packs the whole geometry/constraints/proxy triplet together, not individual pieces.

## Read the simulation

`rbd_sim_report(path, start, end, quiet_until=..., group_by="part")` on the solver or DOP Import output:

- per frame: how many pieces moved, max and mean displacement, broken constraints;
- `group_by` splits counts by the attribute: shows whether only the roof falls or the walls slide too;
- `quiet_until` flags anything that moved before the impact frame;
- `exclude="projectile"` keeps the projectile out of the statistics.

Interpretation:

- Constraints broken but **nothing moved**: glue can break without motion; it is not a fragment problem.
- High mean displacement in a group with few broken constraints: the group moves as a block (unpinned foundation, or too strong glue).
- On RBD Bullet Solver, output 3 (Simulation Points, one point per piece) is the fastest to read. Its pivot jumps from the bounding-box center to the center of mass on the first step, so rest positions are taken one frame after the start.

## Verify visually

`viewport_sequence` across the impact, and a `make_video` of the whole collapse for review.
