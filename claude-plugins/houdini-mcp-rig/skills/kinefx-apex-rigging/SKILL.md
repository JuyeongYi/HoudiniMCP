---
name: kinefx-apex-rigging
description: Build and check character rigs in Houdini with the houdini_mcp_rig tools - KineFX skeletons and poses, skin capture and weight analysis, APEX rig graphs and callbacks, and rig validation. Use when creating or inspecting a skeleton, skinning a mesh, fixing deformation problems, reading or building APEX rigs, or validating a rig before export.
---

# KineFX and APEX rigging

This pack handles **one pose at a time**. Animation over time (MotionClips, channels, keyframes) belongs to the CHOP pack.

## Skeleton

1. `create_skeleton(parent, joints, comment)` — joints as `{name, position, parent}`; names must be unique and English.
2. `skeleton_info`, `list_joints(pattern)`, `joint_info(joint)`, `joint_attributes` — hierarchy, world transforms, bone lengths, attributes actually present.
3. `pose_joints(path, poses, comment)` — rotate/translate joints; descendants follow. `compare_poses(path, reference)` measures how far joints moved from the bind pose.

## Skin

1. `capture_skin(mesh, skeleton, comment, method, max_influences, normalize=True)` — the skeleton must be in the bind pose.
2. `weight_stats(path)` — distribution, influences per point, top joints.
3. `find_unweighted_points(path)` — points that will stay behind when deforming. Fix these first.
4. `joint_influence(path, joint)` — which points a joint pulls.
5. `deform_skin(rest, capture_pose, animated_pose, comment)` — deforms and measures whether the mesh really moved.

## APEX graphs

- `apex_graph_info` / `apex_graph_nodes(pattern, parms=True)` — structure, callbacks, ports, errors.
- `apex_rig_script(path)` — decompiles the graph into APEX Script code; read it to understand an existing rig.
- `apex_callbacks(pattern)` / `apex_callback_info(name)` — the operations available and their exact signatures. Look them up; do not guess port names.
- `build_fk_rig(skeleton, comment)` — FK rig graph from a skeleton with a `transform` attribute.

## Validate

`validate_rig(skeleton, skin, max_influences=4)` checks hierarchy, names, joint orientation, weight sums and bind pose in one pass, with a fix for every finding. Run it before handing a rig over or exporting (game engines usually allow 4 influences).
