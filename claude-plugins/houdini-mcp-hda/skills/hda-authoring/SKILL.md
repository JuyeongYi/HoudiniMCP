---
name: hda-authoring
description: Turn Houdini subnets into Digital Assets and maintain them with the houdini_mcp_hda tools - create, build the parameter interface, promote inner parameters, edit sections and callbacks, install/reload, validate by cooking, and expand/collapse for Git. Use when packaging a network as an HDA, changing an HDA's interface or scripts, or when an HDA fails to install or cook.
---

# HDA authoring

## Definition vs instance

- This pack edits the **HDA definition**: changes apply to every instance of the type and are saved into the `.hda` file.
- Base `add_spare_parm` changes **one node instance** only. Do not use it to change an asset's interface.

## Create

1. Build and test the network as a subnet first.
2. `create_hda(path, name, hda_file, comment, namespace, version, label)` — `name` is the core name without `::` (for example `brick_maker`); namespace and version make `ns::brick_maker::1.0`.
3. `hda_info(target)` — confirm metadata, sections and instances.

## Interface

- `promote_parm(path, inner, parm, link=True)` — lift an inner node's parameter and link it with an expression. Needs an instance path to reach inner nodes. Give vectors by tuple name (`size`).
- `add_hda_parm(target, kind, name, label, ...)` — new parameters (float/int/string/toggle/menu/button/ramps/separator), optionally in a folder.
- `hda_interface(target)` to read, `reorder_hda_parms` to order top-level entries, `remove_hda_parm` to remove.
- Labels, help text and script comments in English.

## Sections and callbacks

`hda_sections(target)` lists sections; `get_hda_section` / `set_hda_section(name="PythonModule"|"OnCreated"|"Help", language=...)` read and write; `remove_hda_section` deletes. Write script comments in English.

## Validate

`validate_hda(target, parms, frame)` instantiates the asset in a temporary node, cooks it with the given parameters and deletes the temporary node. Run it after every interface or section change.

## Libraries and versions

- `install_hda`, `uninstall_hda(force=...)`, `reload_hda` (updates scene instances), `list_installed_hdas(pattern, category)`.
- `save_as_hda` copies a definition to another file, optionally with a new name or version (for version bumps).
- Git: `expand_hda(file_path, directory)` writes a diffable directory; `collapse_hda(directory, file_path, install=True)` builds the `.hda` back.
