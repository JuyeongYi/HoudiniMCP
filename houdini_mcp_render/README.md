# houdini_mcp_render

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `houdini_mcp_render.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 13개 |
| 모듈 (`TOOL_MODULES`) | `settings`, `check`, `run`, `result` |

## 개요

```text
렌더를 걸고, 진행 상황을 알고, 결과 이미지를 실제로 읽어 확인하는 팩.

이 팩의 존재 이유는 마지막 한 줄이다. 렌더를 걸어 놓고 "끝났습니다" 로
돌려주면 새까만 프레임이 나와도 알 수 없다. 여기의 툴은 렌더가 끝나면
OpenImageIO 로 픽셀을 읽어 채널별 통계를 내고, 검거나 NaN 이 섞였으면
그렇다고 말한다.

모듈 구성:

    settings   UsdRender 스키마로 렌더 설정을 읽는다
    check      렌더를 걸기 전에 무엇이 빠졌는지 점검한다
    run        husk 백그라운드 렌더와 ROP 블로킹 렌더
    result     렌더 결과 이미지를 읽어 통계·썸네일·비교를 낸다

밑줄로 시작하는 모듈(_common, _usdrender, _image)은 헬퍼라 여기 적지 않는다.
TOOL_MODULES 에 적힌 것만 register_pack 이 격리해서 읽는다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`render_settings`](#render_settings) | `settings` | LOP 노드가 만든 스테이지의 렌더 설정을 UsdRender 스키마로 읽는다. |  |
| [`list_renderers`](#list_renderers) | `settings` | 이 설치본에서 실제로 쓸 수 있는 Hydra 렌더 델리게이트. |  |
| [`validate_render`](#validate_render) | `check` | 렌더를 걸어도 되는 상태인지 스테이지를 훑어 점검한다. |  |
| [`start_render`](#start_render) | `run` | husk 로 백그라운드 렌더를 시작하고 잡 핸들을 돌려준다. Houdini 는 멈추지 않는다. |  |
| [`render_status`](#render_status) | `run` | 렌더 잡의 진행 상황. 끝났으면 결과 이미지를 실제로 읽어 통계까지 준다. |  |
| [`render_log`](#render_log) | `run` | 렌더 잡이 내보낸 husk 로그의 끝부분. |  |
| [`cancel_render`](#cancel_render) | `run` | 돌고 있는 렌더를 중단한다. |  |
| [`render_rop`](#render_rop) | `run` | ROP 을 렌더하고, 나온 파일을 실제로 열어 무엇이 찍혔는지 돌려준다. |  |
| [`image_info`](#image_info) | `result` | 렌더된 이미지를 열어 해상도·채널(AOV)·비트뎁스와 채널별 픽셀 통계를 낸다. |  |
| [`image_preview`](#image_preview) | `result` | 렌더된 이미지를 썸네일로 줄여 그림으로 돌려준다. 눈으로 확인할 때. |  |
| [`compare_images`](#compare_images) | `result` | 두 렌더를 픽셀 단위로 비교한다. 고친 것이 정말 달라졌는지 확인할 때. |  |
| [`image_sequence_report`](#image_sequence_report) | `result` | 렌더한 시퀀스 전체를 훑어 빠진 프레임·검은 프레임·깜빡임을 찾는다. |  |
| [`list_aovs`](#list_aovs) | `result` | 이미지 파일에 실제로 들어 있는 AOV 목록. 렌더 설정이 아니라 결과에서 읽는다. |  |

## 모듈별 상세

### `settings`

렌더 설정을 읽는 툴들.

#### render_settings

```python
render_settings(path: str, settings_prim: str | None = None)
```

LOP 노드가 만든 스테이지의 렌더 설정을 UsdRender 스키마로 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | LOP 노드 경로. 예: /stage/karma_settings |
| `settings_prim` | `str \| None` | `None` | 읽을 RenderSettings 프림 경로. 생략하면 스테이지 기본값. |

#### list_renderers

```python
list_renderers()
```

이 설치본에서 실제로 쓸 수 있는 Hydra 렌더 델리게이트.

### `check`

렌더를 걸기 전에 점검하는 툴.

#### validate_render

```python
validate_render(path: str, settings_prim: str | None = None)
```

렌더를 걸어도 되는 상태인지 스테이지를 훑어 점검한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | LOP 노드 경로, 또는 usdrender_rop / karma ROP 경로. ROP 를 주면 그것이 가리키는 LOP 을 따라간다. |
| `settings_prim` | `str \| None` | `None` | 점검할 RenderSettings 프림. 생략하면 스테이지 기본값. |

### `run`

렌더를 실제로 거는 툴들.

#### start_render

```python
start_render(target: str, output: str | None = None, frame: float | None = None, frame_count: int = 1, frame_inc: float = 1.0, resolution: list[int] | None = None, samples: int | None = None, renderer: str | None = None, settings_prim: str | None = None, snapshot_seconds: float | None = None, threads: int = 0, skip_validation: bool = False)
```

husk 로 백그라운드 렌더를 시작하고 잡 핸들을 돌려준다. Houdini 는 멈추지 않는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | LOP 노드 경로, 또는 렌더할 .usd 파일 경로. |
| `output` | `str \| None` | `None` | 출력 이미지 경로 override. 생략하면 RenderSettings 의 것을 쓴다. $F4 같은 프레임 변수를 그대로 쓸 수 있다. |
| `frame` | `float \| None` | `None` | 시작 프레임. 생략하면 USD 의 startTimeCode. |
| `frame_count` | `int` | `1` | 렌더할 프레임 수. |
| `frame_inc` | `float` | `1.0` | 프레임 증가폭. |
| `resolution` | `list[int] \| None` | `None` | [가로, 세로] override. |
| `samples` | `int \| None` | `None` | 픽셀당 샘플 수. 확인용 렌더는 4~16 이면 충분하다. |
| `renderer` | `str \| None` | `None` | Hydra 델리게이트 이름. `list_renderers` 로 확인한다. |
| `settings_prim` | `str \| None` | `None` | 쓸 RenderSettings 프림 경로. |
| `snapshot_seconds` | `float \| None` | `None` | 이 초마다 부분 이미지를 저장한다. 긴 렌더의 중간 결과를 미리 보고 싶을 때. |
| `threads` | `int` | `0` | 쓸 스레드 수. 0 이면 전부. |
| `skip_validation` | `bool` | `False` | 렌더 전 점검을 건너뛴다. |

#### render_status

```python
render_status(job: str | None = None, with_stats: bool = True)
```

렌더 잡의 진행 상황. 끝났으면 결과 이미지를 실제로 읽어 통계까지 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `job` | `str \| None` | `None` | 잡 id. 생략하면 이 세션의 잡 전부를 요약해서 보여준다. |
| `with_stats` | `bool` | `True` | 끝난 잡의 결과 이미지를 열어 통계를 낼지. 큰 시퀀스에서 응답을 가볍게 하고 싶으면 False. |

#### render_log

```python
render_log(job: str, lines: int = 40)
```

렌더 잡이 내보낸 husk 로그의 끝부분.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `job` | `str` | 필수 | 잡 id. |
| `lines` | `int` | `40` | 돌려줄 줄 수. 최대 200. |

#### cancel_render

```python
cancel_render(job: str)
```

돌고 있는 렌더를 중단한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `job` | `str` | 필수 | 잡 id. |

#### render_rop

```python
render_rop(path: str, frame_range: list[float] | None = None, output_file: str | None = None, ignore_inputs: bool = False, inspect_outputs: bool = True)
```

ROP 을 렌더하고, 나온 파일을 실제로 열어 무엇이 찍혔는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | ROP 노드 경로. 예: /out/karma_beauty, /stage/usdrender_rop1 |
| `frame_range` | `list[float] \| None` | `None` | [시작, 끝] 또는 [시작, 끝, 증가폭]. 생략하면 ROP 설정대로. |
| `output_file` | `str \| None` | `None` | 출력 경로 override. |
| `ignore_inputs` | `bool` | `False` | True 면 이 ROP 만 렌더하고 입력 ROP 은 건너뛴다. |
| `inspect_outputs` | `bool` | `True` | 나온 이미지를 열어 픽셀 통계를 낼지. |

### `result`

렌더 결과 이미지를 읽는 툴들.

#### image_info

```python
image_info(path: str, frame: float | None = None, subimage: int = 0)
```

렌더된 이미지를 열어 해상도·채널(AOV)·비트뎁스와 채널별 픽셀 통계를 낸다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 이미지 경로. $HIP/$F4 같은 Houdini 변수를 써도 된다. |
| `frame` | `float \| None` | `None` | 경로에 $F 가 있을 때 풀어 넣을 프레임. |
| `subimage` | `int` | `0` | 볼 서브이미지(AOV) 번호. |

#### image_preview

```python
image_preview(path: str, width: int = 512, frame: float | None = None, subimage: int = 0, exposure: float = 0.0)
```

렌더된 이미지를 썸네일로 줄여 그림으로 돌려준다. 눈으로 확인할 때.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 이미지 경로. |
| `width` | `int` | `512` | 썸네일 가로 픽셀. 세로는 비율대로. |
| `frame` | `float \| None` | `None` | 경로에 $F 가 있을 때 풀어 넣을 프레임. |
| `subimage` | `int` | `0` | 볼 서브이미지(AOV) 번호. |
| `exposure` | `float` | `0.0` | 스톱 단위 노출 보정. 어두운 렌더를 볼 때 +2 처럼. |

#### compare_images

```python
compare_images(a: str, b: str, frame: float | None = None, fail_threshold: float = 0.01, warn_threshold: float = 0.001)
```

두 렌더를 픽셀 단위로 비교한다. 고친 것이 정말 달라졌는지 확인할 때.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `a` | `str` | 필수 | 첫 번째 이미지 경로. |
| `b` | `str` | 필수 | 두 번째 이미지 경로. |
| `frame` | `float \| None` | `None` | 두 경로에 $F 가 있을 때 풀어 넣을 프레임. |
| `fail_threshold` | `float` | `0.01` | 이 값보다 큰 차이를 '실패 픽셀'로 센다. |
| `warn_threshold` | `float` | `0.001` | 이 값보다 큰 차이를 '경고 픽셀'로 센다. |

#### image_sequence_report

```python
image_sequence_report(path: str, start: float, end: float, inc: float = 1.0)
```

렌더한 시퀀스 전체를 훑어 빠진 프레임·검은 프레임·깜빡임을 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | $F4 같은 프레임 변수가 든 경로. 예: $HIP/render/beauty.$F4.exr |
| `start` | `float` | 필수 | 시작 프레임. |
| `end` | `float` | 필수 | 끝 프레임. |
| `inc` | `float` | `1.0` | 프레임 증가폭. |

#### list_aovs

```python
list_aovs(path: str, frame: float | None = None)
```

이미지 파일에 실제로 들어 있는 AOV 목록. 렌더 설정이 아니라 결과에서 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 이미지 경로. |
| `frame` | `float \| None` | `None` | 경로에 $F 가 있을 때 풀어 넣을 프레임. |
