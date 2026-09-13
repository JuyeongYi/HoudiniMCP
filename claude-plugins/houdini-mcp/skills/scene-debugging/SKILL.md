---
name: scene-debugging
description: Find out why a Houdini scene is wrong, slow or broken using the base inspection tools - errors, cook order, expensive nodes, dependencies, snapshots and diffs. Use when a node errors or warns, output is empty or unexpected, cooking is slow, files are missing, or you need to know what changed.
---

# Scene debugging

Work from the symptom to the cause. Prefer reading tools; change nothing until the cause is known.

## Errors and wrong output

1. `find_error_nodes` under the relevant root — every node with errors or warnings.
2. `node_errors` / `explain_node` on the first failing node upstream. `explain_node` combines type, parameters that differ from defaults, inputs, errors and comment in one call.
3. `cook_chain` on the output node — what cooks, in what order, to produce it. The broken link is usually the first node whose output stops looking right.
4. `geometry_stats` / `list_attributes` / `list_groups` at each step to see where points, attributes or groups disappear. Use `output` for nodes with several outputs.

## Slow scenes

- `find_expensive_nodes` reports measured cook times. Fix the top entries first.
- `cook_status` tells whether a node is time dependent (recooks every frame).

## What changed?

- `scene_snapshot(label)` before an experiment, `diff_scene(label)` after. Use it to show the user exactly what you changed, or to find what they changed.

## Dependencies and portability

- `node_references` / `find_referencing_nodes` — who depends on whom, including expressions.
- `list_dependencies(missing_only=True)` — external files that do not exist.
- `validate_scene` — missing files and absolute paths that break on another machine. `remap_paths` and `collect_dependencies` default to `dry_run=True`; show the plan before applying.

## Parameters

- `get_parms` without names returns only non-default values — the fastest way to see what someone set.
- `list_animated_parms`, `get_expression` — values driven by keys or expressions are not what `set_parms` changes.
