# houdini_mcp_chop

한국어: [README.md](README.md)

> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change
> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.
> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).

| Item | Value |
|---|---|
| Package JSON | `packages/houdini_mcp_chop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| Tools | 17 |
| Modules (`TOOL_MODULES`) | `build`, `data`, `check`, `transfer`, `files`, `bake`, `audio` |

## Overview

```text
CHOP tool pack — treats channels as **analysis results** rather than lists of values.

Setting, reading and deleting keys on a single parameter lives in the anim module of
`houdini_mcp_base`, and the frame range is base's `set_frame_range`. This pack treats channels
as time series and judges their properties.

    build      CHOP network and node creation, applying filters (before/after statistics)
    data       channel lists, statistics and samples — numpy bulk path
    check      decides from actual values whether a channel loops and where it spikes
    transfer   CHOP <-> parameters (bake to keys, pull parameters in, export flag)
    files      Houdini channel file I/O (.clip/.bclip, .chan/.bchan)
    bake       bakes parameter expressions to keyframes and verifies the values match
    audio      reads audio files and analyses the waveform

Samples are not read one by one. `hou.Track.allSamples()` returns the whole range at once and
numpy condenses it. Measured, the difference is 360x for 240 samples (see
docs/design/packs/chop.md).

Modules are not imported here. register_pack reads TOOL_MODULES and loads each module in
isolation, so one broken module does not stop the other tools from registering.
```

## Tools

Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).

| Tool | Module | Description | Undo |
|---|---|---|---|
| [`create_chop_network`](#create_chop_network) | `build` | Creates a CHOP network (chopnet). | ✓ |
| [`create_chop_node`](#create_chop_node) | `build` | Creates a CHOP inside a CHOP network, cooks it and returns its channels. | ✓ |
| [`apply_chop_filter`](#apply_chop_filter) | `build` | Appends a filter to a CHOP and returns **a before/after comparison of statistics**. | ✓ |
| [`list_channels`](#list_channels) | `data` | Channel list of a CHOP, one line each with name, sample count and value range. |  |
| [`channel_stats`](#channel_stats) | `data` | Full analysis of channels. The core tool of this pack. |  |
| [`channel_samples`](#channel_samples) | `data` | Shows the **actual values** of a channel, over a narrowed or thinned range. |  |
| [`check_loop`](#check_loop) | `check` | Decides from actual values whether channels can be joined into a loop. |  |
| [`find_spikes`](#find_spikes) | `check` | Finds the frames where channels spike. |  |
| [`export_to_keyframes`](#export_to_keyframes) | `transfer` | Bakes CHOP channels to parameter keyframes and returns them **after verifying the values match**. | ✓ |
| [`import_from_parms`](#import_from_parms) | `transfer` | Brings animated parameters into a Channel CHOP. | ✓ |
| [`set_chop_export`](#set_chop_export) | `transfer` | Turns a CHOP's export flag on or off. Drives parameters **live**. | ✓ |
| [`export_channels`](#export_channels) | `files` | Writes CHOP output to a clip file. Channel names are preserved. |  |
| [`import_channels`](#import_channels) | `files` | Reads a channel file into a File CHOP and returns what actually came in. | ✓ |
| [`export_parm_channels`](#export_parm_channels) | `files` | Writes parameter animation to `.chan` / `.bchan`, readable by other DCCs. |  |
| [`import_parm_channels`](#import_parm_channels) | `files` | Reads `.chan` / `.bchan` into parameter keyframes. | ✓ |
| [`bake_channels`](#bake_channels) | `bake` | Bakes parameter expressions to keyframes and returns a check that the values were preserved. | ✓ |
| [`load_audio`](#load_audio) | `audio` | Reads an audio file into a File CHOP, analyses the waveform and returns the result. | ✓ |

## Details by module

### `build`

Create CHOP networks and nodes and apply filters.

#### create_chop_network

```python
create_chop_network(parent: str, comment: str, name: str | None = None)
```

Creates a CHOP network (chopnet).

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | Parent path to place the network in. Example: /obj |
| `comment` | `str` | required | What this network is for. Write it in English. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |

#### create_chop_node

```python
create_chop_node(parent: str, node_type: str, comment: str, name: str | None = None, parms: dict[str, Any] | None = None, inputs: Sequence[str] | None = None)
```

Creates a CHOP inside a CHOP network, cooks it and returns its channels.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | CHOP network path, as returned by create_chop_network. |
| `node_type` | `str` | required | CHOP type name. Examples: noise, wave, constant |
| `comment` | `str` | required | What this node does. Write it in English. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |
| `parms` | `dict[str, Any] \| None` | `None` | Parameters to set. Example: {"channelname": "shake", "amp": 0.4} |
| `inputs` | `Sequence[str] \| None` | `None` | CHOP paths to connect as inputs, in order starting from input 0. |

#### apply_chop_filter

```python
apply_chop_filter(path: str, filter: str, comment: str, name: str | None = None, strength: float | None = None, parms: dict[str, Any] | None = None)
```

Appends a filter to a CHOP and returns **a before/after comparison of statistics**.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path to filter. |
| `filter` | `str` | required | One of lag, smooth, limit, shift, resample, spring, jiggle. |
| `comment` | `str` | required | Why this filter is applied. Write it in English. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |
| `strength` | `float \| None` | `None` | The filter's main parameter. Node default if omitted. |
| `parms` | `dict[str, Any] \| None` | `None` | Overrides detailed parameters directly. Example: {"min": 0, "max": 1} |

### `data`

Read channels — as analysis results, not lists of values.

#### list_channels

```python
list_channels(path: str, output_index: int = 0)
```

Channel list of a CHOP, one line each with name, sample count and value range.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `output_index` | `int` | `0` | Output index for CHOPs with several outputs. |

#### channel_stats

```python
channel_stats(path: str, channels: Sequence[str] | None = None, output_index: int = 0, spike_threshold: float = c.SPIKE_THRESHOLD, still_tolerance: float | None = None, loop_tolerance: float = c.LOOP_TOLERANCE, sparkline_points: int = c.SPARKLINE_POINTS)
```

Full analysis of channels. The core tool of this pack.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `channels` | `Sequence[str] \| None` | `None` | Channel names to inspect. All if omitted. |
| `output_index` | `int` | `0` | Output index for CHOPs with several outputs. |
| `spike_threshold` | `float` | `c.SPIKE_THRESHOLD` | Spike detection threshold. Lower is more sensitive. Default 6.0 |
| `still_tolerance` | `float \| None` | `None` | Change treated as standing still. Defaults to 0.01% of the value range. |
| `loop_tolerance` | `float` | `c.LOOP_TOLERANCE` | Loop detection tolerance as a fraction of the value range. Default 0.01 |
| `sparkline_points` | `int` | `c.SPARKLINE_POINTS` | Number of sparkline points. Default 48 |

#### channel_samples

```python
channel_samples(path: str, channel: str, start_frame: float | None = None, end_frame: float | None = None, max_points: int = MAX_SAMPLE_POINTS, output_index: int = 0)
```

Shows the **actual values** of a channel, over a narrowed or thinned range.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `channel` | `str` | required | Channel name to inspect. list_channels shows the names. |
| `start_frame` | `float \| None` | `None` | Start frame of the range. Defaults to the start of the channel. |
| `end_frame` | `float \| None` | `None` | End frame of the range (inclusive). Defaults to the end of the channel. |
| `max_points` | `int` | `MAX_SAMPLE_POINTS` | Maximum number of values returned. Beyond it, values are thinned evenly. |
| `output_index` | `int` | `0` | Output index for CHOPs with several outputs. |

### `check`

Judge channels **from their actual values**.

#### check_loop

```python
check_loop(path: str, channels: Sequence[str] | None = None, tolerance: float = c.LOOP_TOLERANCE, output_index: int = 0)
```

Decides from actual values whether channels can be joined into a loop.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `channels` | `Sequence[str] \| None` | `None` | Channel names to inspect. All if omitted. |
| `tolerance` | `float` | `c.LOOP_TOLERANCE` | Tolerance as a fraction of the value range. Default 0.01 (1%) |
| `output_index` | `int` | `0` | Output index for CHOPs with several outputs. |

#### find_spikes

```python
find_spikes(path: str, channels: Sequence[str] | None = None, threshold: float = c.SPIKE_THRESHOLD, max_report: int = 40, output_index: int = 0)
```

Finds the frames where channels spike.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `channels` | `Sequence[str] \| None` | `None` | Channel names to inspect. All if omitted. |
| `threshold` | `float` | `c.SPIKE_THRESHOLD` | Threshold. Lower is more sensitive. Default 6.0 |
| `max_report` | `int` | `40` | Maximum number of spikes reported per channel. |
| `output_index` | `int` | `0` | Output index for CHOPs with several outputs. |

### `transfer`

Move between CHOPs and parameters.

#### export_to_keyframes

```python
export_to_keyframes(path: str, targets: dict[str, str] | None = None, channels: Sequence[str] | None = None, interpolation: str = 'linear', output_index: int = 0)
```

Bakes CHOP channels to parameter keyframes and returns them **after verifying the values match**.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `targets` | `dict[str, str] \| None` | `None` | Channel name -> parameter path. Example: {"shake": "/obj/cam/tx"} |
| `channels` | `Sequence[str] \| None` | `None` | Channel names to bake. All (or the keys of targets) if omitted. |
| `interpolation` | `str` | `'linear'` | constant / linear / cubic / bezier / ease. Default linear. |
| `output_index` | `int` | `0` | Output index for CHOPs with several outputs. |

#### import_from_parms

```python
import_from_parms(parent: str, parms: Sequence[str], comment: str, name: str | None = None)
```

Brings animated parameters into a Channel CHOP.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | CHOP network path, as returned by create_chop_network. |
| `parms` | `Sequence[str]` | required | Parameter paths to bring in. Example: ["/obj/cam/tx", "/obj/cam/ty"] |
| `comment` | `str` | required | What is being brought in. Write it in English. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |

#### set_chop_export

```python
set_chop_export(path: str, enable: bool = True)
```

Turns a CHOP's export flag on or off. Drives parameters **live**.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `enable` | `bool` | `True` | True turns it on, False turns it off. |

### `files`

Exchange channels as Houdini-format files. No custom JSON format is invented.

#### export_channels

```python
export_channels(path: str, file_path: str)
```

Writes CHOP output to a clip file. Channel names are preserved.

| Argument | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | CHOP path. |
| `file_path` | `str` | required | File path to write. .clip / .bclip / .bclip.sc. Variables such as $HIP are kept as is. |

#### import_channels

```python
import_channels(parent: str, file_path: str, comment: str, name: str | None = None)
```

Reads a channel file into a File CHOP and returns what actually came in.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | CHOP network path. |
| `file_path` | `str` | required | File path to read. Variables such as $HIP are kept as is - the raw string goes into the File CHOP. |
| `comment` | `str` | required | What these channels are. Write it in English. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |

#### export_parm_channels

```python
export_parm_channels(parms: Sequence[str], file_path: str, start_frame: float | None = None, end_frame: float | None = None)
```

Writes parameter animation to `.chan` / `.bchan`, readable by other DCCs.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parms` | `Sequence[str]` | required | Parameter paths to export. Example: ["/obj/cam/tx", "/obj/cam/ty"] |
| `file_path` | `str` | required | File path to write. .chan or .bchan. Variables such as $HIP are kept as is. |
| `start_frame` | `float \| None` | `None` | Start frame. Defaults to the scene's global start. |
| `end_frame` | `float \| None` | `None` | End frame (inclusive). Defaults to the scene's global end. |

#### import_parm_channels

```python
import_parm_channels(parms: Sequence[str], file_path: str, start_frame: float | None = None, end_frame: float | None = None)
```

Reads `.chan` / `.bchan` into parameter keyframes.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parms` | `Sequence[str]` | required | Parameter paths that receive the values, in the same order as the columns. |
| `file_path` | `str` | required | File path to read. .chan or .bchan. Variables such as $HIP are kept as is. |
| `start_frame` | `float \| None` | `None` | Start frame of the range to fill. Defaults to the scene's global start. |
| `end_frame` | `float \| None` | `None` | End frame (inclusive). Defaults to the scene's global end. |

### `bake`

Bake parameter expressions to keyframes and **verify the baked values match the originals.**

#### bake_channels

```python
bake_channels(parms: Sequence[str], start_frame: float | None = None, end_frame: float | None = None, step: float = 1.0, interpolation: str = 'linear', keep_expression: bool = False)
```

Bakes parameter expressions to keyframes and returns a check that the values were preserved.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parms` | `Sequence[str]` | required | Parameter paths to bake. Example: ["/obj/cam/tx", "/obj/cam/rz"] |
| `start_frame` | `float \| None` | `None` | Start frame. Defaults to the scene's global start. |
| `end_frame` | `float \| None` | `None` | End frame (inclusive). Defaults to the scene's global end. |
| `step` | `float` | `1.0` | Key spacing in frames. 1 means every frame. |
| `interpolation` | `str` | `'linear'` | constant / linear / cubic / bezier / ease. Default linear. |
| `keep_expression` | `bool` | `False` | True adds keys without removing the expression. Usually False. |

### `audio`

Read audio and **analyse the waveform.**

#### load_audio

```python
load_audio(parent: str, file_path: str, comment: str, name: str | None = None, envelope_points: int = ENVELOPE_POINTS, set_audio_flag: bool = False)
```

Reads an audio file into a File CHOP, analyses the waveform and returns the result.

| Argument | Type | Default | Description |
|---|---|---|---|
| `parent` | `str` | required | CHOP network path, as returned by create_chop_network. |
| `file_path` | `str` | required | Audio file path. .wav has been verified. Variables such as $HIP are kept as is. |
| `comment` | `str` | required | What this audio is. Write it in English. |
| `name` | `str \| None` | `None` | Node name. Houdini picks one if omitted. |
| `envelope_points` | `int` | `ENVELOPE_POINTS` | Number of envelope points. Default 64 |
| `set_audio_flag` | `bool` | `False` | True makes this CHOP the scene's audio source. |
