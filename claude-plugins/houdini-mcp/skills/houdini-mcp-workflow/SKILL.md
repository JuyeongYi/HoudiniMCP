---
name: houdini-mcp-workflow
description: Working rules for driving a live Houdini session through the Houdini MCP tools. Use at the start of any Houdini task (building, editing, simulating, rendering) and whenever a Houdini MCP tool fails, times out, or the scene looks different from what you expected.
---

# Working in Houdini through MCP

The MCP server runs **inside a GUI Houdini session**. Every tool acts on the scene the user has open, in real time. Tool names below are bare names; the prefix depends on how the server is connected (plugin or project `.mcp.json`).

## Start of a task

1. `scene_info` — scene path, unsaved changes, frame range, current frame.
2. `network_overview` on the network you will work in, then `explain_node` on nodes you plan to touch.
3. If a tool you expect is missing, the matching Houdini package (`houdini_mcp_<domain>`) is not loaded. Say so instead of emulating it with `run_python`.

## Respect the user's scene

- **Read before you change.** The user may have rewired nodes, moved display flags or added their own nodes since your last look. Re-read (`node_flags`, `network_graph`) before acting.
- **Never silently override the user's edits.** If your plan conflicts with a change they made (a display flag on their node, a different input wiring), ask first.
- If you temporarily change a flag or the current frame to inspect something, restore it.

## Creating and editing nodes

- `comment` is required when creating nodes. Write it, node names and undo labels in **English**; they are stored in the scene.
- Name nodes by role (`wall_body`, `flag_pin_edge`), never `box1`.
- Each scene-changing tool call is **one undo step**.
- Before setting parameters on an unfamiliar node, check `node_type_info` or `parm_info`: vector parms are set by component (`tx`, `ty`, `tz`), some parms are tuples, menus take tokens, and buttons are pressed, not set.
- Tool errors are written to be acted on: read the message, it says what to do next.

## Long operations and the main thread

- Tools that touch `hou` run on Houdini's main thread with a **120 s limit** (`MainThreadTimeout`). A foreground render or cache blocks the main thread and every later call fails.
- Use background paths (render/cache "in background" buttons, `start_render`) for heavy work.
- **Save the scene first** (`save_scene`) before any background job. An unsaved scene opens a modal dialog that blocks Houdini until a human clicks it.

## Escape hatch

`run_python` / `run_hscript` are last resorts for things no tool covers. Always pass a meaningful `comment`. If you find yourself using them repeatedly for the same job, report the missing tool.

## Verify, don't assume

After building or changing something, look at it (`viewport_snapshot`, `viewport_sequence`) and read numbers (`geometry_stats`, `node_errors`). See the `visual-review` skill.
