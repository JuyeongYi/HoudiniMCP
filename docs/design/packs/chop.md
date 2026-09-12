# houdini_mcp_chop — CHOP·채널·애니메이션 데이터

> 먼저 [README.md](README.md) 를 읽는다.

## 무엇을 담나

채널 데이터를 만들고, 필터하고, **실제 값을 분석해서** 보는 것. 파라미터에 키를
찍는 기본 동작은 이미 `houdini_mcp_base` 의 `anim` 모듈에 있다
(`set_keyframe`, `get_keyframes`, `delete_keyframes`, `set_expression`,
`list_animated_parms`). 여기는 채널을 **데이터로** 다루는 것을 담는다.

경계는 이렇게 긋는다.

| 하려는 것 | 어디 |
|---|---|
| 파라미터 하나에 키 하나 찍기·읽기·지우기 | base `anim` |
| 파라미터에 식 걸기 | base `anim` |
| 프레임 범위·FPS | base `scene.set_frame_range` |
| 채널 **값의 분포·튐·정지·루프**를 판정 | 이 팩 |
| CHOP 네트워크를 만들고 필터를 걸기 | 이 팩 |
| CHOP 출력을 파라미터 키로 굽기, 그 반대 | 이 팩 |
| 채널을 Houdini 포맷 파일로 주고받기 | 이 팩 |
| 오디오를 읽어 파형을 분석 | 이 팩 |

기존 구현이 가진 것: fx CHOPs 4 (`create_chop_node`, `get_chop_data`,
`list_chop_channels`, `export_chop_to_parm`), dcc chops 6
(`create_chop_network`, `apply_filter`, `create_audio_driven`,
`create_motionclip`, `export_to_keyframes`, `get_channel_info`),
dcc animation 12 (`bake_channels`, `export_channels`, `import_channels`,
`get_timeline`, `set_timeline`, `cache_simulation`, `validate_loop_contract`).

## 기존 구현이 한 방식과 그 한계

- **샘플을 하나씩 판다.** `for i in range(n): track.evalAtSampleIndex(i)`.
  실측: 240샘플 트랙 하나에 파이썬 루프 **5.8ms**, `allSamples()` **0.016ms**.
  360배 차이가 나고, 샘플이 수천이면 그대로 비례한다.
- **모션을 분석하지 않는다.** 값 목록만 준다. 이 커브가 튀는지, 멈춰 있는지,
  루프가 맞는지 모델이 숫자를 눈으로 훑어야 한다.

---

## 실측 결과 (Houdini 22.0.368, 2026-09-13)

아래는 전부 hython 으로 확인한 것이다. 추측이 아니다.

### 1. `hou.Track.allSamples()` 는 **파이썬 float 튜플**이다

```
allSamples(self) -> tuple of double
```

`geo.pointFloatAttribValuesAsString` 같은 **바이트 버퍼 경로는 없다.**
`numpy.frombuffer` 로 꽂을 수 없고, `numpy.asarray(tuple)` 로 파이썬 객체를
거쳐 복사해야 한다. 그래도 이것이 유일하고 가장 빠른 벌크 경로다.

| 방법 | 240샘플 소요 |
|---|---|
| `[t.evalAtSample(i) for i in range(n)]` | 5.817 ms |
| `t.allSamples()` | 0.016 ms |
| `numpy.asarray(t.allSamples(), numpy.float32)` | 0.057 ms |

범위 평가도 전부 튜플을 준다. **끝값을 포함한다** — `evalAtSampleRange(0, 9)`
는 10개를 준다.

```
allSamples()                    -> tuple of double
evalAtSampleRange(start, end)   -> tuple of double   (양끝 포함)
evalAtFrameRange(start, end)    -> tuple of double   (양끝 포함)
evalAtTimeRange(start, end)     -> tuple of double
numSamples() -> int
```

`evalAtSampleIndex` 는 **deprecated** 다 (`evalAtSample` 로 대체). 기존 구현
다섯이 전부 이것을 쓴다.

### 2. 쿡되지 않은 CHOP 의 `tracks()`

시그니처에 `cook` 인자가 있다.

```
tracks(output_index=0, cook=True) -> tuple of hou.Track
track(track_name, output_index=0, cook=True) -> hou.Track
```

- `tracks()` (기본, cook=True): 쿡이 실패하면 `hou.OperationFailed` 를 던진다.
  노드의 `errors()` 에 이유가 남는다.
- `tracks(cook=False)`: 쿡하지 않고 캐시만 본다. 한 번도 쿡되지 않았으면
  **빈 튜플** `()` 을 준다. 예외는 없다.

그래서 "쿡 안 된 노드에서 뭐가 나오나"의 답은 **빈 튜플 또는 예외**이고, 이 팩은
언제나 쿡을 강제한 뒤 실패를 노드 에러와 함께 되돌려준다.

### 3. 채널 파일 — `.chan` 과 `.clip` 은 **다른 경로다**

문서 초안이 이 둘을 같은 것처럼 적어 두었는데 틀렸다. 실측하면 이렇다.

| 포맷 | 무엇의 파일인가 | 쓰기 | 읽기 |
|---|---|---|---|
| `.clip` `.bclip` `.bclip.sc` | **CHOP 클립** | `hou.ChopNode.saveClip`, `hou.Clip.saveToFile`, `rop_channel` ROP | `hou.Clip.loadFromFile`, File CHOP |
| `.chan` `.bchan` | **파라미터 채널** (raw 컬럼) | hscript `chwrite` | hscript `chread`, File CHOP |

교차는 통하지 않는다. 실측한 실패들:

- `chopnode.saveClip("x.chan")` → `OperationFailed: Failed to save clip.`
- `hou.Clip.saveToFile("x.bchan")` → 같은 실패
- `rop_channel` 의 `chopoutput` 에 `.chan` → `Failed to save output to file`
- `hscript chwrite ... x.clip` → `Unrecognized channel extension`

File CHOP 은 **넷 다 읽는다.** `.chan`/`.bchan` 을 읽으면 채널 이름이 파일에
없으므로 `chan0`, `chan1`... 로 붙는다. `.clip`/`.bclip` 은 이름을 보존한다.

hscript 인자 순서에 주의한다 — 파일명이 **뒤**다.

```
chwrite [-f <start> <end>] <channel_patterns...> <file>
chread  [-f <start> <end>] <parm_patterns...> <file>
```

공백이 든 경로는 큰따옴표로 감싸면 통한다(실측).

### 4. CHOP → 파라미터는 두 경로가 있고, 둘 다 쓴다

**(a) 익스포트 플래그 — 라이브 연결.** `chopnode.setExportFlag(True)` 를 켜면
채널 이름이 가리키는 파라미터를 CHOP 이 계속 몬다. 이름 규칙을 실측했다.

| 채널 이름 | 결과 |
|---|---|
| `tx` | **안 먹는다** (어느 노드인지 모른다) |
| `target_box:tx` | 먹는다 |
| `target_box/tx` | 먹는다 |
| `/obj/target_box/tx` | 먹는다 |

**(b) 키프레임으로 굽기 — 끊어진 사본.** 트랙 샘플을 읽어
`hou.Parm.setKeyframes(list)` 로 한 번에 건다. HOM 문서가 "여러 번
`setKeyframe` 하는 것보다 효율적"이라고 명시한다. 샘플 인덱스 → 프레임은
`chopnode.samplesToFrame(i)` 로 얻는다(실측: 샘플 0 → 프레임 1.0).

### 5. 파라미터 → CHOP 은 `hou.Parm.appendClip`

Channel CHOP 의 `name<i>` 를 손으로 채워 넣으면 **값이 전부 0 으로 나온다**
(실측). 이름만으로는 애니메이션이 따라오지 않는다. 올바른 경로는

```
parm.appendClip(channel_chop, apply_immediately, current_value_only)
```

이고, SideFX 자신의 `choptoolutils.createClipForParmObjects` 도 이것을 쓴다.
Channel CHOP 은 만들자마자 기본 채널 `chan1` 하나를 갖고 있으므로, 붙이기 전에
`numchannels` 를 0 으로 내려 지운다.

### 6. `choptoolutils` — 절반만 쓸 수 있다

| 함수 | 시그니처 | 쓸 수 있나 |
|---|---|---|
| `genericTool(scriptargs, ...)` | 셸프 `scriptargs` | ✗ 뷰포트 컨텍스트 |
| `parmFilterEffect(kwargs, ...)` | 셸프 `kwargs` | ✗ |
| `modifyObjectTool`, `visualizeParmEffect` | 셸프 | ✗ |
| `createClipForParmObjects(parms, prefix, parent=None)` | 순수 | △ 헤드리스에서 **돈다** |
| `groupTracksByChop`, `scopeTracks`, `adjustRate` | 순수 | ○ |

`createClipForParmObjects` 는 헤드리스에서 실제로 동작하는 것을 확인했지만,
노드를 오브젝트의 `motion_effects` 네트워크에 강제로 놓고 이름도 스스로 정한다.
모델이 배치를 정할 수 없어서 이 팩은 쓰지 않고, 그 안의 `appendClip` 경로만
직접 쓴다.

### 7. 오디오

File CHOP 이 `.wav` 를 그대로 읽는다(실측: 44.1kHz 스테레오 → 트랙 2개
`chan0`/`chan1`, 44100 샘플, `sampleRate()` 가 44100.0). 채널 하나당 트랙
하나이고 이름은 파일에 없으면 `chan<i>` 다. `rateoption` 은
`nochange`/`override`/`resample`, `nameoption` 은 `infile`/`new`/`filename`.

`isAudioFlagSet()` 는 오디오를 읽어도 자동으로 켜지지 않는다 — 씬의 오디오
소스로 쓰려면 `setAudioFlag(True)` 를 따로 켠다.

파이썬 3.13 에서 `aifc` 가 표준 라이브러리에서 빠져서 aiff 는 합성 파일을 만들
수단이 없어 검증하지 못했다. wav 만 확인된 것으로 적어 둔다.

### 8. 필터 CHOP 들의 실제 파라미터 (실측)

| 노드 | 파라미터 |
|---|---|
| `lag` | `lagmethod`, `lag1`, `lag2`, `overshoot1/2`, `clamp`, `slope1/2`, `aclamp`, `accel1/2` |
| `filter` (smooth) | `type`, `effect`, `width`, `spike`, `passes` |
| `limit` | `type`, `min`, `max`, `positive`, `norm`, `quantvalue`, `vstep`, `voffset` |
| `shift` | `reference`, `relative`, `start`, `end`, `scroll` |
| `resample` | `method`, `rate`, `relative`, `start`, `end`, `interp` |
| `spring` | `springk`, `mass`, `dampingk`, `method`, `initpos`, `initspeed` |
| `jiggle` | `stiff`, `damp`, `limit`, `flex`, `mult1/2/3`, `reference` |

"smooth" 라는 CHOP 은 없다. Filter CHOP 의 `type` 이 그 역할을 한다.

### 9. 소스 CHOP 두 개의 함정 (검증하다 걸린 것)

- **Constant CHOP 은 기본이 샘플 하나다.** `single` 파라미터가 켜져 있어
  `tracks()[0].numSamples()` 가 1 이다. 전 구간을 채우려면 `single` 을 끈다.
- **Wave CHOP 의 `wavetype` 메뉴**는 `const, sin, normal, tri, ramp, square,
  pulse, expr` 순서다. 기본값 0 은 **`const`** 라 값이 변하지 않는다 — 사인은
  1 이다. 0 인 채로 루프 판정을 돌리면 상수가 통과해 시험이 되지 않는다.
- Houdini 의 `tri` 는 `0 -> 1 -> -1 -> 0` 이라 값도 기울기도 진짜로 이어진다.
  값은 이어지는데 기울기가 끊기는 경우를 만들려면 `ramp`(톱니)를 쓴다.

---

## 우리가 쓰는 경로

### 값이 아니라 **분석 결과**를 돌려준다

이 팩의 존재 이유다. 샘플 5,000개를 보내는 대신 numpy 로 압축해서 보낸다.

- min / max / mean / std, 처음·끝 값, 전체 변화량
- **루프 가능 여부** — 첫·끝 값 차이와 1차 미분 차이를 값 범위로 정규화해 판정
- **튐 감지** — 인접 샘플 차이의 MAD 기반 이상치. MAD 가 정확히 0 이면 평균
  편차로 떨어지고, 그 위에 **신호 크기의 1e-9 라는 바닥**을 깐다. 바닥이
  없으면 선형에 가까운 채널에서 MAD 가 1e-17 까지 내려가 부동소수점 마지막
  자리 오차가 전부 튐으로 잡힌다 — 검증에서 실제로 겪은 오검출이다
- **정지 구간** — 변화가 허용치 이하인 연속 프레임 범위
- NaN / inf 개수
- 다운샘플한 스파크라인 배열 (기본 48점)

`validate_loop_contract` 를 기존처럼 "속성 비교"가 아니라 **실제 값으로**
판정한다.

---

## 만든 툴

| 모듈 | 툴 |
|---|---|
| `build` | `create_chop_network`, `create_chop_node`, `apply_chop_filter` |
| `data` | `list_channels`, `channel_stats`, `channel_samples` |
| `check` | `check_loop`, `find_spikes` |
| `transfer` | `export_to_keyframes`, `import_from_parms`, `set_chop_export` |
| `files` | `export_channels`, `import_channels`, `export_parm_channels`, `import_parm_channels` |
| `bake` | `bake_channels` |
| `audio` | `load_audio` |

### 일부러 만들지 않은 것

| 무엇 | 왜 |
|---|---|
| `get_timeline` / `set_timeline` | base `scene.set_frame_range` 와 중복 |
| `cache_simulation` | base `cache` 모듈의 `write_cache`/`cache_status`/`list_caches` 와 중복 |
| `create_motionclip` | KineFX 영역. `houdini_mcp_rig` 가 `apex` 로 다룬다. **아래 경계 참고** |
| `get_chop_data` (원본 샘플 덤프) | 제3원칙 위반. `channel_stats` + `channel_samples`(상한 있음) + `export_channels`(파일) 로 가른다 |

### `houdini_mcp_rig` 와의 경계

`create_motionclip` 을 여기 두지 않는다. MotionClip 은 KineFX 의 스켈레톤
애니메이션 표현이고 SOP 컨텍스트에서 `motionclip` 계열 노드와 `apex` API 로
다룬다. CHOP 의 트랙(스칼라 시계열)과 자료 구조가 다르다.

- **이 팩**: `hou.Track` 으로 열리는 스칼라 채널. CHOP 네트워크, 클립 파일,
  파라미터 키.
- **`houdini_mcp_rig`**: 스켈레톤·조인트·MotionClip·APEX 그래프. 포즈를
  다루는 것은 전부 저쪽이다.

겹치는 지점은 하나뿐이다 — 리그 채널을 **시계열로 분석**하고 싶을 때. 그때는
rig 팩이 채널을 CHOP 으로 뽑고, 분석은 이 팩의 `channel_stats` 를 쓴다.

---

## 검증

`tests/chop/` 에 회귀 테스트가 있다. `tests/sop` 와 같은 방식으로 hython
서브프로세스를 띄우고, **등록된 툴이 하나도 빠짐없이 호출됐는지**를
`uncalled` 로 확인한다.

분석이 맞는지는 **정답을 아는 신호**로 못 박는다.

- `wave` CHOP (`wavetype` 1 = sin, 한 주기) → `check_loop` 가 루프 **가능** 판정
- 톱니파(`wavetype` 4) → 첫·끝 값은 같지만 기울기가 끊기므로 **불가** 판정.
  값만 비교하는 판정이라면 통과시켜 버리는 경우다
- 난수 채널 → **불가** 판정
- 프레임 60 에 일부러 튐을 넣은 채널 → `find_spikes` 가 **프레임 60·61 만**
  집는다. 같은 채널의 선형 램프 구간과 매끄러운 사인 채널에서는 하나도 잡지
  않는다 (부동소수점 오차 오검출이 실제로 있었고, 기준에 바닥을 깔아 고쳤다)
- `constant` CHOP(`single` 끔) → `channel_stats` 의 정지 구간이 전 구간
- `lag` 필터 전후 → 표준편차가 줄어든다. `limit` 전후 → 범위가 잘린다
- 키로 굽기·`.bclip`·`.chan` 왕복 → 값이 원본과 1e-6 안에서 같다

```
python -m pytest tests/chop -q
```
