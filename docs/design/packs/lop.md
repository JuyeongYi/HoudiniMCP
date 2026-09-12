# houdini_mcp_lop — LOPs / USD 전문

> 먼저 [README.md](README.md) 를 읽는다. 이 팩은 **제1원칙의 두 번째 사례**다.
>
> 구현 완료. 툴 22개. 아래 내용은 전부 Houdini 22.0.368 에서 실측으로 확인한
> 것이다 — 초안의 가정 중 틀린 것은 "실측으로 바로잡은 것" 절에 적어 두었다.

## 무엇을 담나

Solaris(LOP) 네트워크와 그것이 만드는 USD 스테이지.

기존 구현이 가진 것: fx LOPs/USD 18 — `get_stage_info`, `list_usd_prims`,
`get_usd_prim`, `find_usd_prims`, `get_usd_attribute`, `set_usd_attribute`,
`get_usd_layers`, `inspect_usd_layer`, `get_usd_composition`, `get_usd_variants`,
`get_usd_materials`, `get_usd_prim_stats`, `get_last_modified_prims`,
`create_lop_node`, `create_light`, `create_light_rig`, `list_lights`,
`set_light_properties`.

라이트 관련(dcc light-rig 9)도 LOP 에서 하는 것이 22.0 의 표준 경로이므로
여기로 합친다.

## 기존 구현이 한 방식과 그 한계

fx 구현은 **USD 를 LOP 노드의 파라미터로 다룬다.** `get_usd_prim` 이 실제로는
LOP 노드의 `primpath` 파라미터를 읽는 식이다.

USD 의 핵심은 컴포지션이다 — 서브레이어, 레퍼런스, 페이로드, 배리언트, 인헤릿,
스페셜라이즈가 겹쳐서 최종 값이 나온다. **노드 파라미터를 읽어서는 최종 결과를
알 수 없다.** 컴포지션을 무시한 USD 툴은 틀린 답을 준다.

검증 중에 이것이 그대로 재현됐다. 레퍼런스 안에서 `radius` 가
`/prop/body`(직접 스펙)와 `/prop{size=small}body`(배리언트 스펙) 양쪽에
걸려 있으면, **배리언트를 바꿔도 값이 안 바뀐다** — 직접 스펙이 더 강하기
때문이다. 노드 파라미터를 읽는 툴은 "배리언트를 big 으로 바꿨다"고 보고하고
끝나지만, `prim_origin` 은 어느 의견이 이겼고 왜 그런지를 보여 준다.

## 우리가 쓸 경로 — 스테이지를 직접 연다

`hou.LopNode` 가 스테이지를 그대로 준다:

```python
stage       = lop.stage()              # 읽기 전용, 컴포지션이 끝난 것
active      = lop.activeLayer()
source      = lop.sourceLayer()
stats       = lop.stagePrimStats()
```

그리고 `pxr` 가 번들돼 있다 (OpenUSD 0.26.5):

```python
from pxr import Usd, UsdGeom, UsdShade, UsdLux, UsdRender, Sdf, Ar, Pcp
```

기존 구현 다섯 중 `pxr` 를 쓰는 곳은 **한 곳도 없다.**

### 이것으로 할 수 있는 것

| 하고 싶은 것 | 제대로 된 경로 |
|---|---|
| 프림 찾기 | `hou.LopSelectionRule` (Houdini 패턴 + `%type:` `%kind:` 술어). 또는 `Usd.PrimRange` + 술어 |
| 어트리뷰트 읽기 | `prim.GetAttribute(name).Get(time)` — 컴포지션 적용된 값 |
| 컴포지션 분석 | `Usd.PrimCompositionQuery` — 아크 종류·출처·도입 위치가 전부 나온다 |
| 값의 출처 | `prim.GetPrimStack()`, `attr.GetPropertyStack(time)` — 강한 순서대로 |
| 레이어를 만든 노드 | `husd.GetLabelForLayer`, `husd.GetEditorNodesForLayer` |
| 레이어 스택 | `husd.GetRootLayerStackInfo(stage.GetRootLayer())` |
| 배리언트 | `prim.GetVariantSets()` |
| 바운딩박스 | `UsdGeom.BBoxCache` |
| 라이트 | `prim.HasAPI(UsdLux.LightAPI)` — 노드가 아니라 프림에서 |
| 머티리얼 바인딩 | `UsdShade.MaterialBindingAPI.ComputeBoundMaterial()` |
| 계층 통계 | `stagePrimStats(do_geometry_counts=True, do_kind_counts=True)` |

### 주의 — 스테이지는 크다

씬 하나에 프림 수십만 개가 있을 수 있다. **전체 계층을 JSON 으로 돌려주지
않는다.** 깊이 제한, 개수 제한, 술어 필터를 반드시 둔다. 배열 어트리뷰트도
마찬가지다 — `jsonify` 가 `max_array` 를 넘으면 `{count, head, truncated}` 로
줄인다.

---

## 실측으로 바로잡은 것

초안의 가정 중 틀렸거나 불완전했던 것들이다. 전부 hython 으로 확인했다.

### `lop.stage()` 는 알아서 쿡한다

쿡 전에 불러도 된다. `needsToCook()` 이 True 인 노드에 `stage()` 를 부르면
`cookCount` 가 0 에서 1 이 되고 유효한 스테이지가 온다. 다만 **쿡이 실패하면
`None` 이 오므로** 반드시 걸러야 한다 (`usdcommon.stage_of`).

`stage(frame=...)` 로 특정 프레임의 스테이지를 얻을 수 있다.

### `editableStage()` 는 Python LOP 전용이고, **예외 없이 `None` 을 준다**

lop.md 초안이 가장 크게 틀렸던 지점이다. 일반 LOP 노드에서
`node.editableStage()` 를 부르면 에러도 없이 `None` 이 온다. 여기에 `.` 를
찍으면 `AttributeError` 가 나서, 진짜 원인("이건 Python LOP 이 아니다")과
동떨어진 메시지를 보게 된다.

**edit layer block(`editlayer_begin`/`editlayer_end`)은 쓰기 경로가 아니라
편집이 어느 레이어로 가는지를 정하는 장치다.** 값을 쓰려면 어차피 노드가
필요하다.

그래서 **스테이지에 값을 쓰는 툴은 전부 `pythonscript` LOP 노드를 만들어 그
안에서 쓴다.** 얻는 것이 셋이다.

1. 편집이 노드로 남는다 — 재쿡·Undo·씬 저장이 자연스럽다.
2. 사용자가 무엇이 쓰였는지 코드로 볼 수 있다.
3. 스테이지를 몰래 오염시키지 않는다.

생성되는 코드는 **이 팩을 import 하지 않는다.** 팩이 없는 머신에서 씬을 열어도
노드가 쿡돼야 하기 때문이다. 값은 JSON 으로 코드 안에 박는다.

```python
# Authored by houdini_mcp_lop. Edit freely - this is plain USD.
import json

from pxr import Sdf, Usd

node = hou.pwd()
stage = node.editableStage()
spec = json.loads(r"""[{"prim": "/world/ball", "name": "radius", ...}]""")

for item in spec:
    ...
```

값을 쓰는 노드는 `lop` 바로 뒤에 **끼워 넣는다(splice)** — 원래 하류로 가던
연결을 새 노드 뒤로 다시 잇고 디스플레이 플래그도 옮긴다. 그래야 편집이 실제로
반영된다. 어느 노드가 다시 이어졌는지는 결과의 `rewired` 로 돌려준다.

### 라이트 파라미터 이름은 `hou.text.encode` 로 만든다

`light::2.0` 의 Intensity 파라미터 이름은 `xn__inputsintensity_i0a` 다. Houdini
가 USD 속성 이름을 punycode 로 인코딩한 것이다. 하드코딩하면 Houdini 가 스키마를
손볼 때 조용히 깨진다.

```python
hou.text.encode("inputs:intensity")   # 'xn__inputsintensity_i0a'
hou.text.decode("xn__inputsintensity_i0a")  # 'inputs:intensity'
```

`inputs:color` 처럼 벡터인 것은 `parm()` 이 None 이고 `parmTuple()` 로 잡힌다.

### `lighttype` 토큰과 돔

`light::2.0` 의 `lighttype` 메뉴는 `UsdLuxCylinderLight`, `UsdLuxDistantLight`,
`UsdLuxDiskLight`, `point`, `UsdLuxRectLight`, `UsdLuxSphereLight` 다.
**돔은 여기에 없다** — `domelight::3.0` 전용 노드이고, 만들어지는 프림 타입은
`DomeLight_1`(새 돔 스키마)이다. `UsdLux.DomeLight` 가 아니라
`UsdLux.DomeLight_1` 이므로 타입 이름으로 거르는 코드는 둘 다 봐야 한다.

라이트를 찾을 때는 타입 이름 대신 `prim.HasAPI(UsdLux.LightAPI)` 를 쓴다.
22.0 에서 모든 구체 라이트 타입에 LightAPI 가 붙는 것을 확인했다.

### `reference` LOP 의 파라미터

`primpath`(상단)가 아니라 멀티파라미터 쪽 `primpath1` 이 실제로 쓰인다.
`reftype1` 토큰은 `file`, `payload`, `prim`, `inherit`, `specialize` 다.

두 갈래로 갈린다.

- `file` / `payload` — `filepath1` 로 외부 파일. `filerefprim1` 이 빈
  문자열이면 `filerefprimpath1` 을 소스 프림으로 쓰고, `defaultPrim` /
  `automaticPrim` 이면 파일 메타데이터를 따른다.
- `prim` / `inherit` / `specialize` — **`filepath1` 을 쓰지 않는다.**
  `filerefprimpath1` 이 같은 스테이지 안의 원본 프림 경로다.

### `hou.LopSelectionRule`

`rule.setPathPattern(...)` + `rule.expandedPaths(lopnode)` 다. 확인한 패턴:

```
/world/**                   /world 아래 전부
%type:Sphere                타입으로
%type:UsdLuxDistantLight    UsdLux 스키마 이름으로도 된다
/world/lights/*             한 단계만
```

`setTraversalDemands(hou.lopTraversalDemands.*)` 로 순회 조건을 바꾼다
(`Default`, `NoDemands`, `Defined`, `Active`, `Loaded`, `NonAbstract`,
`AllowInstanceProxies`).

### 익명 레이어는 `husd` 가 사람 말로 바꿔 준다

Houdini 의 LOP 스테이지는 레이어가 거의 다 익명이라 identifier 가
`anon:0000000041645800:LOP` 같은 주소값이다. 그대로 돌려주면 쓸모가 없다.

```python
husd.GetLabelForLayer(layer)        # '/stage/ground_ball'
husd.GetEditorNodesForLayer(layer)  # [<hou.LopNode /stage/ground_ball>, ...]
husd.GetRootLayerStackInfo(root)    # 세션 레이어를 뺀 루트 레이어 스택
```

`stage.GetLayerStack()` 을 그냥 쓰면 뷰포트 오버라이드용 세션 레이어(Solo
Lights, Visibility and Activation 등)까지 10개 넘게 섞여 나온다.
`GetRootLayerStackInfo` 는 그것을 빼 준다.

### 그 밖의 실측 메모

- `pxr.Vt.Array` 라는 베이스 클래스는 **없다.** 배열 판별은 타입의 모듈
  (`pxr.Vt`)과 이름(`*Array`)으로 한다.
- `Sdf.ValueTypeNames.GetAll()` 은 없다. 타입 유효성은
  `Sdf.ValueTypeNames.Find(name)` 의 참/거짓으로 본다.
- 스칼라 타입(`double`, `token`, `string`)은 `valueType.type.pythonClass` 가
  `None` 이다. 캐스팅은 `pythonClass` 가 있을 때만 한다. `asset` 은
  `Sdf.AssetPath` 로 따로 감싸야 한다.
- `Sdf.CopySpec` 은 대상 레이어에 **부모 스펙이 먼저 있어야** 한다.
  `Sdf.CreatePrimInLayer` 를 먼저 부른다.
- `Sdf.Path(...).pathString` 은 메서드가 아니라 프로퍼티다.
- Houdini 는 레이어마다 `/HoudiniLayerInfo` 라는 장부 프림을 심는다. 씬의
  내용이 아니므로 순회에서 걸러 낸다.
- `loptoolutils` 는 셸프 툴 상태(뷰포트 인터랙션)에 묶인 함수가 대부분이라
  MCP 툴에서 쓸 것이 거의 없다. 쓸모 있는 것은 `husd` 쪽이다.

---

## 만든 툴 (22)

| 모듈 | 툴 |
|---|---|
| `stage` | `stage_info`, `list_prims`, `find_prims`, `prim_info`, `prim_stats` |
| `attrs` | `list_usd_attributes`, `get_usd_attribute`, `set_usd_attribute` |
| `layers` | `layer_stack`, `layer_contents`, **`prim_origin`** |
| `composition` | `composition_arcs`, `list_variants`, `set_variant`, `add_reference`, `add_sublayer` |
| `lights` | `create_light`, `create_light_rig`, `list_lights`, `light_info`, `set_light` |
| `check` | `validate_stage` |
| `usdcommon` | 툴 없음. 스테이지 해석·값 변환·노드 삽입 공용 헬퍼 |

`create_lop_node` 는 만들지 않았다 — base 의 `create_node` 로 되는 일이다.

### 이름이 초안과 다른 것

`houdini_mcp_base` 에 지오메트리 어트리뷰트용 `list_attributes` 가 이미 있어
이름이 부딪힌다. USD 어트리뷰트 셋은 `list_usd_attributes` /
`get_usd_attribute` / `set_usd_attribute` 로 간다.

### `prim_origin` — 이 팩의 차별점

이 값이 **어느 레이어의 어느 아크에서 왔는가.** 기존 구현 다섯 중 어디에도
없다.

```
prim_origin(lop, "/world/imported/body", attribute="radius")
→ winning: {value: 3.0}
  opinions:
    rank 0 (strongest)  hmcp_lop_asset.usda  /prop/body.radius           = 3.0
                        arc: reference, introduced at /world/imported
    rank 1              hmcp_lop_asset.usda  /prop{size=small}body.radius = 1.0
                        arc: variant, introduced at /prop
```

익명 레이어면 `label` 에 그 레이어를 만든 LOP 노드 경로가, `editor_nodes` 에
그 레이어를 건드린 노드들이 붙는다. "이 값은 `/stage/mat_override` 가
걸었다"까지 답한다.

---

## 다른 팩과의 경계

### `houdini_mcp_mat` — 머티리얼

| 무엇 | 누구 |
|---|---|
| 셰이더 그래프 만들기·고치기 (MaterialX, Karma, USD Preview Surface) | mat |
| `materiallibrary` / `assignmaterial` 로 바인딩 저작 | mat |
| 머티리얼 프림의 셰이더 네트워크 질의 | mat |
| 프림에 무엇이 바인딩됐는지 질의 (`prim_info.material_binding`) | lop |
| 바인딩이 없는 지오메트리 찾기 (`validate_stage.unbound_geometry`) | lop |

한 줄로: **머티리얼 자체는 mat, 스테이지 일반은 lop.** lop 은 바인딩을 *읽기만*
하고 고치지 않는다. `validate_stage` 는 바인딩 누락을 찾으면 mat 의 툴을 쓰라고
안내한다.

### `houdini_mcp_render` — 렌더

| 무엇 | 누구 |
|---|---|
| `UsdRender.Settings` / `Product` / `Var` 저작, AOV 구성 | render |
| `husk` 실행, 렌더 진행·결과 확인, `OpenImageIO` 로 이미지 검사 | render |
| Karma 전용 설정 | render |
| 렌더 설정 프림이 **있는지** 확인 (`validate_stage.no_render_settings`) | lop |
| 라이트 (UsdLux) | lop |
| 카메라 프림이 있는지 확인 | lop |

한 줄로: **렌더 설정과 실행은 render, 렌더될 스테이지는 lop.** 라이트는
`UsdLux` 스키마라 스테이지의 일부이므로 lop 이 갖는다. `validate_stage` 의
`check_render=False` 로 렌더 관련 검사를 끌 수 있다.

`UsdRender` 를 lop 이 건드리는 곳은 `validate_stage` 에서
`prim.IsA(UsdRender.Settings)` 로 존재 여부를 세는 것뿐이다.

---

## base 에 있어야 할 것

- `hou.text.encode` / `decode` 래퍼. USD 속성 이름 ↔ 파라미터 이름 변환은
  LOP 뿐 아니라 머티리얼·렌더 팩도 똑같이 필요하다. 지금은 lights 모듈의
  `_set_usd_parm` 에 있다.
- 노드를 **끼워 넣는**(하류 연결을 다시 잇는) 헬퍼. 지금은
  `usdcommon.insert_lop` 에 있지만 SOP/DOP 도 같은 것이 필요하다. base 의
  `create_node` 에 `insert_after` 옵션을 두는 편이 낫다.

## 남긴 TODO

- `set_usd_attribute` 는 호출마다 `pythonscript` 노드를 하나 만든다. 편집을 많이
  하면 노드가 줄줄이 쌓인다. 같은 노드에 스펙을 누적하는 `append` 모드를
  생각해 볼 만하다 — 다만 노드 하나 = 편집 하나가 Undo 와 가독성에는 낫다.
- 프림 **삭제·비활성화**(`prune` LOP) 툴이 없다. 만들기만 하고 지우지 못한다.
- 카메라 툴이 없다. `validate_stage` 가 없다고 지적만 한다. 카메라는 렌더
  팩과 lop 중 어디로 갈지 정해야 한다(스키마상으로는 `UsdGeom.Camera` 라 lop).
- `set_variant` 는 `setvariant` 노드를 매번 새로 만든다. 배리언트를 여러 개
  고를 때 멀티파라미터에 누적하는 편이 낫다.
- 인스턴싱(`PointInstancer`, prototypes)을 따로 다루지 않는다. `list_prims` 는
  인스턴스 프록시를 기본적으로 내려가지 않는다.

## 검증

```
LOP 네트워크 만들기 → stage_info → 프림 수 확인                           OK
→ sphere 프림 추가 → find_prims(%type:Sphere) 로 찾기                     OK
→ 레퍼런스 걸기 → prim_origin 이 레퍼런스 레이어를 가리키는가             OK
→ 배리언트 전환 → 값이 바뀌는가 (radius 1.0 → 10.0)                       OK
→ 라이트 추가 → list_lights 에 나오는가                                   OK
```

추가로 확인한 것:

- 툴 22개 전부 등록 (`register_pack` → 22)
- 서브레이어, 페이로드, 같은 스테이지 안의 프림 레퍼런스
- 시간 샘플 쓰기/읽기 (`frame=10.0`)
- 프림 503개 스테이지에서 `list_prims` / `find_prims` 의 `truncated`
- 점 3,600개 배열 어트리뷰트가 `{count, head, truncated}` 로 줄어드는 것
- 에러 메시지 13종 — 전부 "무엇이 잘못됐고 다음에 무엇을 할지"를 담고 있다
- `pythonrc.py` 보호회로: `houdini_mcp` 이 깨져도 예외가 새지 않는다
- 모듈 격리: `lights` 가 깨져도 나머지 17개가 등록된다
- `python -m pytest tests/package_order -q` → 16 passed, 9 skipped
