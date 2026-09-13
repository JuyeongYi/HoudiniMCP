# houdini_mcp_example

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_example.json` |
| requires | `houdini_mcp` |
| Tools | 1 |
| Modules (`TOOL_MODULES`) | `tools` |

## Overview

```text
Minimal example pack showing how to write a tool pack.

List the names of the modules that contain tools in TOOL_MODULES and register_pack loads them one
by one. Modules are not imported here so that one broken module does not stop the rest from
registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`tool_catalog`](#tool_catalog) | `tools` | Name, description and pack of every registered tool. |  |

## Details by module

### `tools`

Minimal example showing how to write a tool pack.

#### tool_catalog

```python
tool_catalog()
```

Name, description and pack of every registered tool.
