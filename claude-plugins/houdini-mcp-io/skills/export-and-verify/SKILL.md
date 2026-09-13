---
name: export-and-verify
description: Export Houdini geometry and stages to disk and bring files in, verifying every file by reading it back, with the houdini_mcp_io tools - native geometry caches, USD, Alembic, FBX, file probing and scene merging. Use when writing geometry or USD for another tool or DCC, importing external files, or when an exported file looks empty or wrong elsewhere.
---

# Export and import with verification

Never trust that a write succeeded because it did not raise. Every export tool here reopens the file with a reader for its format and compares counts.

## Pick the right tool

Start with `export_formats` — it says which tool writes which format and what this installation supports.

| Format | Tool | Verified with |
|---|---|---|
| `.bgeo.sc`, `.bgeo`, `.geo`, `.obj`, `.ply`, `.stl`, `.vdb` | `write_geometry` | reloaded point/prim counts |
| `.usd`, `.usda`, `.usdc`, `.usdz` | `export_usd` | reopened with `pxr` |
| `.abc` | `export_alembic` | `abcinfo` |
| `.fbx` | `export_fbx` | file header |

- Do not write `.usd`, `.abc` or `.fbx` through a plain geometry save: `hou.Geometry.saveToFile()` accepts those extensions but writes ASCII `.geo` content.
- `export_usd(flatten=True)` writes a self-contained file; `False` keeps relative references that break if the file moves. Keep `set_metadata=True` so `upAxis` and `defaultPrim` are authored; `run_usdchecker=True` for delivery.
- Sequences: pass `frame_range` and put a frame token (`$F4`) in the path for `write_geometry`. Alembic and FBX store time samples in one file.
- Existing files are not overwritten unless `overwrite=True`.

## Read the verification

Check the returned counts against the source (`geometry_stats` on the exported node). A mismatch is reported, not raised: read it.

## Import

- `probe_file(file_path, detail=True)` — look inside a file before bringing it in (layers for USD, attributes and face sets for Alembic).
- `import_geometry(parent, file_path, comment, name)` — creates the file SOP, cooks it and returns what came in.
- `import_scene(file_path, node_pattern)` — merges nodes from another `.hip`. `overwrite_on_conflict` replaces nodes at the same path and is hard to undo; ask first.

Scene-wide file references, collection and path remapping are base pack tools (`list_dependencies`, `collect_dependencies`, `remap_paths`).
