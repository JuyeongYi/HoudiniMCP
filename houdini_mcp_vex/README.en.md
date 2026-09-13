# houdini_mcp_vex

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_vex.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 8 |
| Modules (`TOOL_MODULES`) | `validate`, `wrangle`, `reference` |

## Overview

```text
VEX tool pack.

Write VEX code, **compile it**, and diagnose it. The key point is that validation does not use
nodes. Houdini ships the VEX compiler as an executable at `$HFS/bin/vcc`, so you get diagnostics
with exact line and column numbers without touching the scene.

    compiler   finds and calls vcc, parses diagnostics (no tools)
    snippet    translates wrangle @attribute syntax into plain VEX (no tools)
    validate   validate_vex, wrangle_attribs - validation without creating nodes
    wrangle    create_wrangle, update_wrangle, list_wrangles, diagnose_wrangle
    reference  list_vex_contexts, vex_function_info - reference for the VEX language itself

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering. compiler and
snippet have no tools and are not listed - the tool modules import them.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`validate_vex`](#validate_vex) | `validate` | Validates wrangle code by compiling it. Creates no nodes and does not touch the scene. |  |
| [`wrangle_attribs`](#wrangle_attribs) | `validate` | Extracts the attributes the code reads and writes and checks whether the input actually has them. |  |
| [`create_wrangle`](#create_wrangle) | `wrangle` | Creates a wrangle node and puts VEX code in it. The code is compiled first. | ✓ |
| [`update_wrangle`](#update_wrangle) | `wrangle` | Replaces a wrangle's VEX code. The code is compiled first. | ✓ |
| [`list_wrangles`](#list_wrangles) | `wrangle` | Scans the wrangles in a scope and their code. |  |
| [`diagnose_wrangle`](#diagnose_wrangle) | `wrangle` | Looks at one wrangle from three angles: compile errors, cook errors and attributes. |  |
| [`list_vex_contexts`](#list_vex_contexts) | `reference` | List of VEX contexts. Given one context, also returns its global variables. |  |
| [`vex_function_info`](#vex_function_info) | `reference` | Looks up VEX function signatures. If the name is not exact, similar ones are returned. |  |

## Details by module

### `validate`

Validate VEX without creating nodes.

#### validate_vex

```python
validate_vex(code: str, mode: str = MODE_SNIPPET, context: str = DEFAULT_CONTEXT, attrib_types: dict[str, str] | None = None, include_dirs: list[str] | None = None)
```

Validates wrangle code by compiling it. Creates no nodes and does not touch the scene.

| Argument | Type | Default | Description |
|---|---|---|---|
| `code` | `str` | required | Code to validate. Depending on mode, a VEXpression or plain VEX source. |
| `mode` | `str` | `MODE_SNIPPET` | "snippet" treats the code as a VEXpression for a wrangle (`@P.y += 1;`). "source" treats it as a plain VEX file that defines the context function itself. |
| `context` | `str` | `DEFAULT_CONTEXT` | VEX context. Wrangle snippets are all "cvex". Change it to "surface" and so on only for shader source. See list_vex_contexts for the list. |
| `attrib_types` | `dict[str, str] \| None` | `None` | Types for attributes written without a prefix. Example: {"myvec": "vector"}. If omitted, types are inferred with Houdini's rules and unknown names are treated as float. |
| `include_dirs` | `list[str] \| None` | `None` | Extra directories to search for `#include "..."`. |

#### wrangle_attribs

```python
wrangle_attribs(code: str, input_path: str | None = None, run_over: str = 'point', attrib_types: dict[str, str] | None = None)
```

Extracts the attributes the code reads and writes and checks whether the input actually has them.

| Argument | Type | Default | Description |
|---|---|---|---|
| `code` | `str` | required | Wrangle snippet. |
| `input_path` | `str \| None` | `None` | Input node to check against, usually the wrangle's first input. Cooked if it has not been. |
| `run_over` | `str` | `'point'` | Element the wrangle runs over: "point", "prim", "vertex", "detail". That class is searched first, then the others. |
| `attrib_types` | `dict[str, str] \| None` | `None` | Types for attributes written without a prefix. |

### `wrangle`

Create, change, find and diagnose wrangle nodes.

#### create_wrangle

```python
create_wrangle(parent: str, code: str, comment: str, node_type: str = 'attribwrangle', name: str | None = None, run_over: str = 'point', group: str | None = None, input_path: str | None = None, attrib_types: dict[str, str] | None = None)
```

Creates a wrangle node and puts VEX code in it. The code is compiled first.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Parent network path. Example: /obj/geo1 |
| `code` | `str` | required | Wrangle snippet. Use the `@` syntax as is, e.g. `@P.y += 1;`. |
| `comment` | `str` | required | What this wrangle does. Required. Stored in the scene file, so write it in English. Example: "Push points up by noise" |
| `node_type` | `str` | `'attribwrangle'` | Node type to create: attribwrangle, pointwrangle, volumewrangle, deformationwrangle, popwrangle, geometrywrangle, channelwrangle and so on. |
| `name` | `str \| None` | `None` | Node name. English, describing its role. If omitted, Houdini picks one. |
| `run_over` | `str` | `'point'` | Element to run over: "point", "prim", "vertex", "detail". Applies only to nodes with a class parameter. |
| `group` | `str \| None` | `None` | Group to process. All elements if omitted. |
| `input_path` | `str \| None` | `None` | Node path to connect as the first input. |
| `attrib_types` | `dict[str, str] \| None` | `None` | Types for attributes written without a prefix. Example: {"myvec": "vector"} |

#### update_wrangle

```python
update_wrangle(path: str, code: str, comment: str | None = None, attrib_types: dict[str, str] | None = None)
```

Replaces a wrangle's VEX code. The code is compiled first.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Wrangle node path. |
| `code` | `str` | required | New snippet. |
| `comment` | `str \| None` | `None` | Also replaces the comment. Update it if what the node does has changed. Stored in the scene, so write it in English. |
| `attrib_types` | `dict[str, str] \| None` | `None` | Types for attributes written without a prefix. |

#### list_wrangles

```python
list_wrangles(root: str = '/obj', depth: int = 3, contains: str | None = None)
```

Scans the wrangles in a scope and their code.

| Argument | Type | Default | Description |
|---|---|---|---|
| `root` | `str` | `'/obj'` | Path to start scanning from. |
| `depth` | `int` | `3` | How many levels of sub-networks to follow. |
| `contains` | `str \| None` | `None` | Only wrangles whose code contains this string. Example: "@Cd" |

#### diagnose_wrangle

```python
diagnose_wrangle(path: str, cook: bool = True)
```

Looks at one wrangle from three angles: compile errors, cook errors and attributes.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Wrangle node path. |
| `cook` | `bool` | `True` | Whether to cook the node to see real errors too. Set False if it is heavy. |

### `reference`

Reference for the VEX language itself — contexts, globals, function signatures.

#### list_vex_contexts

```python
list_vex_contexts(context: str | None = None)
```

List of VEX contexts. Given one context, also returns its global variables.

| Argument | Type | Default | Description |
|---|---|---|---|
| `context` | `str \| None` | `None` | Context whose globals to show. Examples: sop, cvex, surface. If omitted, only the list is returned. |

#### vex_function_info

```python
vex_function_info(name: str, context: str = 'sop')
```

Looks up VEX function signatures. If the name is not exact, similar ones are returned.

| Argument | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Function name. A partial name works. Examples: "noise", "pcopen", "prim" |
| `context` | `str` | `'sop'` | Context to check availability in: sop, cvex, surface and so on. The available functions differ slightly per context. |
