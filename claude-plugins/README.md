# Houdini MCP plugins for Claude Code

Skills and subagents for each Houdini MCP tool pack, published as a Claude Code plugin marketplace from this repository.

## Install - use the clone Houdini already uses

Houdini needs a clone of this repository anyway (its `packages/` directory is on `HOUDINI_PACKAGE_DIR`). Add **that same clone** as a local marketplace instead of adding the GitHub URL, which would clone the repository a second time under `~/.claude/plugins/marketplaces/`.

```text
git clone https://github.com/JuyeongYi/HoudiniMCP.git
/plugin marketplace add /path/to/HoudiniMCP
/plugin install houdini-mcp@houdini-mcp
/plugin install houdini-mcp-dop@houdini-mcp
```

- A local marketplace is read in place. Installed plugins are copied into `~/.claude/plugins/cache/` (only the plugin folders, not the repository).
- Every pack plugin depends on `houdini-mcp`, which is installed automatically.
- The catalog is `.claude-plugin/marketplace.json` at the repository root; plugins live in `claude-plugins/` and are referenced by relative path.

Do not point `HOUDINI_PACKAGE_DIR` at the marketplace clone Claude Code creates for a GitHub URL. Claude Code manages that folder: background `git pull` or a re-clone can change the code under a running Houdini and discard local edits.

## Update

```text
git pull                         (in the clone)
/plugin marketplace update houdini-mcp
/plugin update houdini-mcp-dop@houdini-mcp
```

Plugins pin `version` in `plugin.json`. Installed copies only update when that version changes, so **bump the plugin's `version` whenever you change its skills or agents**.

## What each plugin needs in Houdini

A plugin only teaches Claude how to use tools. The tools come from the matching Houdini package, which must be loaded in the Houdini session (`packages/houdini_mcp_<domain>.json`).

| Plugin | Houdini package | Skills | Subagents |
|---|---|---|---|
| `houdini-mcp` | `houdini_mcp`, `houdini_mcp_base` | `houdini-mcp-workflow`, `visual-review`, `scene-debugging` | `houdini-scene-auditor` |
| `houdini-mcp-sop` | `houdini_mcp_sop` | `sop-procedural-modeling` | |
| `houdini-mcp-vex` | `houdini_mcp_vex` | `vex-wrangle-authoring` | |
| `houdini-mcp-mat` | `houdini_mcp_mat` | `materialx-lookdev` | |
| `houdini-mcp-lop` | `houdini_mcp_lop` | `usd-stage-debugging` | |
| `houdini-mcp-render` | `houdini_mcp_render` | `render-and-verify` | `render-qc` |
| `houdini-mcp-dop` | `houdini_mcp_dop` | `dop-simulation-setup` | `simulation-debugger` |
| `houdini-mcp-dop-rbd` | `houdini_mcp_dop_rbd` | `rbd-destruction` | `rbd-diagnostician` |
| `houdini-mcp-hda` | `houdini_mcp_hda` | `hda-authoring` | |
| `houdini-mcp-rig` | `houdini_mcp_rig` | `kinefx-apex-rigging` | |
| `houdini-mcp-chop` | `houdini_mcp_chop` | `channel-analysis` | |
| `houdini-mcp-io` | `houdini_mcp_io` | `export-and-verify` | |
| `houdini-mcp-cop` | `houdini_mcp_cop` | `copernicus-textures` | |

## MCP server connection

`houdini-mcp` declares the `houdini` MCP server at `http://127.0.0.1:<port>/mcp`. The port is a plugin option (default `22926`, the server's `HOUDINI_MCP_PORT`).

If a project already connects the same server in its own `.mcp.json` (this repository does), the tools appear twice under two prefixes. Use one connection: disable the project entry or the plugin server.

Skills and subagents refer to tools by bare name (`make_video`), because the prefix depends on how the server is connected.

## Writing rules

- Plugin content is English.
- A skill states only facts measured in Houdini or stated by the tool itself. Tool lists and arguments live in each pack's generated `README.md`; skills explain when and how to use tools, not every argument.
- Validate after editing: `claude plugin validate .` (marketplace) and `claude plugin validate claude-plugins/<plugin>`.
