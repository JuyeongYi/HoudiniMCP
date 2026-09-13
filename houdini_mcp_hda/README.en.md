# houdini_mcp_hda

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_hda.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 19 |
| Modules (`TOOL_MODULES`) | `create`, `interface`, `sections`, `manage`, `vcs`, `check` |

## Overview

```text
HDA authoring and management tool pack — bakes subnets into digital assets, builds interfaces,
installs them and keeps them under version control.

    create      subnet → HDA, copying definitions
    interface   parameter interface of an HDA **definition** — add, promote, remove, reorder
    sections    sections inside a definition — callback scripts such as PythonModule, OnCreated
    manage      install, uninstall, reload, query
    vcs         expand into a Git-friendly directory and collapse back
    check       verifies by actually placing and cooking an instance

The boundary with parmedit in `houdini_mcp_base` differs. That module adds spare parameters to
**one node instance** (they stay on that node only). This pack changes the interface of the
**HDA definition** (every instance of the type changes along with it, and it is saved to the
.hda file).

Parameter templates are built with base's `parmtemplate` helper as is. DialogScript strings are
not assembled by hand.

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`create_hda`](#create_hda) | `create` | Bakes a subnet into a digital asset (HDA). | ✓ |
| [`save_as_hda`](#save_as_hda) | `create` | Copies an existing HDA definition into another .hda file. It can be renamed too. | ✓ |
| [`hda_interface`](#hda_interface) | `interface` | Reads the parameter interface of an HDA definition, expanded down to folders. |  |
| [`add_hda_parm`](#add_hda_parm) | `interface` | Adds a new parameter to an HDA definition's interface and saves the .hda file. | ✓ |
| [`promote_parm`](#promote_parm) | `interface` | Promotes an inner node's parameter to the HDA interface and links them with an expression. | ✓ |
| [`remove_hda_parm`](#remove_hda_parm) | `interface` | Removes a parameter or folder from an HDA interface. | ✓ |
| [`reorder_hda_parms`](#reorder_hda_parms) | `interface` | Changes the order of the top-level entries of an HDA interface. | ✓ |
| [`hda_sections`](#hda_sections) | `sections` | Lists the sections inside an HDA definition, with size, language and the start of the content. |  |
| [`get_hda_section`](#get_hda_section) | `sections` | Reads the whole content of one section. |  |
| [`set_hda_section`](#set_hda_section) | `sections` | Writes a section's content and saves the .hda file. Creates the section if missing. | ✓ |
| [`remove_hda_section`](#remove_hda_section) | `sections` | Deletes a section and saves the .hda file. | ✓ |
| [`install_hda`](#install_hda) | `manage` | Installs an .hda library in this session, returning what it brings in. | ✓ |
| [`uninstall_hda`](#uninstall_hda) | `manage` | Removes an .hda library from this session. The file is left alone. | ✓ |
| [`reload_hda`](#reload_hda) | `manage` | Rereads an .hda file from disk. Instances in the scene update to the new definition. | ✓ |
| [`list_installed_hdas`](#list_installed_hdas) | `manage` | Lists the HDA libraries installed in this session and the assets inside them. |  |
| [`hda_info`](#hda_info) | `manage` | Reads one HDA definition in detail — metadata, options, sections and instances. |  |
| [`expand_hda`](#expand_hda) | `vcs` | Expands an .hda file into a directory, in a form that can go into Git. | ✓ |
| [`collapse_hda`](#collapse_hda) | `vcs` | Collapses an expanded directory back into an .hda file. | ✓ |
| [`validate_hda`](#validate_hda) | `check` | Actually instantiates and cooks an HDA to confirm it works. Temporary nodes are deleted. | ✓ |

## Details by module

### `create`

Bake subnets into digital assets and move definitions to other files.

#### create_hda

```python
create_hda(path: str, name: str, hda_file: str, comment: str, namespace: str | None = None, version: str | None = None, label: str | None = None, icon: str | None = None, min_inputs: int = 0, max_inputs: int = 0)
```

Bakes a subnet into a digital asset (HDA).

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Path of the subnet node to bake. Example: /obj/castle/wall_builder |
| `name` | `str` | required | Core name of the node type. No `::`. Example: brick_maker |
| `hda_file` | `str` | required | .hda file path to save to. Created if missing. |
| `comment` | `str` | required | What this asset does, in English. Set on both the node and the definition. |
| `namespace` | `str \| None` | `None` | Namespace of the type name. Example: krafton |
| `version` | `str \| None` | `None` | Version of the type name. Example: "1.0" |
| `label` | `str \| None` | `None` | Name shown in the Tab menu, in English. Houdini picks one if omitted. |
| `icon` | `str \| None` | `None` | Icon name. Example: SOP_box |
| `min_inputs` | `int` | `0` | Minimum number of inputs. |
| `max_inputs` | `int` | `0` | Maximum number of inputs. 0 means no inputs. |

#### save_as_hda

```python
save_as_hda(target: str, hda_file: str, name: str | None = None, namespace: str | None = None, version: str | None = None, label: str | None = None, install: bool = True)
```

Copies an existing HDA definition into another .hda file. It can be renamed too.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Source. Node path of an HDA instance or a node type name (Sop/ns::brick_maker::1.0). |
| `hda_file` | `str` | required | .hda file path to copy into. Created if missing. |
| `name` | `str \| None` | `None` | New core name. Original name if omitted. |
| `namespace` | `str \| None` | `None` | New namespace. Original if omitted. |
| `version` | `str \| None` | `None` | New version. Original if omitted. |
| `label` | `str \| None` | `None` | Tab menu name, in English. |
| `install` | `bool` | `True` | True installs that file in this session after copying. |

### `interface`

Build the parameter interface of an HDA **definition**.

#### hda_interface

```python
hda_interface(target: str)
```

Reads the parameter interface of an HDA definition, expanded down to folders.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name (Sop/ns::brick_maker::1.0). |

#### add_hda_parm

```python
add_hda_parm(target: str, kind: str, name: str, label: str, size: int = 1, default: Any = None, min_value: float | None = None, max_value: float | None = None, menu_items: list[str] | None = None, menu_labels: list[str] | None = None, string_type: str = 'regular', help_text: str | None = None, folder: list[str] | None = None)
```

Adds a new parameter to an HDA definition's interface and saves the .hda file.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name. |
| `kind` | `str` | required | float / int / string / toggle / menu / button / ramp_float / ramp_color / separator. |
| `name` | `str` | required | Internal name, used by expressions and set_parms. Example: wall_height |
| `label` | `str` | required | Name shown in the UI, in English. Example: "Wall Height" |
| `size` | `int` | `1` | Number of components. Only meaningful for float/int/string. |
| `default` | `Any` | `None` | Default value. For vectors, give a list or one value to fill every component. |
| `min_value` | `float \| None` | `None` | Slider minimum. |
| `max_value` | `float \| None` | `None` | Slider maximum. |
| `menu_items` | `list[str] \| None` | `None` | Values to choose from for the menu kind. |
| `menu_labels` | `list[str] \| None` | `None` | Display names of those values. |
| `string_type` | `str` | `'regular'` | For the string kind: regular / file / node / node_list. |
| `help_text` | `str \| None` | `None` | Parameter tooltip, in English. |
| `folder` | `list[str] \| None` | `None` | Folder path to put it in. Example: ["Controls"]. Created if missing. |

#### promote_parm

```python
promote_parm(path: str, inner: str, parm: str, name: str | None = None, label: str | None = None, folder: list[str] | None = None, link: bool = True)
```

Promotes an inner node's parameter to the HDA interface and links them with an expression.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | Node path of the HDA instance. An instance is needed to reach inner nodes. |
| `inner` | `str` | required | Relative path of the inner node. Example: brick_body |
| `parm` | `str` | required | Parameter name to promote. Give vectors by tuple name. Example: size |
| `name` | `str \| None` | `None` | New name in the interface. Original name if omitted. |
| `label` | `str \| None` | `None` | Name shown in the UI, in English. Original label if omitted. |
| `folder` | `list[str] \| None` | `None` | Folder path to put it in. Example: ["Controls"]. Created if missing. |
| `link` | `bool` | `True` | True links the inner parameter with an expression. False only promotes it. |

#### remove_hda_parm

```python
remove_hda_parm(target: str, name: str)
```

Removes a parameter or folder from an HDA interface.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name. |
| `name` | `str` | required | Internal name of the parameter/folder to remove. Give vectors by tuple name. |

#### reorder_hda_parms

```python
reorder_hda_parms(target: str, order: list[str])
```

Changes the order of the top-level entries of an HDA interface.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name. |
| `order` | `list[str]` | required | Top-level entry names in the desired order. Example: ["size", "controls"] |

### `sections`

Sections inside an HDA definition — read and write callback scripts and help.

#### hda_sections

```python
hda_sections(target: str)
```

Lists the sections inside an HDA definition, with size, language and the start of the content.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name (Sop/ns::brick_maker::1.0). |

#### get_hda_section

```python
get_hda_section(target: str, name: str)
```

Reads the whole content of one section.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name. |
| `name` | `str` | required | Section name. Example: PythonModule |

#### set_hda_section

```python
set_hda_section(target: str, name: str, contents: str, language: str = 'python')
```

Writes a section's content and saves the .hda file. Creates the section if missing.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name. |
| `name` | `str` | required | Section name. Examples: PythonModule, OnCreated, Help |
| `contents` | `str` | required | Content to write. Write comments in English for scripts. |
| `language` | `str` | `'python'` | python / hscript / text. text is for sections that are not scripts. |

#### remove_hda_section

```python
remove_hda_section(target: str, name: str)
```

Deletes a section and saves the .hda file.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name. |
| `name` | `str` | required | Name of the section to delete. |

### `manage`

Install, uninstall and reload HDA libraries in the session, and read what they contain.

#### install_hda

```python
install_hda(file_path: str)
```

Installs an .hda library in this session, returning what it brings in.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file_path` | `str` | required | .hda or .otl file path. |

#### uninstall_hda

```python
uninstall_hda(file_path: str, force: bool = False)
```

Removes an .hda library from this session. The file is left alone.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file_path` | `str` | required | .hda file path, or "Embedded". |
| `force` | `bool` | `False` | True uninstalls even if instances exist. |

#### reload_hda

```python
reload_hda(file_path: str)
```

Rereads an .hda file from disk. Instances in the scene update to the new definition.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file_path` | `str` | required | .hda file path. |

#### list_installed_hdas

```python
list_installed_hdas(pattern: str | None = None, category: str | None = None, limit: int = 60)
```

Lists the HDA libraries installed in this session and the assets inside them.

| Argument | Type | Default | Description |
|---|---|---|---|
| `pattern` | `str \| None` | `None` | Glob pattern. Examples: "*brick*", "*/castle/*" |
| `category` | `str \| None` | `None` | Filter by node category. Examples: Sop, Object, Lop |
| `limit` | `int` | `60` | Maximum number of libraries returned. |

#### hda_info

```python
hda_info(target: str)
```

Reads one HDA definition in detail — metadata, options, sections and instances.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name (Sop/ns::brick_maker::1.0). |

### `vcs`

Expand HDAs into directories Git can handle, and collapse them back.

#### expand_hda

```python
expand_hda(file_path: str, directory: str, uncompress_contents: bool = True)
```

Expands an .hda file into a directory, in a form that can go into Git.

| Argument | Type | Default | Description |
|---|---|---|---|
| `file_path` | `str` | required | .hda file path to expand. |
| `directory` | `str` | required | Directory to expand into. Created if missing. |
| `uncompress_contents` | `bool` | `True` | True saves the contents uncompressed first. |

#### collapse_hda

```python
collapse_hda(directory: str, file_path: str, install: bool = True)
```

Collapses an expanded directory back into an .hda file.

| Argument | Type | Default | Description |
|---|---|---|---|
| `directory` | `str` | required | Directory created by `expand_hda`. |
| `file_path` | `str` | required | .hda file path to create. Overwritten if it exists. |
| `install` | `bool` | `True` | True installs it in this session after collapsing. |

### `check`

Confirm that an HDA actually works.

#### validate_hda

```python
validate_hda(target: str, parms: dict[str, Any] | None = None, frame: float | None = None)
```

Actually instantiates and cooks an HDA to confirm it works. Temporary nodes are deleted.

| Argument | Type | Default | Description |
|---|---|---|---|
| `target` | `str` | required | Node path of an HDA instance or a node type name (Sop/ns::brick_maker::1.0). |
| `parms` | `dict[str, Any] \| None` | `None` | Parameters to set before cooking. Example: {"size": 2.0} |
| `frame` | `float \| None` | `None` | Frame to validate at. Defaults to the current frame. |
