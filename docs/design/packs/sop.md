# houdini_mcp_sop — SOP 전문

> 먼저 [README.md](README.md) 의 다섯 원칙을 읽는다. 특히 제1원칙(기존 구현을
> 베끼지 않는다)과 제3원칙(대량 데이터는 벌크 경로로)이 이 팩의 핵심이다.

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

## 우리가 쓸 경로

### 1. 조작 툴은 "노드 하나 = 툴 하나" 로 만들지 않는다

의미 있는 단위로 묶는다. 모델이 `create_node("bevel")` 을 부를 수 있는데
`bevel_edges` 툴이 따로 있을 이유는, **그 툴이 더 많은 것을 알 때뿐**이다.

각 조작 툴은 다음을 반드시 한다.

1. 입력 지오메트리를 확인한다 (점/프림 수, 어떤 어트리뷰트가 있는지)
2. 노드를 만들고 파라미터를 건다
3. **쿡해서 결과를 확인하고 전후를 비교해 돌려준다**

```python
return {
    "path": node.path(),
    "before": {"points": 8, "prims": 6},
    "after":  {"points": 32, "prims": 30},
    "bbox": [...],
    "warnings": [...],
}
```

이러면 모델이 "베벨이 먹었는지"를 다시 묻지 않는다. 이것이 기존 19개 래퍼와
갈라지는 지점이다.

### 2. `soptoolutils` 를 먼저 본다

SideFX 셸프 툴이 쓰는 검증된 조립 로직이다. 번들돼 있다(실측 확인).
`bevel` 하나를 놓는 것과 셸프의 "Bevel" 이 하는 일이 다르다면, 셸프 쪽이
맞을 가능성이 높다.

```bash
hython -c "import soptoolutils, inspect; print([f for f in dir(soptoolutils) if not f.startswith('_')])"
```

### 3. 조회는 numpy 벌크 경로로

```python
# hou.Geometry 의 벌크 접근자 (실측 확인)
geo.pointFloatAttribValues("P")            # tuple, C++ 에서 한 번에
geo.pointFloatAttribValuesAsString("P", hou.numericData.Float32)   # bytes
geo.primIntAttribValues(...)
geo.vertexFloatAttribValues(...)
```

바이트로 받아 `numpy.frombuffer(buf, dtype=numpy.float32).reshape(-1, 3)` 로
꽂는다. numpy 2.3.2 가 번들돼 있다(실측 확인).

**돌려줄 때는 요약한다.** 점 10만 개를 그대로 보내지 않는다.

- `attrib_stats`: min/max/mean/std, 분위수, 히스토그램
- `sample_points`: 균등 샘플 N개 (이미 base 에 있다. 중복 만들지 말 것)
- 원본이 필요하면 `.npy` 나 `.bgeo.sc` 로 쓰고 **경로를 돌려준다**

### 4. 근접 질의는 Houdini 것을 쓴다

`find_nearest_point` 를 파이썬으로 전탐색하지 않는다. `scipy` 는 번들에
**없다**(실측 확인). 대신 Houdini 가 가진 것을 쓴다.

- `hou.Geometry.nearestPrim()`, `hou.Geometry.pointsInBoundingBox()` — 있는지
  `dir()` 로 먼저 확인한다
- 없으면 임시 `xyzdist` / `nearpoint` VEX wrangle 을 쿡해서 답을 얻는다.
  이쪽이 파이썬 전탐색보다 수십 배 빠르다

### 5. 볼륨은 따로 다룬다

`get_volume_info` 는 `hou.Volume` / `hou.VDB` 를 본다. 해상도·복셀 크기·
바운딩박스·값 범위는 `hou.Volume.resolution()`, `voxelSize()` 등으로 얻는다.
복셀 값을 통째로 넘기지 않는다.

## 툴 초안

`comment` 는 노드를 만드는 툴 전부에 **기본값 없는 인자**로 넣는다.

| 모듈 | 툴 | 비고 |
|---|---|---|
| `create` | `create_primitive` | box/sphere/tube/grid/torus/circle/curve. 전후 통계 반환 |
| | `create_curve` | 점 목록으로 곡선. NURBS/폴리 선택 |
| `modify` | `bevel`, `extrude`, `inset`, `bridge`, `mirror`, `lathe`, `loft` | 각각 전후 비교 반환 |
| | `boolean` | union/intersect/subtract. 입력 매니폴드 여부 먼저 확인 |
| | `transform_geometry` | 그룹 지정 가능 |
| | `convert`, `triangulate`, `remesh` | |
| `attribs` | `add_normals` | cusp 각도. 이미 있으면 알려 준다 |
| | `attrib_stats` | 히스토그램·분위수 포함 |
| | `attrib_values` | 벌크 경로 + 요약. base 의 것과 중복 점검 |
| | `set_detail_attrib` | |
| `groups` | `create_group` | 그룹 종류·표현식. 결과 멤버 수 반환 |
| | `group_members` | 큰 그룹은 요약 |
| `uv` | `uv_project`, `auto_uv` | UV 겹침·바깥 여부를 확인해 돌려준다 |
| `query` | `nearest_point`, `sample_geometry`, `bounding_box` | |
| | `volume_info` | |
| `copy` | `array_instances` | copy-to-points. 대상 점 수 확인 |

## 먼저 확인할 것

구현 전에 hython 으로 실측한다.

1. `soptoolutils` 가 실제로 제공하는 함수
2. `hou.Geometry` 의 벌크 접근자 정확한 시그니처와 `hou.numericData` 값들
3. `hou.Geometry` 에 근접 질의 메서드가 있는지
4. `hou.Volume` / VDB 접근자
5. 22.0 에서 `bevel` 등 노드의 실제 파라미터 이름 — **버전마다 다르다.**
   `nodetypes.node_type_info` 툴이 이미 있으니 그걸로 확인한다

## 검증

빈 씬에서 다음 시나리오가 끝까지 도는지 확인한다.

```
box 만들기 → 점 8개 확인 → bevel → 점 수 늘어남 확인
→ uv_project → UV 범위 확인 → attrib_stats 로 P 분포 확인
→ 그룹 만들기 → 멤버 수 확인
```

`tests/` 에 회귀를 남긴다. hython 서브프로세스로 돌리는 기존 방식을 따른다.
