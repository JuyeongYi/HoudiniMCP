# houdini_mcp_lop — LOPs / USD 전문

> 먼저 [README.md](README.md) 를 읽는다. 이 팩은 **제1원칙의 두 번째 사례**다.

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

## 우리가 쓸 경로 — 스테이지를 직접 연다

`hou.LopNode` 가 스테이지를 그대로 준다 (실측 확인):

```python
stage       = lop.stage()              # 읽기 전용, 컴포지션이 끝난 것
editable    = lop.editableStage()
active      = lop.activeLayer()
source      = lop.sourceLayer()
stats       = lop.stagePrimStats()
```

그리고 `pxr` 가 번들돼 있다 (OpenUSD 0.26.5, 실측 확인):

```python
from pxr import Usd, UsdGeom, UsdShade, UsdLux, UsdRender, Sdf, Ar
```

기존 구현 다섯 중 `pxr` 를 쓰는 곳은 **한 곳도 없다.**

### 이것으로 할 수 있는 것

| 하고 싶은 것 | 제대로 된 경로 |
|---|---|
| 프림 찾기 | `Usd.PrimRange(stage.GetPseudoRoot())` + 술어. 또는 `hou.LopSelectionRule` (실측 확인: 있다) |
| 어트리뷰트 읽기 | `prim.GetAttribute(name).Get(time)` — 컴포지션 적용된 값 |
| 컴포지션 분석 | `prim.GetPrimIndex()`, `.GetPrimStack()` — 어느 레이어에서 왔는지 |
| 레이어 스택 | `stage.GetLayerStack()`, `Sdf.Layer` |
| 배리언트 | `prim.GetVariantSets()` |
| 바운딩박스 | `UsdGeom.BBoxCache` |
| 라이트 | `UsdLux.LightAPI` — 노드가 아니라 프림에서 |
| 머티리얼 바인딩 | `UsdShade.MaterialBindingAPI` |
| 계층 통계 | `stagePrimStats()` + `PrimRange` 순회 |

`husd` 와 `loptoolutils` 도 번들돼 있다(실측 확인). SideFX 자체 헬퍼이므로
먼저 본다.

### 주의 — 스테이지는 크다

씬 하나에 프림 수십만 개가 있을 수 있다. **전체 계층을 JSON 으로 돌려주지
않는다.** 깊이 제한, 개수 제한, 술어 필터를 반드시 둔다. base 의
`network_graph` 가 쓰는 방식과 같다.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `stage` | `stage_info` (프림 수, 레이어 수, up axis, 단위, 시간 범위), `list_prims` (깊이·개수 제한 필수), `find_prims` (타입/패턴/커스텀 술어), `prim_info` (타입 + 어트리뷰트 + 스키마 + 바인딩 + 활성) |
| `attrs` | `get_attribute` (시간 샘플 포함), `set_attribute` (edit layer 에서), `list_attributes` |
| `layers` | `layer_stack`, `layer_info`, `prim_origin` (이 값이 어느 레이어·어느 아크에서 왔는가) ← **기존 구현에 없다. USD 디버깅의 핵심이다** |
| `composition` | `composition_arcs`, `list_variants`, `set_variant` |
| `light` | `create_light` (distant/dome/rect/sphere/disk), `light_info`, `set_light`, `list_lights` — `UsdLux` 로 |
| | `create_light_rig` (3점 조명 + HDRI 돔). 셸프가 하는 것과 맞춘다 |
| `build` | `create_lop_node` — base 의 `create_node` 로 되는 일이면 만들지 않는다 |
| `check` | `validate_stage` — 비어 있는 프림, 깨진 레퍼런스, 바인딩 없는 지오, 렌더 설정 누락 |

## 먼저 확인할 것

1. `lop.stage()` 가 노드를 쿡해야 유효한지 — 쿡 전에 부르면 무엇이 오는지
2. `hou.LopSelectionRule` 의 사용법
3. `husd` / `loptoolutils` 가 제공하는 함수 목록
4. edit layer 에서 값을 쓰는 올바른 방법 (`hou.LopNode.editableStage()` 와
   edit block 의 관계). **잘못 쓰면 스테이지가 오염된다** — 여기는 특히
   조심한다
5. `UsdRender` 스키마 — `houdini_mcp_render` 와 경계를 정한다

## 검증

```
LOP 네트워크 만들기 → stage_info → 프림 수 확인
→ sphere 프림 추가 → find_prims(type=Sphere) 로 찾기
→ 레퍼런스 걸기 → prim_origin 이 레퍼런스 레이어를 가리키는가
→ 배리언트 전환 → 값이 바뀌는가
→ 라이트 추가 → list_lights 에 나오는가
```
