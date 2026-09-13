# houdini_mcp_chop

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_chop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 17개 |
| 모듈 (`TOOL_MODULES`) | `build`, `data`, `check`, `transfer`, `files`, `bake`, `audio` |

## 개요

```text
CHOP 전문 툴 팩 — 채널을 값이 아니라 **분석 결과**로 다룬다.

파라미터 하나에 키를 찍고 읽고 지우는 것은 `houdini_mcp_base` 의 anim 모듈에
있다. 프레임 범위는 base 의 `set_frame_range` 다. 여기는 채널을 시계열
데이터로 보고 그 성질을 판정하는 것을 담는다.

    build      CHOP 네트워크·노드 생성, 필터 적용 (전후 통계 비교)
    data       채널 목록·통계·샘플 — numpy 벌크 경로
    check      루프 가능 여부와 튐을 실제 값으로 판정
    transfer   CHOP <-> 파라미터 (키로 굽기, 파라미터 끌어오기, 익스포트 플래그)
    files      Houdini 채널 파일 입출력 (.clip/.bclip, .chan/.bchan)
    bake       파라미터의 식을 키프레임으로 굽고 값이 같은지 검증
    audio      오디오 파일을 읽어 파형을 분석

샘플을 하나씩 파지 않는다. `hou.Track.allSamples()` 가 범위를 통째로 주고,
numpy 가 그것을 압축한다. 실측으로 240샘플에 360배 차이가 난다
(docs/design/packs/chop.md 참고).

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`create_chop_network`](#create_chop_network) | `build` | CHOP 네트워크(chopnet)를 만든다. | ✓ |
| [`create_chop_node`](#create_chop_node) | `build` | CHOP 네트워크 안에 CHOP 을 만들고 쿡해서 채널을 돌려준다. | ✓ |
| [`apply_chop_filter`](#apply_chop_filter) | `build` | CHOP 뒤에 필터를 달고 **전후 통계를 비교해서** 돌려준다. | ✓ |
| [`list_channels`](#list_channels) | `data` | CHOP 의 채널 목록. 이름·샘플 수·값 범위까지 한 줄씩. |  |
| [`channel_stats`](#channel_stats) | `data` | 채널의 전체 분석. 이 팩의 핵심 툴이다. |  |
| [`channel_samples`](#channel_samples) | `data` | 채널의 **실제 값**을 본다. 구간을 좁히거나 추려서. |  |
| [`check_loop`](#check_loop) | `check` | 채널이 루프로 이어 붙일 수 있는지 실제 값으로 판정한다. |  |
| [`find_spikes`](#find_spikes) | `check` | 채널이 튄 프레임을 찾는다. |  |
| [`export_to_keyframes`](#export_to_keyframes) | `transfer` | CHOP 채널을 파라미터 키프레임으로 굽는다. **값이 맞는지 검증해서** 돌려준다. | ✓ |
| [`import_from_parms`](#import_from_parms) | `transfer` | 애니메이션된 파라미터를 Channel CHOP 으로 가져온다. | ✓ |
| [`set_chop_export`](#set_chop_export) | `transfer` | CHOP 의 익스포트 플래그를 켜고 끈다. 파라미터를 **살아 있는 채로** 몬다. | ✓ |
| [`export_channels`](#export_channels) | `files` | CHOP 출력을 클립 파일로 쓴다. 채널 이름이 보존된다. |  |
| [`import_channels`](#import_channels) | `files` | 채널 파일을 File CHOP 으로 읽어 들이고, 실제로 무엇이 들어왔는지 돌려준다. | ✓ |
| [`export_parm_channels`](#export_parm_channels) | `files` | 파라미터 애니메이션을 `.chan` / `.bchan` 으로 쓴다. 다른 DCC 가 읽는다. |  |
| [`import_parm_channels`](#import_parm_channels) | `files` | `.chan` / `.bchan` 을 파라미터 키프레임으로 읽어 넣는다. | ✓ |
| [`bake_channels`](#bake_channels) | `bake` | 파라미터에 걸린 식을 키프레임으로 굽는다. 값이 보존됐는지 확인해서 준다. | ✓ |
| [`load_audio`](#load_audio) | `audio` | 오디오 파일을 File CHOP 으로 읽고 파형을 분석해서 돌려준다. | ✓ |

## 모듈별 상세

### `build`

CHOP 네트워크와 노드를 만들고 필터를 건다.

#### create_chop_network

```python
create_chop_network(parent: str, comment: str, name: str | None = None)
```

CHOP 네트워크(chopnet)를 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 네트워크를 놓을 부모 경로. 예: /obj |
| `comment` | `str` | 필수 | 이 네트워크가 무엇을 위한 것인지. 영어로 적는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |

#### create_chop_node

```python
create_chop_node(parent: str, node_type: str, comment: str, name: str | None = None, parms: dict[str, Any] | None = None, inputs: Sequence[str] | None = None)
```

CHOP 네트워크 안에 CHOP 을 만들고 쿡해서 채널을 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | CHOP 네트워크 경로. create_chop_network 가 돌려준 것. |
| `node_type` | `str` | 필수 | CHOP 타입 이름. 예: noise, wave, constant |
| `comment` | `str` | 필수 | 이 노드가 무엇을 하는지. 영어로 적는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |
| `parms` | `dict[str, Any] \| None` | `None` | 걸 파라미터. 예: {"channelname": "shake", "amp": 0.4} |
| `inputs` | `Sequence[str] \| None` | `None` | 입력으로 이을 CHOP 경로들. 순서대로 0번 입력부터. |

#### apply_chop_filter

```python
apply_chop_filter(path: str, filter: str, comment: str, name: str | None = None, strength: float | None = None, parms: dict[str, Any] | None = None)
```

CHOP 뒤에 필터를 달고 **전후 통계를 비교해서** 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 필터를 걸 CHOP 경로. |
| `filter` | `str` | 필수 | lag, smooth, limit, shift, resample, spring, jiggle 중 하나. |
| `comment` | `str` | 필수 | 왜 이 필터를 거는지. 영어로 적는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |
| `strength` | `float \| None` | `None` | 필터의 주 파라미터. 생략하면 노드 기본값. |
| `parms` | `dict[str, Any] \| None` | `None` | 세부 파라미터를 직접 덮어쓴다. 예: {"min": 0, "max": 1} |

### `data`

채널을 읽는다 — 값 목록이 아니라 분석 결과로.

#### list_channels

```python
list_channels(path: str, output_index: int = 0)
```

CHOP 의 채널 목록. 이름·샘플 수·값 범위까지 한 줄씩.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `output_index` | `int` | `0` | 출력이 여러 개인 CHOP 의 출력 번호. |

#### channel_stats

```python
channel_stats(path: str, channels: Sequence[str] | None = None, output_index: int = 0, spike_threshold: float = c.SPIKE_THRESHOLD, still_tolerance: float | None = None, loop_tolerance: float = c.LOOP_TOLERANCE, sparkline_points: int = c.SPARKLINE_POINTS)
```

채널의 전체 분석. 이 팩의 핵심 툴이다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `channels` | `Sequence[str] \| None` | `None` | 볼 채널 이름들. 생략하면 전부. |
| `output_index` | `int` | `0` | 출력이 여러 개인 CHOP 의 출력 번호. |
| `spike_threshold` | `float` | `c.SPIKE_THRESHOLD` | 튐 판정 문턱. 낮출수록 민감해진다. 기본 6.0 |
| `still_tolerance` | `float \| None` | `None` | 정지로 볼 변화량. 생략하면 값 범위의 0.01%. |
| `loop_tolerance` | `float` | `c.LOOP_TOLERANCE` | 루프 판정 허용치. 값 범위 대비 비율. 기본 0.01 |
| `sparkline_points` | `int` | `c.SPARKLINE_POINTS` | 스파크라인 점 수. 기본 48 |

#### channel_samples

```python
channel_samples(path: str, channel: str, start_frame: float | None = None, end_frame: float | None = None, max_points: int = MAX_SAMPLE_POINTS, output_index: int = 0)
```

채널의 **실제 값**을 본다. 구간을 좁히거나 추려서.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `channel` | `str` | 필수 | 볼 채널 이름. list_channels 가 알려 준다. |
| `start_frame` | `float \| None` | `None` | 볼 구간 시작 프레임. 생략하면 채널의 처음. |
| `end_frame` | `float \| None` | `None` | 볼 구간 끝 프레임(포함). 생략하면 채널의 끝. |
| `max_points` | `int` | `MAX_SAMPLE_POINTS` | 돌려줄 값의 상한. 넘으면 등간격으로 추린다. |
| `output_index` | `int` | `0` | 출력이 여러 개인 CHOP 의 출력 번호. |

### `check`

채널을 **실제 값으로** 판정한다.

#### check_loop

```python
check_loop(path: str, channels: Sequence[str] | None = None, tolerance: float = c.LOOP_TOLERANCE, output_index: int = 0)
```

채널이 루프로 이어 붙일 수 있는지 실제 값으로 판정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `channels` | `Sequence[str] \| None` | `None` | 볼 채널 이름들. 생략하면 전부. |
| `tolerance` | `float` | `c.LOOP_TOLERANCE` | 허용치. 값 범위 대비 비율. 기본 0.01 (1%) |
| `output_index` | `int` | `0` | 출력이 여러 개인 CHOP 의 출력 번호. |

#### find_spikes

```python
find_spikes(path: str, channels: Sequence[str] | None = None, threshold: float = c.SPIKE_THRESHOLD, max_report: int = 40, output_index: int = 0)
```

채널이 튄 프레임을 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `channels` | `Sequence[str] \| None` | `None` | 볼 채널 이름들. 생략하면 전부. |
| `threshold` | `float` | `c.SPIKE_THRESHOLD` | 문턱. 낮출수록 민감해진다. 기본 6.0 |
| `max_report` | `int` | `40` | 채널당 돌려줄 튐 개수 상한. |
| `output_index` | `int` | `0` | 출력이 여러 개인 CHOP 의 출력 번호. |

### `transfer`

CHOP 과 파라미터 사이를 오간다.

#### export_to_keyframes

```python
export_to_keyframes(path: str, targets: dict[str, str] | None = None, channels: Sequence[str] | None = None, interpolation: str = 'linear', output_index: int = 0)
```

CHOP 채널을 파라미터 키프레임으로 굽는다. **값이 맞는지 검증해서** 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `targets` | `dict[str, str] \| None` | `None` | 채널 이름 -> 파라미터 경로. 예: {"shake": "/obj/cam/tx"} |
| `channels` | `Sequence[str] \| None` | `None` | 구울 채널 이름들. 생략하면 전부(또는 targets 의 키). |
| `interpolation` | `str` | `'linear'` | constant / linear / cubic / bezier / ease. 기본 linear. |
| `output_index` | `int` | `0` | 출력이 여러 개인 CHOP 의 출력 번호. |

#### import_from_parms

```python
import_from_parms(parent: str, parms: Sequence[str], comment: str, name: str | None = None)
```

애니메이션된 파라미터를 Channel CHOP 으로 가져온다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | CHOP 네트워크 경로. create_chop_network 가 돌려준 것. |
| `parms` | `Sequence[str]` | 필수 | 가져올 파라미터 경로들. 예: ["/obj/cam/tx", "/obj/cam/ty"] |
| `comment` | `str` | 필수 | 무엇을 가져오는지. 영어로 적는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |

#### set_chop_export

```python
set_chop_export(path: str, enable: bool = True)
```

CHOP 의 익스포트 플래그를 켜고 끈다. 파라미터를 **살아 있는 채로** 몬다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `enable` | `bool` | `True` | True 면 켜고 False 면 끈다. |

### `files`

채널을 Houdini 포맷 파일로 주고받는다. 자체 JSON 포맷을 만들지 않는다.

#### export_channels

```python
export_channels(path: str, file_path: str)
```

CHOP 출력을 클립 파일로 쓴다. 채널 이름이 보존된다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | CHOP 경로. |
| `file_path` | `str` | 필수 | 쓸 파일 경로. .clip / .bclip / .bclip.sc. $HIP 같은 변수를 그대로 쓴다. |

#### import_channels

```python
import_channels(parent: str, file_path: str, comment: str, name: str | None = None)
```

채널 파일을 File CHOP 으로 읽어 들이고, 실제로 무엇이 들어왔는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | CHOP 네트워크 경로. |
| `file_path` | `str` | 필수 | 읽을 파일 경로. $HIP 같은 변수를 그대로 쓴다 - File CHOP 에 원문으로 걸린다. |
| `comment` | `str` | 필수 | 이 채널이 무엇인지. 영어로 적는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |

#### export_parm_channels

```python
export_parm_channels(parms: Sequence[str], file_path: str, start_frame: float | None = None, end_frame: float | None = None)
```

파라미터 애니메이션을 `.chan` / `.bchan` 으로 쓴다. 다른 DCC 가 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parms` | `Sequence[str]` | 필수 | 내보낼 파라미터 경로들. 예: ["/obj/cam/tx", "/obj/cam/ty"] |
| `file_path` | `str` | 필수 | 쓸 파일 경로. .chan 또는 .bchan. $HIP 같은 변수를 그대로 쓴다. |
| `start_frame` | `float \| None` | `None` | 시작 프레임. 생략하면 씬의 전역 시작. |
| `end_frame` | `float \| None` | `None` | 끝 프레임(포함). 생략하면 씬의 전역 끝. |

#### import_parm_channels

```python
import_parm_channels(parms: Sequence[str], file_path: str, start_frame: float | None = None, end_frame: float | None = None)
```

`.chan` / `.bchan` 을 파라미터 키프레임으로 읽어 넣는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parms` | `Sequence[str]` | 필수 | 받을 파라미터 경로들. 컬럼 순서와 같아야 한다. |
| `file_path` | `str` | 필수 | 읽을 파일 경로. .chan 또는 .bchan. $HIP 같은 변수를 그대로 쓴다. |
| `start_frame` | `float \| None` | `None` | 넣을 구간 시작 프레임. 생략하면 씬의 전역 시작. |
| `end_frame` | `float \| None` | `None` | 끝 프레임(포함). 생략하면 씬의 전역 끝. |

### `bake`

파라미터의 식을 키프레임으로 굽고, **구운 값이 원래와 같은지 검증한다.**

#### bake_channels

```python
bake_channels(parms: Sequence[str], start_frame: float | None = None, end_frame: float | None = None, step: float = 1.0, interpolation: str = 'linear', keep_expression: bool = False)
```

파라미터에 걸린 식을 키프레임으로 굽는다. 값이 보존됐는지 확인해서 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parms` | `Sequence[str]` | 필수 | 구울 파라미터 경로들. 예: ["/obj/cam/tx", "/obj/cam/rz"] |
| `start_frame` | `float \| None` | `None` | 시작 프레임. 생략하면 씬의 전역 시작. |
| `end_frame` | `float \| None` | `None` | 끝 프레임(포함). 생략하면 씬의 전역 끝. |
| `step` | `float` | `1.0` | 키 간격(프레임). 1 이면 매 프레임. |
| `interpolation` | `str` | `'linear'` | constant / linear / cubic / bezier / ease. 기본 linear. |
| `keep_expression` | `bool` | `False` | True 면 식을 지우지 않고 키만 더한다. 보통 False 다. |

### `audio`

오디오를 읽어 **파형을 분석한다.**

#### load_audio

```python
load_audio(parent: str, file_path: str, comment: str, name: str | None = None, envelope_points: int = ENVELOPE_POINTS, set_audio_flag: bool = False)
```

오디오 파일을 File CHOP 으로 읽고 파형을 분석해서 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | CHOP 네트워크 경로. create_chop_network 가 돌려준 것. |
| `file_path` | `str` | 필수 | 오디오 파일 경로. .wav 를 확인했다. $HIP 같은 변수를 그대로 쓴다. |
| `comment` | `str` | 필수 | 이 오디오가 무엇인지. 영어로 적는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |
| `envelope_points` | `int` | `ENVELOPE_POINTS` | 포락선 점 수. 기본 64 |
| `set_audio_flag` | `bool` | `False` | True 면 이 CHOP 을 씬의 오디오 소스로 지정한다. |
