# houdini_mcp_render — 렌더·Karma·Husk 전문

> 먼저 [README.md](README.md) 를 읽는다.

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

## 우리가 쓸 경로

### 1. 결과를 반드시 확인한다 — OpenImageIO (2.5.18.0, 실측 확인)

이 팩의 존재 이유다. **렌더가 끝나면 이미지를 읽어서 무엇이 나왔는지
돌려준다.**

```python
import OpenImageIO as oiio
inp = oiio.ImageInput.open(str(path))
spec = inp.spec()                    # 해상도, 채널(AOV 목록), 비트뎁스
stats = oiio.ImageBufAlgo.computePixelStats(oiio.ImageBuf(str(path)))
```

돌려줄 것:

- 해상도, 채널·AOV 목록, 비트뎁스
- 채널별 min/max/mean — **새까만지, 날아갔는지, NaN 이 있는지 즉시 안다**
- 알파가 전부 0 이면 경고 (아무것도 안 찍혔다는 뜻)
- 썸네일을 작게 줄여 이미지로 반환 (`houdini_mcp.image_result` 가 이미 있다)

기존 구현 다섯 중 렌더 결과를 읽는 곳은 **한 곳도 없다.**

### 2. husk 는 실행 파일이다 (실측 확인: `$HFS/bin/husk.exe`)

프로세스로 띄우고 `subprocess.Popen` 으로 관리한다. 자체 잡 딕셔너리를 만들기
전에, husk 가 제공하는 것부터 본다 — 진행률을 stdout 으로 내보내고,
`--snapshot` 으로 중간 결과를 쓴다.

```bash
"$HFS/bin/husk" --help     # 22.0 의 실제 플래그를 먼저 확인한다
```

**경로는 `hou.text.expandString("$HFS")` + `pathlib` 로 얻는다.** 하드코딩 금지.

렌더는 오래 걸린다. MCP 툴이 블로킹하면 안 된다. 백그라운드로 띄우고 핸들을
돌려준 뒤 `render_status` 로 폴링하는 구조로 간다. 프로세스 핸들은 모듈
전역에 두되, **Houdini 가 죽으면 자식도 정리되도록** 한다.

### 3. 렌더 설정은 `UsdRender` 스키마로 (실측 확인: `pxr.UsdRender` 있다)

파라미터 이름을 하드코딩하지 않는다.

```python
from pxr import UsdRender
settings = UsdRender.Settings(prim)
settings.GetResolutionAttr().Get()
settings.GetProductsRel().GetTargets()
```

Karma 는 USD 렌더 delegate 다. 설정을 LOP 파라미터가 아니라 스테이지의
RenderSettings 프림에서 읽고 쓴다. 그러면 22.x 에서 파라미터가 바뀌어도 안 깨진다.

### 4. 렌더 전에 검증한다

렌더는 비싸다. 걸기 전에 확인한다 — 이게 `validate_karma_stage` 의 올바른 형태다.

- 카메라가 있는가, RenderSettings 가 카메라를 가리키는가
- 라이트가 하나라도 있는가 (없으면 까맣게 나온다)
- 지오메트리에 머티리얼이 바인딩돼 있는가
- 출력 경로의 디렉토리가 쓸 수 있는가
- 프레임 범위가 말이 되는가

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `settings` | `render_settings` (읽기), `set_render_settings` (해상도/샘플/프레임), `configure_aovs`, `list_render_products` |
| `run` | `render` (ROP 실행, 백그라운드), `render_status`, `cancel_render` |
| | `render_with_husk` — USD 파일 직행 |
| `check` | `validate_render` — 위 목록 전부. **렌더 전 필수** |
| `result` | `image_info` (OIIO 통계 + AOV 목록), `image_preview` (썸네일 반환), `compare_images` (두 렌더 diff) |
| `flipbook` | `flipbook` (뷰포트 시퀀스), `flipbook_status` |
| `bake` | `bake_textures`, `bake_ao`, `transfer_maps` — 22.0 의 베이크 경로를 먼저 조사 |

`manage_takes` 는 base 나 별도로 뺀다. 렌더 전용이 아니다.

## 먼저 확인할 것

1. `husk --help` 전체 플래그 (진행률 출력, 스냅샷, 로그 레벨)
2. `hou.RopNode.render()` 의 시그니처와 `addRenderEventCallback` (실측 확인:
   둘 다 있다). 콜백으로 진행률을 받을 수 있는지
3. 22.0 의 베이크 노드 — `bakeanimation`? Karma 베이크? 실제 경로 확인
4. OIIO 파이썬 API 의 정확한 사용법 — `ImageBufAlgo.computePixelStats` 반환 형태
5. flipbook 은 UI 전용이다. `hou.SceneViewer.flipbook()` 은 hython 에서 못
   쓴다. **UI 세션 전제로 만들고, 없으면 명확한 에러를 낸다**

## 검증

```
간단한 씬 → validate_render → 라이트 없음 경고
→ 라이트 추가 → validate_render 통과
→ render (낮은 샘플) → render_status 폴링 → 완료
→ image_info → 채널 평균이 0 이 아닌가 → image_preview 로 눈으로 확인
```
