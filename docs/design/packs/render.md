# houdini_mcp_render — 렌더·Karma·Husk 전문

> 먼저 [README.md](README.md) 를 읽는다.
>
> **구현 완료.** 아래는 계획이 아니라 2026-09-13 에 Houdini 22.0.368 로 실측하고
> 구현한 결과다. 계획과 달랐던 것은 "실측에서 달랐던 것" 절에 모았다.

## 무엇을 담나

렌더를 걸고, 진행 상황을 알고, **결과 이미지를 실제로 확인하는** 것.

기존 구현이 가진 것: dcc render 16 + husk 6 + karma 4 + texture-bake 5,
fx `setup_render` / `capture_viewport`. 합쳐서 약 30개(중복 제거 후 ~24).

## 기존 구현이 한 방식과 그 한계

- **렌더를 걸고 끝난다.** 결과 이미지를 열어 보지 않는다. 새까만 프레임이
  나와도 `{"status": "done"}` 을 돌려준다.
- **잡 관리를 자체 구현한다.** `start_render_job` / `get_render_job` /
  `cancel_render_job` 을 딕셔너리에 담아 돌린다. 프로세스가 죽으면 잃는다.
- **Karma 설정을 파라미터 이름으로 하드코딩한다.** 22.0 에서 바뀌면 조용히
  깨진다.

## 우리가 쓴 경로

### 1. 결과를 반드시 확인한다 — OpenImageIO 2.5.18.0

이 팩의 존재 이유다. **렌더가 끝나면 이미지를 읽어서 무엇이 나왔는지
돌려준다.** 기존 구현 다섯 중 렌더 결과를 읽는 곳은 한 곳도 없다.

```python
import OpenImageIO as oiio
buf = oiio.ImageBuf(str(path), subimage, 0)
buf.read()                                       # 게으르게 읽으므로 명시적으로
stats = oiio.ImageBufAlgo.computePixelStats(buf)  # PixelStats
```

`PixelStats` 의 필드는 **전부 채널 수만큼의 리스트**다(실측):
`min` `max` `avg` `stddev` `sum` `sum2` `nancount` `infcount` `finitecount`.

돌려주는 것: 해상도, 채널·AOV 목록, 비트뎁스, 채널별 min/max/평균/표준편차,
NaN·Inf 개수, husk 가 박아 넣은 메타데이터(`renderTime_s`, `husk:command`),
그리고 그것을 사람 말로 옮긴 `diagnosis`.

진단은 전부 실제 이미지로 검증했다:

| 이미지 | 진단 |
|---|---|
| RGBA 전부 0 | "색 채널이 전부 0 입니다 - 완전히 새까만 이미지입니다" + 알파 0 + 단색 |
| NaN·Inf 섞임 | "NaN 이 있습니다 (R 채널에 1개)" / "무한대 값이 있습니다" |
| 색은 있고 알파만 0 | "알파가 전부 0 입니다 - 카메라에 아무것도 안 잡혔다" |
| 평균 1e-5 | "거의 검습니다 (색 평균 0.000010)" |

### 2. husk 는 실행 파일이다 (`$HFS/bin/husk[.exe]`)

`hou.text.expandString("$HFS")` + `pathlib` 로 찾는다. 하드코딩하지 않는다.

실제로 쓴 플래그(`husk --help` 로 실측):

| 플래그 | 쓰임 |
|---|---|
| `-Va2` | **ALF_PROGRESS 를 stdout 으로 내보낸다.** 진행률의 출처 |
| `--no-mplay` | 헤드리스 필수. 없으면 MPlay 를 띄우려 든다 |
| `--make-output-path` | 출력 디렉토리를 만들어 준다 |
| `-f` / `-n` / `-i` | 시작 프레임 / 프레임 수 / 증가폭 |
| `--res W H` | 해상도 (**인자 두 개**) |
| `-p` | 픽셀당 샘플 |
| `-R` | Hydra 델리게이트 |
| `-s` | 쓸 RenderSettings 프림 |
| `--snapshot` | 이 초마다 부분 이미지 저장 |
| `--list-renderers` | 델리게이트 목록. **stdout 이 아니라 stderr 로 나온다** |

stdout 을 파싱해 얻는 것: `ALF_PROGRESS n%` → 진행률, `Saved Image: <경로>` →
실제로 쓴 파일. 자체 잡 딕셔너리를 만들되 **진행률·출력 경로는 husk 가
말해 주는 것을 쓴다.** 프로세스는 `atexit` 으로 정리해 Houdini 가 닫힐 때
자식이 남지 않게 한다.

### 3. 렌더 설정은 `UsdRender` 스키마로

파라미터 이름을 하드코딩하지 않는다.

```python
from pxr import UsdRender
settings = UsdRender.Settings.GetStageRenderSettings(stage)   # 스테이지 기본값
settings.GetResolutionAttr().Get()
settings.GetCameraRel().GetTargets()
settings.GetProductsRel().GetTargets()      # → UsdRender.Product → OrderedVars(AOV)
```

델리게이트 전용 설정(`karma:global:samplesperpixel` 등)은 스키마 밖이다.
이름을 미리 알 수 없으므로 **`GetSchemaAttributeNames` 에 없으면서 값이 찍힌
어트리뷰트**를 그대로 긁어 `renderer_settings` 로 돌려준다. 22.x 에서 이름이
바뀌어도 안 깨진다.

### 4. 렌더 전에 검증한다

렌더는 비싸다. `validate_render` 가 걸기 전에 확인하고, `start_render` 는
기본적으로 이 점검을 먼저 돌려 `errors` 가 있으면 **렌더를 시작하지 않는다**
(`skip_validation=True` 로 끌 수 있다).

보는 것: RenderSettings 존재 / 카메라가 걸렸고 실제로 `UsdGeom.Camera` 인가 /
해상도 / 라이트(`UsdLux.LightAPI`) 유무 / 렌더할 `UsdGeom.Gprim` 유무 /
머티리얼 바인딩(`UsdShade.MaterialBindingAPI.ComputeBoundMaterial`) /
출력 경로에 쓸 수 있는가 / RenderProduct·RenderVar 존재 / 프레임 범위.

## 만든 툴 (13개)

| 모듈 | 툴 |
|---|---|
| `settings` | `render_settings` (UsdRender 스키마로 설정+Product+AOV 전부), `list_renderers` |
| `check` | `validate_render` — LOP 도 ROP 도 받는다 |
| `run` | `start_render` (husk 백그라운드), `render_status`, `render_log`, `cancel_render`, `render_rop` (블로킹) |
| `result` | `image_info`, `image_preview`, `compare_images`, `image_sequence_report`, `list_aovs` |

헬퍼는 `_common` (hou·경로), `_usdrender` (USD 질의·점검), `_image` (OIIO).
`TOOL_MODULES` 에는 툴이 있는 넷만 적는다.

## 실측에서 달랐던 것

### ROP 을 비동기로 거는 길은 없다

`hou.RopNode.render()` 는 블로킹이다. 실측으로 확인했다.

- `render(frame_range, res, output_file, output_format, to_flipbook, quality,
  ignore_inputs, method, ignore_bypass_flags, ignore_lock_flags, verbose,
  output_progress)` — 끝날 때까지 돌아오지 않는다.
- `addRenderEventCallback` 은 있지만 `hou.ropRenderEventType` 은
  PreFrame/PostFrame/PreRender/PostRender/PostWrite 뿐이고, 콜백도 렌더
  스레드 안에서 돈다. **진행률을 물을 수 있는 API 는 없다.**
- ROP 의 `executebackground` 파라미터는 콜백이
  `kwargs['node'].hm().renderToDiskBackground()` 다. hip 파일을 임시로 저장해
  hbatch 를 띄우는 것이라 핸들을 돌려주지 않고 씬 파일을 건드린다. 쓰지 않는다.

그래서 비동기는 **husk 프로세스로만** 간다. `start_render` 는 LOP 스테이지를
`stage.Flatten()` → `layer.Export()` 로 임시 USD 에 내보내고 husk 를 띄운다.
`render_rop` 은 블로킹이라는 사실을 docstring 첫머리에 적는다.

**LOP 을 줄 때의 한계**: 스테이지는 지금 Houdini 프레임에서 쿡된 상태로
내보내진다. SOP Import 처럼 프레임마다 다시 쿡해야 하는 네트워크는 여러
프레임을 걸어도 첫 프레임 데이터로 렌더된다. 시퀀스는 USD ROP 으로 범위를
미리 내보낸 뒤 그 `.usd` 를 `target` 으로 준다.

### husk 가 "Saved Image" 를 찍고도 파일이 없을 수 있다

지오메트리가 없는 스테이지에서 husk 가 종료 코드 0 으로 끝나고
`Saved Image: ...` 를 찍었는데 파일이 없는 경우를 실측했다(같은 씬에서 파일이
생기는 경우도 있었다). `render_status` 는 이 경우 `missing: true` 와 함께
"husk 는 끝났는데 파일이 없습니다" 를 돌려준다.

### ROP 의 출력 파라미터에는 공통 규약이 없다

실측한 것: karma→`picture`, geometry→`sopoutput`,
usdrender→`outputimage`(+내부용 `lopoutput`), alembic→`filename`,
comp→`copoutput`, baketexture::3.0→`vm_uvoutputpicture1`.
우선순위 목록을 두고 **값이 있는 첫 번째 것만** 쓴다. 뒤쪽(`lopoutput`)은
usdrender_rop 이 husk 에 넘기는 임시 USD 라 결과가 아니다.

### 초안에서 뺀 툴과 이유

| 초안 | 어떻게 됐나 |
|---|---|
| `set_render_settings` | **안 만든다.** 노드 파라미터를 거는 것은 base 의 `set_parms` 가 이미 한다. 무엇을 걸어야 하는지는 `render_settings` 가 보여준다 |
| `configure_aovs` | 같은 이유. `rendervar` LOP 을 만드는 것은 base `create_node` |
| `list_render_products` | `render_settings` 가 Product 와 AOV 를 함께 돌려주므로 합쳤다 |
| `image_info` + `image_stats` | 합쳤다. 통계 없는 이미지 정보는 쓸모가 적다 |
| `render_with_husk` | `start_render` 가 `.usd` 파일 경로도 받으므로 하나로 합쳤다 |
| `flipbook`, `flipbook_status` | **안 만든다.** `hou.SceneViewer.flipbook` 은 UI 전용이라 hython 에서 검증할 수 없다. base 의 `viewport_snapshot` 이 같은 경로로 단일 프레임을 이미 찍는다. 시퀀스가 필요해지면 그때 base 의 viewport 모듈을 넓히는 편이 맞다 |
| `bake_textures`, `bake_ao`, `transfer_maps` | **안 만든다.** 22.0 의 베이크는 `baketexture::3.0` ROP 과 `karmatexturebaker` LOP 둘 다 ROP/LOP 이라, `render_rop` 으로 그대로 돌릴 수 있고 출력 파라미터(`vm_uvoutputpicture1`)도 목록에 넣어 두었다. 전용 툴은 UV·머티리얼이 갖춰진 실제 에셋 없이는 검증할 수 없어 미뤘다 |

### 초안에 없던 툴

| 툴 | 왜 |
|---|---|
| `list_renderers` | 델리게이트 이름을 추측하지 않기 위해. `husk --list-renderers` 를 그대로 |
| `render_log` | husk 가 실패했을 때 원인이 로그에만 있다 |
| `image_sequence_report` | 시퀀스를 한 번에 훑어 빠진 프레임·검은 프레임·깜빡임을 찾는다. 기존 구현 다섯 중 어디에도 없다 |
| `list_aovs` | 설정이 아니라 **결과 파일에 실제로 들어간** AOV. 둘이 다르면 RenderVar 가 전달되지 않은 것 |

## 검증

전부 hython 에서 실제로 호출했다.

```
빈 스테이지 → validate_render → "지오메트리가 없습니다" 로 start_render 거부
라이트 없음 → validate_render 경고 → domelight 추가 → 통과
start_render (샘플 4, 192x144) → render_status 폴링 → 4.3초에 finished
  → 채널 평균 0.344 / NaN 0 / "특이사항 없습니다"
잘못된 델리게이트 → state=failed, exit_code=1, log_tail 에 원인
무거운 렌더 → cancel_render → state=cancelled, 진행률 1%
render_rop (usdrender_rop) → 3.5초 블로킹 → 결과 EXR 통계까지
render_rop (geometry ROP) → .bgeo.sc 는 "not_an_image" 로 구분
합성 이미지 4종으로 진단 로직 전수 확인 (검정/NaN/알파0/거의검정)
image_sequence_report → 6프레임 중 빠진 1, 검은 1, 깜빡임 1곳 정확히 검출
```

`python -m pytest tests/package_order -q` → 16 passed, 9 skipped (기준선 유지).
