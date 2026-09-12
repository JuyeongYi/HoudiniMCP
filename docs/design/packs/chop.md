# houdini_mcp_chop — CHOP·채널·애니메이션 데이터

> 먼저 [README.md](README.md) 를 읽는다.

## 무엇을 담나

채널 데이터를 만들고, 필터하고, **실제 값을 보는** 것. 파라미터에 키를 찍는
기본 동작은 이미 `houdini_mcp_base` 의 `anim` 모듈에 있다. 여기는 채널을
**데이터로** 다루는 것을 담는다.

기존 구현이 가진 것: fx CHOPs 4 (`create_chop_node`, `get_chop_data`,
`list_chop_channels`, `export_chop_to_parm`), dcc chops 6
(`create_chop_network`, `apply_filter`, `create_audio_driven`,
`create_motionclip`, `export_to_keyframes`, `get_channel_info`),
dcc animation 12 (`bake_channels`, `export_channels`, `import_channels`,
`get_timeline`, `set_timeline`, `cache_simulation`, `validate_loop_contract`).

## 기존 구현이 한 방식과 그 한계

- **샘플을 하나씩 판다.** `for i in range(n): track.evalAtSampleIndex(i)`.
  샘플 수천 개면 느리고, 결과를 그대로 JSON 에 실어 컨텍스트를 태운다.
- **모션을 분석하지 않는다.** 값 목록만 준다. 이 커브가 튀는지, 멈춰 있는지,
  루프가 맞는지 모델이 숫자를 눈으로 훑어야 한다.

## 우리가 쓸 경로

### 1. 범위 평가 + numpy (실측 확인)

`hou.Track` 이 **범위를 한 번에** 준다:

```
allSamples / evalAtSampleRange / evalAtFrameRange / evalAtTimeRange
numSamples / eval / evalAtFrame / evalAtSample / evalAtTime
chopNode / clip / name / color
```

```python
import numpy as np
samples = np.asarray(track.allSamples(), dtype=np.float32)
```

루프를 돌지 않는다. numpy 2.3.2 가 번들돼 있다.

### 2. 값이 아니라 **분석 결과**를 돌려준다

이 팩의 존재 이유다. 샘플 5,000개를 보내는 대신:

- min / max / mean / std
- 처음·끝 값, 전체 변화량
- **루프 가능 여부** — 첫 샘플과 마지막 샘플의 차이, 1차 미분의 차이
- **튐 감지** — 인접 샘플 차이의 이상치 (numpy 로 한 줄)
- **정지 구간** — 변화가 없는 프레임 범위
- NaN / inf 유무
- 다운샘플한 스파크라인용 배열 (예: 64점)

`validate_loop_contract` 를 기존처럼 "속성 비교"가 아니라 **실제 값으로**
판정한다.

### 3. 채널을 파일로 주고받을 때는 Houdini 포맷을 쓴다

`.chan` / `.bchan` / `.clip` / `.bclip` 은 Houdini 와 다른 DCC 가 읽는다.
자체 JSON 포맷을 만들지 않는다. `hou.Clip` / CHOP File 노드의 경로를 확인한다.

### 4. 오디오

`create_audio_driven` 은 File CHOP 으로 오디오를 읽는다. 22.0 이 읽는 포맷과
샘플레이트 처리를 확인하고, **읽은 뒤 실제 길이·샘플레이트·채널 수를
돌려준다**.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `build` | `create_chop_network`, `create_chop_node`, `apply_chop_filter` (lag/smooth/limit/shift) |
| `data` | `list_channels` (이름·샘플 수·범위), `channel_stats` (위의 분석 전부), `channel_samples` (다운샘플 또는 파일로) |
| `transfer` | `export_to_keyframes` (CHOP → 파라미터 키), `import_from_parms`, `export_channels` (.chan/.clip), `import_channels` |
| `bake` | `bake_channels` — 식을 키로 굽는다. 굽기 전후 값이 같은지 검증 |
| `check` | `check_loop` (실제 값 기반), `find_spikes` |
| `audio` | `load_audio` — 길이·샘플레이트·채널 반환 |
| `motion` | `create_motionclip` — KineFX 와 겹친다. `houdini_mcp_rig` 와 경계를 정할 것 |

`get_timeline` / `set_timeline` 은 **base 의 `scene.set_frame_range` 와 중복**이다.
만들지 않는다.

## 먼저 확인할 것

1. `hou.Track.allSamples()` 반환 타입 — tuple 인지, numpy 로 바로 갈 수 있는지
2. `hou.Clip` API 와 `.chan` / `.bclip` 저장·로드 경로
3. CHOP → 파라미터 익스포트의 정확한 방법 (export 플래그? Channel 노드?)
4. 22.0 의 오디오 파일 지원 포맷
5. `hou.ChopNode` 가 쿡되지 않았을 때 `tracks()` 가 무엇을 주는지

## 검증

```
CHOP 네트워크 → noise CHOP → list_channels → 3채널 확인
→ channel_stats → std 가 0 이 아닌가, 스파크라인이 그럴듯한가
→ lag 필터 → std 가 줄었는가
→ export_to_keyframes → 파라미터에 키가 생겼는가, 값이 맞는가
→ check_loop → 루프 아님 판정
```
