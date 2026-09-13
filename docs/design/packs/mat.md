# houdini_mcp_mat — 머티리얼·룩데브 전문

> 먼저 [README.md](README.md) 를 읽는다.
>
> **상태: 구현 완료.** 아래 "우리가 쓸 경로"와 "먼저 확인할 것"은 계획이 아니라
> Houdini 22.0.368 에서 실측한 결과다. 실측과 어긋난 계획은 실측대로 고쳤다.

## 무엇을 담나

셰이더를 만들고, 잇고, 할당하고, 텍스처를 붙이는 것.

기존 구현이 가진 것: dcc material-library 12 + lookdev 12,
fx `create_material` / `assign_material`. 합쳐서 23개.

- 저작: `create_material`, `connect_shader`, `disconnect_shader`,
  `set_material_parms`, `set_material_attribute`
- 조회: `list_materials`, `get_material_parms`, `get_shader_connections`,
  `get_material_connections`, `list_assignments`, `get_shader_assignment`
- 텍스처: `assign_texture`, `list_images`, `reload_image`
- 컬러: `list_color_spaces`, `set_color_management`
- 프리셋: `save_preset` / `load_preset` / `list_presets` / `delete_preset`
  (material-library 와 lookdev 양쪽에 중복돼 있다 — 하나로 합친다)

## 기존 구현이 한 방식과 그 한계

전부 **VOP 노드를 만들고 잇는 수준**에 머문다. `connect_shader(a, b)` 는
`node.setInput()` 래퍼다.

이 방식이 놓치는 것:

- **셰이더가 유효한지 모른다.** 타입이 안 맞는 연결, 빠진 입력, 순환 참조를
  잡지 못한다.
- **머티리얼이 실제로 어떻게 보이는지 모른다.** 값만 던지고 끝난다.
- **컬러 스페이스를 문자열로 다룬다.** OCIO 설정을 읽지 않는다.
- **프리셋을 자체 JSON 포맷으로 저장한다.** 다른 도구에서 못 읽는다.

## 우리가 쓸 경로

### 1. MaterialX 1.39.5 가 번들돼 있다 (실측 확인)

```python
import MaterialX as mx
doc = mx.createDocument()
mx.readFromXmlFile(doc, path)
valid, message = doc.validate()      # 타입·연결 검증을 라이브러리가 해 준다
```

검증·상호운용·프리셋 저장을 **자체 포맷이 아니라 MaterialX 로** 한다.

#### VOP ↔ MaterialX 왕복 경로 (실측 결론)

계획서는 "내보내는 경로가 무엇인지 먼저 확인한다"였다. 확인 결과는 이렇다.

| 방향 | 경로 | 결과 |
|---|---|---|
| VOP → MaterialX | `vop2mtlx.saveShaderNetwork(filepath, vop)` | **있다.** `$HH/python3.13libs/vop2mtlx.py`. 셸프의 "Save MaterialX" 와 같은 경로다. 내보낸 문서는 `doc.validate()` 를 통과한다 |
| MaterialX → VOP | **없다** | Houdini 에 없다. `mtlx2hda.py` 는 **노드 정의**를 HDA 로 만드는 것이지 머티리얼 그래프를 세우는 것이 아니다 |

그래서 **읽어 들이기는 이 팩에서 만들었다**(`preset.load_material`). MaterialX
문서의 노드를 카테고리로 대응하는 `mtlx*` VOP 노드에 매핑해 세우고, 값과 연결과
그래프 출력을 복원한다. 대응이 없는 노드는 조용히 빠뜨리지 않고 `warnings` 에
담는다.

왕복에서 실측으로 확인한 것:

- `vop2mtlx` 가 내보내는 것은 `<nodegraph>` 다. `<surfacematerial>` 이 아니다.
  그래서 읽어 들일 때 MaterialX 빌더 서브넷을 세우고 그 안을 채운다.
- **`kma_material_properties` 가 있으면 내보낼 수 없다.** Karma Material
  Builder 로 만든 머티리얼이 여기 해당한다. `canSaveMaterialX()` 가 False 를
  돌려주고 파일이 만들어지지 않는다.
- **연결이 걸린 입력의 파라미터 값은 문서에 저장되지 않는다.** MaterialX 에서
  연결이 값을 이기기 때문이다. 왕복 뒤 그 파라미터는 노드 기본값으로 돌아온다.
  손실이 아니라 포맷의 의미가 그렇다.
- 새로 만든 `mtlximage` 의 기본 signature 는 `color3` 다. 문서의 타입대로
  되돌리지 않으면 float 입력에 color 를 물리게 된다. signature 메뉴는 float 를
  `"default"` 라고 부른다(`float`, `integer`, `boolean` → `default`).
- signature 가 파라미터 이름을 바꾼다. `default` 입력은 signature 가 color3 면
  `default_color3` 가 된다. 값을 걸기 전에 signature 를 먼저 정해야 한다.

### 2. USD 머티리얼은 `UsdShade` 로 읽는다 (실측 확인)

```python
from pxr import UsdShade
stage = lop.stage()
material = UsdShade.Material(stage.GetPrimAtPath("/materials/wall_stone"))
shader, name, kind = material.ComputeSurfaceSource("mtlx")
```

할당도 `UsdShade.MaterialBindingAPI` 로 **실제 바인딩을 질의**한다.

실측으로 확인한 것:

- `materiallibrary` LOP 의 기본 `matpathprefix` 는 `/materials/` 다. VOP 노드
  이름이 그대로 프림 이름이 된다. 그래서 `assign_material` 은 VOP 노드 경로를
  받아 프림 경로로 바꿔 준다.
- `materiallibrary` 는 `genpreviewshaders` 로 **USD Preview 셰이더를 자동
  생성한다.** mtlx 머티리얼 하나를 만들면 스테이지에는
  `mtlxstandard_surface` 와 `mtlxstandard_preview` 가 함께 생긴다.
  `ComputeSurfaceSource("mtlx")` 는 앞의 것을, 컨텍스트 없이 부르면 뒤의 것을
  준다.

`houdini_mcp_lop` 와의 경계는 아래 "경계" 절에 적었다.

### 3. 텍스처는 OpenImageIO 로 실제로 읽는다 (2.5.18.0, 실측 확인)

```python
import OpenImageIO as oiio
source = oiio.ImageInput.open(path)
spec = source.spec()                 # width, height, nchannels, format
{a.name: a.value for a in spec.extra_attribs}   # oiio:ColorSpace, compression
oiio.ImageBufAlgo.computePixelStats(buf)        # .min .max .avg .stddev .nancount
```

`assign_texture` 가 파일 경로만 받고 끝나지 않는다. 파일을 열어 해상도, 채널,
비트뎁스, 컬러스페이스 메타데이터를 읽고 **용도(`usage`)와 맞는지 판정한다.**
없는 파일이면 노드를 만들지 않고 실패한다.

UDIM 은 `<UDIM>` / `<udim>` / `%(UDIM)d` 토큰을 `[0-9][0-9][0-9][0-9]` 로 바꿔
`pathlib.glob` 으로 실제 타일 수를 센다.

### 4. 컬러 매니지먼트는 OCIO 설정에서 읽는다

**`PyOpenColorIO` 2.5.0 이 번들돼 있다 (실측 확인).** 계획서의 "번들 여부를
먼저 확인한다"에 대한 답이다. 기본 설정은
`$HFS/packages/ocio/houdini-config-v3.0.0_aces-v2.0_ocio-v2.5.ocio` 이고
`$OCIO` 가 그것을 가리킨다. 컬러스페이스 24개, ACES CG Config 다.

주의할 점이 하나 있다. **셰이더의 `filecolorspace` 파라미터 메뉴는 설정의 표시
이름이 아니라 별칭을 쓴다.**

| 설정의 이름 | 파라미터 메뉴가 받는 값 |
|---|---|
| `sRGB Encoded Rec.709 (sRGB)` | `srgb_texture`, `srgb_tx` |
| `Linear Rec.709 (sRGB)` | `lin_rec709` |
| `ACEScg` | `acescg` |

그래서 `list_color_spaces` 는 별칭까지 주고, `texture_parm_colorspaces` 는
파라미터 메뉴를 그대로 준다. `set_color_space` 는 메뉴에 없는 값을 거절한다 —
조용히 무시돼 렌더가 틀어지는 것을 막기 위해서다.

### 5. 22.0 의 기본 머티리얼 경로는 MaterialX 다 (근거)

`renderMask()` 를 실측했다.

| 계열 | VOP 구성 | `renderMask` | MaterialX 내보내기 |
|---|---|---|---|
| `materialx` | `mtlxstandard_surface` + `mtlxdisplacement` | `mtlx` | 된다 |
| `karma` | 위 + `kma_material_properties` | `mtlx` (+ Karma 전용 노드) | **안 된다** |
| `usdpreview` | `usdpreviewsurface` | — | 안 된다 |
| `principled` | `principledshader::2.0` | `VMantra OGL` | 안 된다 |

`principledshader` 의 renderMask 가 `VMantra OGL` 이라는 것이 결정적이다. 이것은
Mantra 시절 경로다. Karma 가 기본 렌더러인 22.0 에서 새로 만드는 머티리얼의
기본값은 **`materialx`** 로 한다. 상호운용이 필요하면 그대로 MaterialX 문서로
저장되고, Karma 전용 속성이 필요할 때만 `karma` 를 고른다.

머티리얼 조립은 손으로 배선하지 않고 `voptoolutils` 의
`_setupMtlXBuilderSubnet` / `_setupUsdPreviewBuilderSubnet` 을 부른다. 셸프의
"USD MaterialX Builder" / "Karma Material Builder" 가 쓰는 것과 같은 함수다.
이름이 밑줄로 시작하지만 `kwargs` 없이 부를 수 있어 hython 에서도 동작한다.

## 만든 툴 (21개)

| 모듈 | 툴 | 기존 구현과 다른 점 |
|---|---|---|
| `build` | `create_material` | 빈 서브넷이 아니라 셰이더·출력 배선까지 갖춘 채로. 계열별 렌더러와 MaterialX 내보내기 가능 여부를 함께 돌려준다 |
| | `connect_shader` | 인덱스가 아니라 **이름**으로 잇고 양쪽 타입을 검사한다 |
| | `disconnect_shader` | 끊은 뒤 **어떤 값이 대신 쓰이는지** 돌려준다 |
| | `set_material_parms` | 색은 `[r,g,b]` 로 한 번에. **연결이 걸린 입력에 값을 걸면 경고한다** |
| | `shader_inputs` | 입력·출력을 타입과 현재 연결과 함께 |
| `query` | `list_materials` | 머티리얼 플래그로 찾는다(이름·위치로 추측하지 않는다). `lop` 을 주면 스테이지에서 USD 머티리얼을 읽는다 |
| | `material_info` | 셰이더·연결·텍스처·**이 머티리얼을 거는 노드**까지 한 번에 |
| | `shader_graph` | 노드와 엣지. 개수 상한 있음 |
| | `validate_material` | **MaterialX 문서를 만들어 라이브러리에게 검증시킨다.** 출력 연결, 텍스처 존재, 내보내기 가능 여부까지 |
| `assign` | `assign_material` | 걸고 나서 **실제로 걸렸는지 센다**. SOP 은 어트리뷰트를 벌크로 읽고, LOP 은 UsdShade 로 질의한다 |
| | `list_assignments` | 파라미터가 아니라 결과를 읽는다. SOP 어트리뷰트 / LOP 바인딩 둘 다 |
| `texture` | `assign_texture` | **붙이기 전에 OIIO 로 파일을 연다.** 없으면 노드를 만들지 않는다. 대상 입력 타입에 맞춰 signature 를 고른다 |
| | `texture_info` | 해상도·채널·비트뎁스·컬러스페이스·MIP·UDIM 타일 수. `stats=True` 면 픽셀 통계 |
| | ~~`list_textures`~~ | **없앴다.** base 의 `list_dependencies(kinds=["Image"])` 와 같은 순회였다. 이미지 내용은 `texture_info` |
| | `reload_textures` | `texcache -c` + `glcache -c` |
| `color` | `list_color_spaces` | 하드코딩이 아니라 OCIO 설정에서. 별칭·롤·디스플레이까지 |
| | `texture_parm_colorspaces` | 파라미터 메뉴가 실제로 받는 값 |
| | `set_color_space` | 메뉴에 없는 값은 거절한다 |
| `preset` | `save_material` | **MaterialX 문서로.** 쓴 파일을 다시 읽어 검증까지 |
| | `load_material` | Houdini 에 없는 경로. 문서를 VOP 그래프로 되돌린다 |
| | `list_presets` | 파일 이름만이 아니라 안의 노드그래프·노드 수·유효성까지 |

`delete_preset` 같은 파일 삭제 툴은 만들지 않았다. 되돌릴 수 없고 MCP 툴로
노출할 이유가 없다.

### `usage` 로 잡는 것

`assign_texture` / `texture_info` 의 `usage` 는 `color` / `scalar` / `normal`
셋이다. 렌더를 돌려야 드러나는 문제를 붙이는 시점에 잡는다.

- `normal`: 채널이 3개 미만이면 노멀맵이 아니라 범프맵일 수 있다고 알려 준다.
  8비트면 밴딩을, sRGB 계열 컬러스페이스면 값이 틀어짐을 경고한다.
- `scalar`: sRGB 가 걸린 러프니스·메탈니스를 잡는다. 채널이 여럿이면 어느
  채널이 쓰이는지 확인하라고 한다.
- `color`: 채널 부족과, 8비트인데 선형이라고 표시된 경우를 잡는다.

## `houdini_mcp_lop` 와의 경계

**머티리얼 자체는 이 팩, 스테이지 일반은 lop 팩.** 이 팩이 USD 를 건드리는 것은
`UsdShade` 에 한정한다.

| 하는 일 | 어느 팩 |
|---|---|
| 머티리얼·셰이더 프림 조회 (`UsdShade.Material`, `Shader`) | **mat** |
| 머티리얼 바인딩 질의·설정 (`MaterialBindingAPI`, `assignmaterial`) | **mat** |
| `materiallibrary` 안의 셰이더 저작 | **mat** |
| 텍스처 파일 검사 (OIIO) | **mat** |
| 컬러스페이스 (OCIO) | **mat** |
| 프림 조회·검색·계층 (`list_prims`, `find_prims`, `prim_info`) | lop |
| 어트리뷰트 읽기·쓰기, edit layer | lop |
| 레이어 스택, 컴포지션 아크, `prim_origin` | lop |
| 배리언트 | lop |
| 라이트 (`UsdLux`) | lop |
| 스테이지 검증 (`validate_stage`) | lop |

`list_materials(lop=...)` 와 `list_assignments(<LOP>)` 가 스테이지를 읽지만,
**머티리얼과 바인딩만** 본다. 프림 목록이 필요하면 lop 팩의 `list_prims` 를
쓴다. 중복 툴을 만들지 않는다.

## 검증 (실행 결과)

```
머티리얼 만들기 → validate_material 통과
→ 텍스처 붙이기 → texture_info 로 해상도·채널 확인
→ 지오메트리에 할당 → list_assignments 에 나오는가
→ MaterialX 로 저장 → 다시 읽어서 같은가
```

`tests/` 에 넣지 않고 hython 스크립트로 돌렸다. Houdini 세션이 필요하고
실제 이미지 파일을 만들어 써야 하기 때문이다. 확인한 것:

- 툴 21개가 모두 등록된다
- 서버 패키지가 없을 때 `pythonrc.py` 가 Houdini 를 막지 않는다
- `create_material` 네 계열, `karma` 는 MaterialX 내보내기 불가로 보고한다
- OIIO 로 128px half float / 8비트 sRGB / 1채널 노멀맵을 읽고 경고를 낸다
- UDIM 타일 3장을 실제로 센다
- 없는 텍스처는 노드를 만들지 않고 실패한다
- `connect_shader` 가 float→float 은 통과, float→color 는 경고한다
- `set_material_parms` 가 연결된 입력을 경고한다
- SOP 할당 뒤 박스 6면에 걸린 것을 어트리뷰트에서 센다
- LOP 할당 뒤 `UsdShade` 로 바인딩 1건을 확인한다
- MaterialX 저장 → 읽기 → 재저장에서 노드 수와 연결과(연결되지 않은) 파라미터
  값이 보존된다
- `python -m pytest tests/package_order -q` 통과 (16 passed, 9 skipped)
