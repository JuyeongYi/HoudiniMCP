# Houdini MCP

한국어: [README.md](README.md)

An [MCP](https://modelcontextprotocol.io) server that runs **inside** SideFX Houdini, plus a set
of domain tool packs that supply its tools. An MCP client such as Claude Code attaches to a running
Houdini session to inspect the scene, build nodes, work with simulations, renders and textures, and
check the results as images.

- **Server inside the Houdini process** — streamable-http at `http://127.0.0.1:22926/mcp`. There is
  no separate server to run.
- **Domain tool packs** — SOP, DOP, LOP, materials, rendering, HDAs, rigging, CHOP, VEX, COP and
  more. Install only the packs you need.
- **Main-thread safe** — tools that touch `hou` run on Houdini's main thread automatically.
- **One undo step** — each scene-changing tool call is grouped into a single undo step.
- **Actionable errors** — a tool's error message reaches the model unchanged and says what to do next.
- **Visual checks** — viewport captures, frame sequences and COP image previews come back as images.

## Requirements

| Item | Version |
|---|---|
| Houdini | 22.0 or later (GUI session) |
| Python | 3.13 as shipped with Houdini |
| MCP Python SDK | `mcp>=2.2,<3` (installed into Houdini's Python) |
| ffmpeg (optional) | Needed only by the video tools. Set `FFMPEG_BIN_PATH` to the bin directory containing ffmpeg and ffprobe. A build with drawtext and libx264 is recommended |

Development and verification were done on Houdini 22.0.368 / Windows 11. The code is written to
support Windows, Linux and macOS.

## Installation

1. Get the repository.

   ```bash
   git clone <this repository> HoudiniMCP
   ```

2. Install the MCP SDK into **Houdini's Python** (not the system Python).

   ```bash
   # Windows
   "%HFS%\bin\hython.exe" -m pip install -r requirements.txt
   # Linux / macOS
   "$HFS/bin/hython" -m pip install -r requirements.txt
   ```

3. **Add** the repository's `packages/` to Houdini's package directories. Prepend it rather than
   overwrite the variable, or other plugin packages disappear. Each pack JSON looks for its pack
   directory one level above its own location (`$HOUDINI_PACKAGE_PATH`), so do not copy the JSON
   files elsewhere.

   ```bash
   # Windows (PowerShell) — the development launch script sets this for you
   .\scripts\run-houdini.ps1
   # Linux / macOS
   HOUDINI_PACKAGE_DIR="/path/to/HoudiniMCP/packages${HOUDINI_PACKAGE_DIR:+:$HOUDINI_PACKAGE_DIR}" houdini
   ```

   To leave a pack out, delete its `houdini_mcp_<domain>.json` from `packages/`.
   `houdini_mcp.json` (the server) is required.

4. The server starts once the Houdini UI is up. Logs go to
   `$HOUDINI_USER_PREF_DIR/log/houdini_mcp.jsonl`.

## Connecting an MCP client

Claude Code:

```bash
claude mcp add --transport http houdini http://127.0.0.1:22926/mcp
```

Or in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "houdini": { "type": "http", "url": "http://127.0.0.1:22926/mcp" }
  }
}
```

When running two Houdini instances, give the second one a different port (`HOUDINI_MCP_PORT`, or
`scripts/run-houdini.ps1 -Port 22927`). On the same port only the first instance opens a server.

## Tool packs

| Pack | Contents | Tool list |
|---|---|---|
| `houdini_mcp` | server and registry (no tools) | [architecture.en.md](docs/architecture.en.md) |
| `houdini_mcp_base` | context-independent inspection, editing, parameters, geometry, viewport, caches, scene | [README](houdini_mcp_base/README.en.md) |
| `houdini_mcp_sop` | SOP modelling, attributes, groups, UVs | [README](houdini_mcp_sop/README.en.md) |
| `houdini_mcp_lop` | USD stage, layers, composition, lights | [README](houdini_mcp_lop/README.en.md) |
| `houdini_mcp_mat` | material creation, assignment, textures, colour spaces | [README](houdini_mcp_mat/README.en.md) |
| `houdini_mcp_hda` | HDA creation, interface, sections, version control | [README](houdini_mcp_hda/README.en.md) |
| `houdini_mcp_rig` | KineFX skeletons, skinning, APEX graphs | [README](houdini_mcp_rig/README.en.md) |
| `houdini_mcp_dop` | DOP network setup, running, caching, checks | [README](houdini_mcp_dop/README.en.md) |
| `houdini_mcp_dop_rbd` | RBD piece and simulation diagnostics | [README](houdini_mcp_dop_rbd/README.en.md) |
| `houdini_mcp_chop` | CHOP channels, filters, audio, baking | [README](houdini_mcp_chop/README.en.md) |
| `houdini_mcp_render` | render settings, checks, running, result images | [README](houdini_mcp_render/README.en.md) |
| `houdini_mcp_io` | export (USD, Alembic, FBX) and import | [README](houdini_mcp_io/README.en.md) |
| `houdini_mcp_vex` | VEXpression compile validation, wrangles | [README](houdini_mcp_vex/README.en.md) |
| `houdini_mcp_cop` | checking COP (Copernicus) images | [README](houdini_mcp_cop/README.en.md) |
| `houdini_mcp_example` | minimal example for writing a new pack | [README](houdini_mcp_example/README.en.md) |

Each pack README is generated from the code by `scripts/gen_pack_readmes.py`; the English versions
use the translation catalog in `docs/i18n/en/`. Tool names, descriptions and arguments are listed
there.

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.en.md](docs/architecture.en.md) | server / tool pack split, startup and call flow, failure model |
| [docs/design/decisions.md](docs/design/decisions.md) | design decisions and the measurements behind them (Korean) |
| [docs/design/packs/README.md](docs/design/packs/README.md) | per-pack design principles and index (Korean) |
| `CLAUDE.md` | code and tool writing rules (Korean) |

## Development

| Task | Command |
|---|---|
| Launch Houdini for development | `.\scripts\run-houdini.ps1` (`-Port`, `-IsolatePrefs`, `-NoTools`, `-ConsoleLog`) |
| Tests (hython subprocesses) | `python -m pytest tests -q` |
| Lint | `ruff check .` |
| Generate pack READMEs | `python scripts/gen_pack_readmes.py` |
| Check pack READMEs and translations are current | `python scripts/gen_pack_readmes.py --check` |

Start a new tool pack by copying `houdini_mcp_example`; the steps are in
[docs/architecture.en.md](docs/architecture.en.md#creating-a-new-pack).

Tools that need the UI, such as viewport and render tools, cannot be verified in hython. After
changing a tool, hot-reload it into GUI Houdini and call it over MCP.
