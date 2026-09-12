# houdini_mcp_sop — SOP 전문

> 먼저 [README.md](README.md) 의 다섯 원칙을 읽는다. 특히 제1원칙(기존 구현을
> 베끼지 않는다)과 제3원칙(대량 데이터는 벌크 경로로)이 이 팩의 핵심이다.

**상태**: 구현 완료. 툴 31개. 회귀 테스트는 `tests/sop/` 에 있다.
아래 "실측으로 고친 것" 절은 구현하면서 확인한 사실이다 — 초안의 가정 몇 개가
틀렸다.

## 무엇을 담나

지오메트리를 **만들고 고치고 읽는** 것. `houdini_mcp_base` 의 `geometry` 모듈은
컨텍스트를 가리지 않는 통계·어트리뷰트만 담는다. 여기는 SOP 에서만 의미 있는
것을 담는다.

기존 구현이 가진 것(요구사항 명세로만 본다):

- dcc mesh-ops 19: `bevel_edges`, `boolean_op`, `extrude_faces`, `inset`,
  `bridge_edges`, `add_edge_loop`, `mirror`, `lathe_profile`, `loft_sections`,
  `auto_uv`, `uv_project`, `triangulate_geometry`, `convert_geometry`,
  `blast_geometry`, `group_geometry`, `merge_geometry`, `transform_geometry`,
  `add_normals`, `array_instances`
- fx Geometry 14: `find_nearest_point`, `get_attrib_stats`, `sample_geometry`,
  `get_group_members`, `get_prim_intrinsics`, `get_volume_info`, `get_bounding_box`
- dcc geometry: `create_primitive`, `create_curve_guides`,
  `get_primitive_intrinsics`

## 기존 구현이 한 방식과 그 한계

**조작 툴**은 전부 `createNode("bevel")` + `parm().set()` 의 얇은 래핑이다.
`create_node` + `set_parms` 로 이미 되는 일을 툴 19개로 늘려 놓은 것에 가깝다.
그대로 베끼면 우리 툴 목록만 부풀고 얻는 게 없다.

**조회 툴**은 파이썬 루프로 점을 돈다. 점 10만 개짜리를 읽으면 수 초가 걸리고,
그 결과를 JSON 으로 그대로 실어 보내 모델 컨텍스트를 태운다.

## 우리가 쓴 경로

### 1. 조작 툴은 "노드 하나 = 툴 하나" 로 만들지 않는다

의미 있는 단위로 묶는다. 모델이 `create_node("bevel")` 을 부를 수 있는데
`bevel` 툴이 따로 있을 이유는, **그 툴이 더 많은 것을 알 때뿐**이다.

각 조작 툴은 `_common.build` + `_common.report` 를 거친다. 그래서 다음이 항상
일어난다.

1. 입력 지오메트리를 확인한다 (점/프림 수, 프림 종류, 바운딩 박스)
2. 노드를 만들고 코멘트를 달고 파라미터를 건다
3. **쿡해서 결과를 확인하고 전후를 비교해 돌려준다**

```json
{
  "path": "/obj/castle/bevel_wall_edges",
  "type": "polybevel::3.0",
  "before": {"points": 8,  "prims": 6},
  "after":  {"points": 24, "prims": 26},
  "delta":  {"points": 16, "prims": 20, "vertices": 72},
  "warnings": []
}
```

이러면 모델이 "베벨이 먹었는지"를 다시 묻지 않는다. 이것이 기존 19개 래퍼와
갈라지는 지점이다.

여기에 툴마다 결과를 하나씩 더 얹었다. 이쪽이 실제로 판단을 바꾼다.

| 툴 | 덧붙이는 것 |
|---|---|
| `boolean_op` | 양쪽 입력의 **열린 에지 수**. 0 이 아니면 solid 연산이 조용히 이상해진다 |
| `reduce_polygons` | 요청한 감면율 대비 **실제 달성치** |
| `remesh_geometry` | 전후 **평균 에지 길이**와 목표치 |
| `convert_geometry` | 프림 종류가 안 바뀌었으면 **무엇을 대신 쓰라고** 알려 준다 |
| `uv_project`, `auto_uv` | **UV 품질 리포트** (0~1 이탈 비율, 점유율) |
| `create_group` | **실제 멤버 수**. 0 이면 무엇을 넓히라고 알려 준다 |
| `add_normals` | 기존 N 이 있었는지 (덮어쓰기 경고) |
| `copy_to_points` | 소스/타깃 개수. 결과 크기가 왜 그만큼인지 읽힌다 |

### 2. `soptoolutils` 는 쓸 수 없었다 (초안의 가정이 틀렸다)

초안은 "셸프 툴이 쓰는 검증된 조립 로직"을 재사용하자고 했는데, 실측해 보니
**`soptoolutils` 는 거의 전부 뷰어 전용**이다. 공개 함수 50여 개가 모두
`kwargs` / `scriptargs`(셸프 툴 컨텍스트)와 `sceneviewer`, 사용자 선택을 받는다.

```python
addPolyBevelTool(kwargs)
genericSopNodeFilterTool(scriptargs, nodetypename, nodename, ...)
getGeometrySelections(sceneviewer, selectors, ...)
```

MCP 에는 뷰어도 선택도 없다. 그래서 조립은 직접 한다.

**대신 쓸 것을 찾았다: SOP verb.** `hou.sopNodeTypeCategory().nodeVerb("...")` 로
노드를 만들지 않고 C++ 연산만 독립 지오메트리에 돌릴 수 있다. `boolean_op` 의
열린 에지 검사가 이것으로 되어 있다 — 사용자 네트워크를 더럽히지 않고
groupcreate(unshared edges)를 돌려 개수만 센다.

```python
verb = hou.sopNodeTypeCategory().nodeVerb("groupcreate")
verb.setParms({"groupname": "open_edges", "grouptype": 2,
               "groupbase": 0, "groupedges": 1, "unshared": 1})
out = hou.Geometry()
verb.execute(out, [geo])
out.findEdgeGroup("open_edges").edgeCount()   # 0 이면 닫힌 메시
```

### 3. 조회는 numpy 벌크 경로로

```python
raw = geo.pointFloatAttribValuesAsString("P", hou.numericData.Float32)  # bytes
array = numpy.frombuffer(raw, dtype=numpy.float32).reshape(-1, 3)
```

`_common.attrib_array` 가 owner(point/prim/vertex)와 dataType(Float/Int)에 따라
맞는 접근자를 골라 준다. numpy 2.3.2 번들 확인.

개수도 루프로 세지 않는다. `pointCount()` / `primCount()` / `vertexCount()` 와
`countPrimType()` 이 있다.

**돌려줄 때는 요약한다.**

- `attrib_stats`: 성분별 min/max/mean/std, 분위수(p05~p95), 히스토그램.
  성분이 여럿이면 크기(L2) 통계도
- `export_attribute`: 원본이 필요하면 `.npy` 로 쓰고 **경로를 돌려준다**
- `export_geometry`: `.bgeo.sc` / `.obj` / `.vdb` / `.usd` 등으로 쓰고 경로 반환
- `sample_points` 는 base 에 이미 있다. 중복으로 만들지 않았다

### 4. 근접 질의는 Houdini 것이 다 있었다

`hou.Geometry` 가 이미 갖고 있다(실측 확인). VEX wrangle 을 쿡할 필요가 없다.

```
nearestPoint(position, ptgroup=None, max_radius=1E18) -> hou.Point
nearestPoints(position, max_points, ptgroup=None, max_radius=1E18)
nearestPrim(position) -> (hou.Prim or None, distance, u, v)
intersect(ray_origin, ray_direction, position_out, normal_out, uvw_out, ...) -> int
```

`pointsInBoundingBox` 는 **없다**. 비슷한 이름의 `pointBoundingBox(pattern)` 은
"주어진 점들의 바운딩 박스"라 뜻이 반대다.

### 5. 볼륨은 값을 넘기지 않는다

`hou.Volume` 은 `resolution()`, `voxelSize()`, `volumeMin/Max/Average()`,
`isSDF()`, `isHeightField()`, `storageType()` 를 준다. `hou.VDB` 는 여기에
`vdbType()`, `activeVoxelCount()` 가 더 있다. `volume_info` 는 이것만 돌려준다.
복셀 값은 `allVoxelsAsString` 으로 받을 수 있지만 응답에 싣지 않는다.

## 실측으로 고친 것 — 초안의 가정이 틀렸던 지점

Houdini 22.0.368 기준. **버전이 올라가면 다시 확인해야 한다.**

| 초안/통념 | 실측 |
|---|---|
| `bevel` 노드 | **없다.** `polybevel` 로 만들면 `polybevel::3.0` 이 뜬다 |
| `boolean` 노드 | 타입 목록에 없지만 `createNode("boolean")` 은 `boolean::2.0` 으로 해석된다 |
| `lathe` 노드 | **없다.** `revolve` → `revolve::2.0` |
| `inset` 노드 | **없다.** PolyExtrude 의 `inset` 파라미터가 그 일을 한다. 툴을 따로 두지 않았다 |
| `curve` SOP 에 `coords` 파라미터 | **없어졌다.** 22.0 의 `curve` 는 `curve::2.0` 이고 좌표를 뷰어에서 그린 지오메트리(`stashgeo`)로 들고 있다. 스크립트로 채울 수 없어서 `create_curve` 는 **Add SOP** 으로 만든다 |
| `soptoolutils` 재사용 | 뷰어 전용이라 불가 (위 2절) |
| 메뉴 파라미터는 토큰으로 걸린다 | **일부만.** `hou.MenuParmTemplate` 은 토큰을 받지만, 메뉴가 달린 `hou.IntParmTemplate`(Normal SOP 의 `method`)은 숫자만 받는다. `_common.set_menu` 가 실패하면 인덱스로 다시 건다 |
| Divide SOP 은 `convex` 만으로 삼각화한다 | **아니다.** `usemaxsides=1` 을 켜야 사각형이 쪼개진다. 끄면 6면체가 6프림 그대로다 |
| UVProject 를 놓으면 UV 가 생긴다 | 생기긴 하는데 **0~1 밖으로 한참 벗어난다.** UI 의 "Initialize" 는 스크립트에서 부를 수 없다. 입력 바운딩 박스로 `t`=center, `s`=size 를 직접 걸면 UV 가 정확히 0~1 에 들어온다 (`fit_to_bounds`) |
| Convert SOP 으로 폴리곤 → VDB | 메뉴에 `vdb` 가 있지만 **변환되지 않는다.** `vdbfrompolygons` / `isooffset` 를 써야 한다. 툴이 변화 없음을 감지해 그렇게 알려 준다 |
| `node.parent()` 비교 | HOM 은 매번 새 래퍼를 준다. `is` / `==` 로 비교하면 같은 부모도 다르다고 나온다. **경로로 비교한다** (`_common.same_network`) |
| 에지 그룹에 번호 범위 | `"0-11"` 은 에지 그룹이 아니다. `"p0-1 p1-2"` 또는 `"*"` 다. 실패 메시지에 이 문법을 담았다 |

## 툴 목록 (31개)

| 모듈 | 툴 |
|---|---|
| `create` | `create_primitive`, `create_curve`, `copy_to_points` |
| `polyedit` | `bevel`, `extrude_faces`, `bridge_edges`, `mirror_geometry`, `revolve_profile`, `skin_sections`, `boolean_op` |
| `topology` | `convert_geometry`, `triangulate`, `remesh_geometry`, `reduce_polygons`, `transform_geometry`, `delete_geometry` |
| `attribs` | `attrib_stats`, `export_attribute`, `add_normals`, `create_attribute` |
| `groups` | `create_group`, `group_members` |
| `uv` | `uv_report`, `uv_project`, `auto_uv` |
| `query` | `nearest_point`, `nearest_prim`, `ray_intersect`, `prim_intrinsics`, `volume_info`, `export_geometry` |

노드를 만드는 툴은 전부 `comment` 를 **기본값 없는 인자**로 받는다. 씬을 바꾸는
툴은 전부 `@undoable("English Label")` 로 감쌌다.

초안에 있었으나 만들지 않은 것:

- `inset` — PolyExtrude 의 파라미터로 흡수 (전용 노드가 없다)
- `merge_geometry` — `create_node("merge")` + `connect_nodes` 로 이미 된다.
  래핑해도 더 아는 것이 없다
- `add_edge_loop` — 뷰어 상호작용 없이는 "어느 루프"를 지정할 수단이 빈약하다.
  `divide`/`polysplit` 을 `create_node` 로 놓는 편이 정직하다
- `sample_geometry`, `bounding_box` — base 의 `sample_points`, `geometry_stats`
  와 중복

## base 에 있으면 좋겠는 것

SOP 팩을 만들면서 base 에 없어 아쉬웠던 것. (이 팩에서 고치지 않았다.)

- `geometry_stats` 가 `len(geo.points())` 로 개수를 센다. `pointCount()` /
  `primCount()` / `vertexCount()` 와 `countPrimType()` 로 바꾸면 프림 10만 개에서
  파이썬 루프가 사라진다. `prim_types` 집계도 같은 문제다
- `attribute_values` 가 vertex owner 를 "아직 지원하지 않습니다" 로 거절한다.
  UV 가 vertex 어트리뷰트라 실제로 자주 막힌다. `vertexFloatAttribValues` 가
  이미 있으므로 채울 수 있다

## 검증

`tests/sop/` 가 hython 서브프로세스로 다음을 고정한다.

```
box 만들기 → 점 8개 확인 → bevel → 점 24개·프림 26개 확인
→ uv_project → UV 가 0~1 안에 들어옴 확인 → attrib_stats 로 P 분포 확인
→ 그룹 만들기 → 멤버 수 확인 → triangulate → 6프림이 12프림 확인
→ create_curve → revolve → 에지 그룹 실패 메시지가 문법을 알려 주는지 확인
```

```bash
python -m pytest tests/sop -q          # 12 passed
python -m pytest tests/package_order -q
```
