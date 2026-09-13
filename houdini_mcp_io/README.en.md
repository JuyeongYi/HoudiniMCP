# houdini_mcp_io

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_io.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 8 |
| Modules (`TOOL_MODULES`) | `export`, `usd`, `interchange`, `load` |

## Overview

```text
Import, export and dependency tool pack — moves between the scene and disk.

    export       native geometry export and format guidance. Everything is **read back and verified after writing**
    usd          USD export. Writes LOP stages with pxr and reopens them
    interchange  Alembic and FBX export. Verified with abcinfo and file signatures
    load         bringing files into the scene (the module is named load because `import` is reserved)

Where this pack departs from existing implementations is that it does not stop at writing.

1. **It does not stop at writing.** The exported file is reopened with a reader for its format
   and the point and primitive counts are compared. If they do not match, the tool says so.
   `hou.Geometry.saveToFile()` accepts `.usd` / `.abc` / `.fbx` extensions but writes ASCII
   `.geo` content (measured). Without reading the file back, this lie goes unnoticed.
The scene's file reference list, collection, path remapping and portability checks do not depend
on context and moved to `deps` / `portability` in houdini_mcp_base. The contents of image textures
are handled by `texture_info` in houdini_mcp_mat.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`write_geometry`](#write_geometry) | `export` | Writes SOP geometry in a native format and reads it back to confirm it matches. |  |
| [`export_formats`](#export_formats) | `export` | Tells which tool to use for which format and what works on this installation. |  |
| [`export_usd`](#export_usd) | `usd` | Exports a SOP or LOP to USD and reopens it with pxr to confirm. | ✓ |
| [`export_alembic`](#export_alembic) | `interchange` | Exports a SOP to Alembic and reopens it with abcinfo to confirm. | ✓ |
| [`export_fbx`](#export_fbx) | `interchange` | Exports an OBJ subtree or a SOP to FBX and checks the header. | ✓ |
| [`probe_file`](#probe_file) | `load` | **Actually opens** a file and returns what is inside. |  |
| [`import_geometry`](#import_geometry) | `load` | Creates a SOP that reads a geometry file, cooks it and returns what came in. | ✓ |
| [`import_scene`](#import_scene) | `load` | Merges nodes from another .hip into the current scene and counts what came in. | ✓ |

## Details by module

### `export`

Export tools — **always read back and verified after writing.**

#### write_geometry

```python
write_geometry(path: str, file_path: str, overwrite: bool = False, frame_range: Sequence[float] | None = None, verify: bool = True)
```

Writes SOP geometry in a native format and reads it back to confirm it matches.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path to export. |
| `file_path` | `str` | required | Path to save to. Houdini variables such as $HIP are allowed. Supported extensions: .bgeo.sc (recommended) / .bgeo / .geo / .obj / .ply / .stl / .vdb |
| `overwrite` | `bool` | `False` | True to overwrite an existing file. |
| `frame_range` | `Sequence[float] \| None` | `None` | [start, end] or [start, end, step]. If given, each frame is cooked and written; file_path must then contain a frame token such as $F4. |
| `verify` | `bool` | `True` | False skips reading back. Use only for very large caches. |

#### export_formats

```python
export_formats()
```

Tells which tool to use for which format and what works on this installation.

### `usd`

USD export - writes LOP stages directly with pxr and reopens them to compare.

#### export_usd

```python
export_usd(path: str, file_path: str, overwrite: bool = False, flatten: bool = True, set_metadata: bool = True, run_usdchecker: bool = False)
```

Exports a SOP or LOP to USD and reopens it with pxr to confirm.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP or LOP node path to export. |
| `file_path` | `str` | required | Path to save to. .usd / .usda (text) / .usdc (binary) / .usdz |
| `overwrite` | `bool` | `False` | True to overwrite an existing file. |
| `flatten` | `bool` | `True` | True flattens the composition into one self-contained file (references and sublayers resolved). False writes only the root layer — references stay relative and may break if the file is moved. |
| `set_metadata` | `bool` | `True` | True (default) fills upAxis and defaultPrim after writing. pxr's Export does not author these, so without them other DCCs do not know the orientation or the entry prim. |
| `run_usdchecker` | `bool` | `False` | True also runs the compliance check with $HFS/bin/usdchecker. |

### `interchange`

Alembic and FBX export - DCC interchange formats. Both are written through ROPs.

#### export_alembic

```python
export_alembic(path: str, file_path: str, overwrite: bool = False, frame_range: Sequence[float] | None = None)
```

Exports a SOP to Alembic and reopens it with abcinfo to confirm.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | SOP node path to export. |
| `file_path` | `str` | required | .abc path to save to. |
| `overwrite` | `bool` | `False` | True to overwrite an existing file. |
| `frame_range` | `Sequence[float] \| None` | `None` | [start, end] or [start, end, step]. Current frame only if omitted. The frames are stored as time samples inside one Alembic file. |

#### export_fbx

```python
export_fbx(path: str, file_path: str, overwrite: bool = False, frame_range: Sequence[float] | None = None, ascii_format: bool = False)
```

Exports an OBJ subtree or a SOP to FBX and checks the header.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path to export. An OBJ node (whole subtree) or a SOP. |
| `file_path` | `str` | required | .fbx path to save to. |
| `overwrite` | `bool` | `False` | True to overwrite an existing file. |
| `frame_range` | `Sequence[float] \| None` | `None` | [start, end] or [start, end, step]. Current frame only if omitted. |
| `ascii_format` | `bool` | `False` | True writes text FBX. Meant for debugging; the file gets larger. |

### `load`

Import tools — files into the scene, and a look inside a file before importing it.

#### probe_file

```python
probe_file(file_path: str, detail: bool = False)
```

**Actually opens** a file and returns what is inside.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file_path` | `str` | required | File path to open. Houdini variables such as $HIP are allowed. |
| `detail` | `bool` | `False` | True looks deeper (resolved layer list for USD, attributes and face sets for Alembic). Slower. |

#### import_geometry

```python
import_geometry(parent: str, file_path: str, comment: str, name: str | None = None)
```

Creates a SOP that reads a geometry file, cooks it and returns what came in.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Network path to create the node in. Example: /obj or /obj/castle |
| `file_path` | `str` | required | File path to read. Houdini variables such as $HIP are allowed. |
| `comment` | `str` | required | Why this node exists, in English. Read by whoever opens the scene. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. Choose a name that describes the role. |

#### import_scene

```python
import_scene(file_path: str, node_pattern: str = '*', overwrite_on_conflict: bool = False)
```

Merges nodes from another .hip into the current scene and counts what came in.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file_path` | `str` | required | Path of the .hip / .hipnc / .hiplc to merge. |
| `node_pattern` | `str` | `'*'` | Import only nodes matching this pattern. Everything by default. |
| `overwrite_on_conflict` | `bool` | `False` | Overwrite nodes at the same path. Hard to undo, so it must be requested explicitly. |
