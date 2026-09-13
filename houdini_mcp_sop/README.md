# houdini_mcp_sop

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `houdini_mcp_sop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 30개 |
| 모듈 (`TOOL_MODULES`) | `create`, `polyedit`, `topology`, `attribs`, `groups`, `uv`, `query` |

## 개요

```text
SOP 전문 툴 팩 — 지오메트리를 만들고 고치고 읽는다.

컨텍스트를 가리지 않는 조회(`geometry_stats`, `list_attributes`, `sample_points`
등)는 `houdini_mcp_base` 의 geometry 모듈에 있다. 여기는 SOP 에서만 의미가 있는
것을 담는다.

    create     프리미티브·커브 생성, 포인트에 복사
    polyedit   폴리곤 편집 — 베벨·익스트루드·브리지·미러·리볼브·스킨·불리언
    topology   토폴로지 변환 — 컨버트·삼각화·리메시·감면·트랜스폼·삭제
    attribs    어트리뷰트 — numpy 벌크 통계, 노멀, 어트리뷰트 생성
    groups     그룹 생성과 멤버 조회
    uv         UV 투영·자동 UV·UV 품질 리포트
    query      근접 질의·레이 교차·인트린식·볼륨·파일 내보내기

이 팩의 조작 툴은 노드를 만들고 끝내지 않는다. 반드시 쿡해서 전후 통계를 비교해
돌려준다. 모델이 "베벨이 먹었는지"를 다시 묻지 않아도 되게 하기 위해서다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`create_primitive`](#create_primitive) | `create` | 기본 도형 SOP 을 만들고 쿡해서 결과 통계를 돌려준다. | ✓ |
| [`create_curve`](#create_curve) | `create` | 점 목록으로 곡선을 만든다. | ✓ |
| [`copy_to_points`](#copy_to_points) | `create` | 소스 지오메트리를 타깃의 각 점에 복사한다. | ✓ |
| [`bevel`](#bevel) | `polyedit` | 에지나 점을 깎는다(PolyBevel). 전후 포인트·프림 수를 비교해 돌려준다. | ✓ |
| [`extrude_faces`](#extrude_faces) | `polyedit` | 면을 밀어낸다(PolyExtrude). 인셋만 하려면 distance=0, inset>0 을 준다. | ✓ |
| [`bridge_edges`](#bridge_edges) | `polyedit` | 두 에지 루프 사이에 면을 만든다(PolyBridge). | ✓ |
| [`mirror_geometry`](#mirror_geometry) | `polyedit` | 평면을 기준으로 지오메트리를 반사한다. | ✓ |
| [`revolve_profile`](#revolve_profile) | `polyedit` | 프로파일 커브를 축 둘레로 돌려 회전체를 만든다(선반/lathe). | ✓ |
| [`skin_sections`](#skin_sections) | `polyedit` | 단면 커브들 사이에 면을 씌운다(Skin/loft). | ✓ |
| [`boolean_op`](#boolean_op) | `polyedit` | 두 메시로 불리언 연산을 한다(Boolean SOP). | ✓ |
| [`convert_geometry`](#convert_geometry) | `topology` | 프리미티브 타입을 바꾼다(Convert SOP). | ✓ |
| [`triangulate`](#triangulate) | `topology` | 폴리곤을 삼각형(또는 지정한 변 수 이하)으로 쪼갠다(Divide SOP). | ✓ |
| [`remesh_geometry`](#remesh_geometry) | `topology` | 삼각형 크기를 고르게 다시 짠다(Remesh SOP). | ✓ |
| [`reduce_polygons`](#reduce_polygons) | `topology` | 폴리곤 수를 줄인다(PolyReduce SOP). | ✓ |
| [`transform_geometry`](#transform_geometry) | `topology` | 지오메트리(또는 그 일부)를 옮기고 돌리고 키운다(Transform SOP). | ✓ |
| [`delete_geometry`](#delete_geometry) | `topology` | 그룹이나 패턴에 걸린 것을 지운다(Blast SOP). | ✓ |
| [`attrib_stats`](#attrib_stats) | `attribs` | 어트리뷰트 전체의 분포를 통계로 돌려준다. |  |
| [`export_attribute`](#export_attribute) | `attribs` | 어트리뷰트 값 전체를 .npy 파일로 쓰고 경로를 돌려준다. |  |
| [`add_normals`](#add_normals) | `attribs` | 노멀을 만든다(Normal SOP). 이미 있으면 덮어쓰기 전에 알려 준다. | ✓ |
| [`create_attribute`](#create_attribute) | `attribs` | 어트리뷰트를 만들어 상수 값을 채운다(AttribCreate SOP). | ✓ |
| [`create_group`](#create_group) | `groups` | 그룹을 만들고 **실제로 몇 개가 걸렸는지** 돌려준다(GroupCreate SOP). | ✓ |
| [`group_members`](#group_members) | `groups` | 그룹에 무엇이 들었는지 돌려준다. 큰 그룹은 범위로 접어서 준다. |  |
| [`uv_report`](#uv_report) | `uv` | UV 가 제대로 깔렸는지 확인한다. |  |
| [`uv_project`](#uv_project) | `uv` | 투영으로 UV 를 만든다(UVProject SOP). 만든 뒤 UV 품질까지 확인해 돌려준다. | ✓ |
| [`auto_uv`](#auto_uv) | `uv` | UV 를 자동으로 펴고 0~1 안에 배치한다. 결과 품질까지 확인해 돌려준다. | ✓ |
| [`nearest_point`](#nearest_point) | `query` | 주어진 위치에 가장 가까운 포인트를 찾는다. |  |
| [`nearest_prim`](#nearest_prim) | `query` | 주어진 위치에 가장 가까운 프리미티브와 그 위의 최근접 점을 찾는다. |  |
| [`ray_intersect`](#ray_intersect) | `query` | 지오메트리에 레이를 쏴서 맞는 지점을 찾는다. |  |
| [`prim_intrinsics`](#prim_intrinsics) | `query` | 프리미티브의 인트린식을 읽는다. |  |
| [`volume_info`](#volume_info) | `query` | 볼륨/VDB 프리미티브의 해상도·복셀 크기·값 범위를 돌려준다. |  |

## 모듈별 상세

### `create`

지오메트리를 처음부터 만드는 툴.

#### create_primitive

```python
create_primitive(parent: str, shape: str, comment: str, name: str | None = None, size: Sequence[float] | None = None, center: Sequence[float] | None = None, rotate: Sequence[float] | None = None, divisions: Sequence[int] | None = None, prim_type: str = 'poly', platonic_solid: str = 'cube')
```

기본 도형 SOP 을 만들고 쿡해서 결과 통계를 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | SOP 을 담을 네트워크. 예: /obj/castle |
| `shape` | `str` | 필수 | box / sphere / tube / grid / torus / circle / platonic |
| `comment` | `str` | 필수 | 이 노드가 무엇을 위한 것인지. 필수. 씬에 저장되므로 영어로. 예: "Wall body, 20 x 4 x 1.2" |
| `name` | `str \| None` | `None` | 노드 이름. 역할이 드러나게. 예: wall_body, tower_shaft |
| `size` | `Sequence[float] \| None` | `None` | 셰이프별 크기 3개. box=(x,y,z), sphere=(rx,ry,rz), tube=(rad_bottom, rad_top, height), grid=(x,y), torus=(major,minor), circle=(rx,ry), platonic=(radius,). 생략하면 노드 기본값. |
| `center` | `Sequence[float] \| None` | `None` | 중심 위치 (x,y,z). 생략하면 원점. |
| `rotate` | `Sequence[float] \| None` | `None` | 회전 (rx,ry,rz) 도 단위. 생략하면 회전 없음. |
| `divisions` | `Sequence[int] \| None` | `None` | 분할 수. box=(x,y,z), 나머지=(rows,cols), circle=(divs,). |
| `prim_type` | `str` | `'poly'` | poly / polysoup / mesh / nurbs / bezier / prim / points. 셰이프가 지원하지 않는 값이면 쓸 수 있는 값을 알려 준다. |
| `platonic_solid` | `str` | `'cube'` | shape="platonic" 일 때만. tetrahedron / cube / octahedron / icosahedron / dodecahedron / soccerball / teapot. |

#### create_curve

```python
create_curve(parent: str, points: Sequence[Sequence[float]], comment: str, name: str | None = None, closed: bool = False, curve_type: str = 'poly')
```

점 목록으로 곡선을 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | SOP 을 담을 네트워크. 예: /obj/castle |
| `points` | `Sequence[Sequence[float]]` | 필수 | 점 좌표 목록. 예: [[0,0,0], [1,2,0], [3,0,0]] |
| `comment` | `str` | 필수 | 이 커브가 무엇인지. 필수. 영어로. |
| `name` | `str \| None` | `None` | 노드 이름. 역할이 드러나게. 예: tower_profile, path_spine |
| `closed` | `bool` | `False` | 시작점과 끝점을 이을지. |
| `curve_type` | `str` | `'poly'` | poly / nurbs / bezier. |

#### copy_to_points

```python
copy_to_points(source: str, target: str, comment: str, name: str | None = None, target_group: str = '', pack: bool = False, pivot: str = 'centroid', use_target_orientation: bool = True)
```

소스 지오메트리를 타깃의 각 점에 복사한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `source` | `str` | 필수 | 복사할 지오메트리 SOP 경로. |
| `target` | `str` | 필수 | 복사 위치가 될 점을 가진 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 복사하는지. 필수. 영어로. |
| `name` | `str \| None` | `None` | 노드 이름. 예: copy_merlons |
| `target_group` | `str` | `''` | 타깃 점 중 일부만 쓸 때 그룹/패턴. 예: "@type==1" |
| `pack` | `bool` | `False` | True 면 복사본을 패킹한다. 개수가 많으면 메모리가 크게 준다. |
| `pivot` | `str` | `'centroid'` | origin / centroid. 소스의 어디를 점에 맞출지. |
| `use_target_orientation` | `bool` | `True` | 타깃 점의 N/up/orient 어트리뷰트로 회전할지. |

### `polyedit`

폴리곤을 고치는 툴 — 베벨·익스트루드·브리지·미러·리볼브·스킨·불리언.

#### bevel

```python
bevel(path: str, comment: str, offset: float = 0.05, group: str = '*', group_type: str = 'edges', divisions: int = 1, shape: str = 'round', name: str | None = None)
```

에지나 점을 깎는다(PolyBevel). 전후 포인트·프림 수를 비교해 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 깎는지. 필수. 영어로. 예: "Soften wall top edges, 0.05" |
| `offset` | `float` | `0.05` | 깎는 폭. 지오메트리 크기 대비 너무 크면 폴리곤이 뒤집힌다. |
| `group` | `str` | `'*'` | 대상 패턴. 에지는 "*" 또는 "p0-1 p1-2", 점/프림은 번호 범위. |
| `group_type` | `str` | `'edges'` | edges / points / prims / guess. |
| `divisions` | `int` | `1` | 필렛 분할 수. 1 이면 챔퍼처럼 각지고, 키우면 둥글어진다. |
| `shape` | `str` | `'round'` | round / chamfer / crease / solid / none. |
| `name` | `str \| None` | `None` | 노드 이름. 역할이 드러나게. 예: bevel_wall_top |

#### extrude_faces

```python
extrude_faces(path: str, comment: str, distance: float = 0.1, inset: float = 0.0, group: str = '', divisions: int = 1, split_type: str = 'elements', output_front: bool = True, output_side: bool = True, output_back: bool = False, name: str | None = None)
```

면을 밀어낸다(PolyExtrude). 인셋만 하려면 distance=0, inset>0 을 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 밀어내는지. 필수. 영어로. 예: "Extrude merlon tops 0.4 up" |
| `distance` | `float` | `0.1` | 밀어내는 거리. 음수면 안쪽으로 판다. |
| `inset` | `float` | `0.0` | 밀어낸 면을 안쪽으로 줄이는 양. 양수면 좁아진다. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `divisions` | `int` | `1` | 옆면 분할 수. |
| `split_type` | `str` | `'elements'` | elements(면 하나씩) / components(붙은 덩어리째). |
| `output_front` | `bool` | `True` | 밀어낸 앞면을 남길지. |
| `output_side` | `bool` | `True` | 옆면을 만들지. |
| `output_back` | `bool` | `False` | 원래 자리의 뒷면을 남길지. 속을 파낼 때 켠다. |
| `name` | `str \| None` | `None` | 노드 이름. 예: extrude_merlon_tops |

#### bridge_edges

```python
bridge_edges(path: str, comment: str, source_group: str, destination_group: str, divisions: int = 1, keep_input: bool = True, name: str | None = None)
```

두 에지 루프 사이에 면을 만든다(PolyBridge).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. 양쪽 루프가 모두 이 지오메트리에 있어야 한다. |
| `comment` | `str` | 필수 | 무엇을 잇는지. 필수. 영어로. |
| `source_group` | `str` | 필수 | 시작 루프의 에지/프림 그룹 이름 또는 패턴. |
| `destination_group` | `str` | 필수 | 끝 루프의 에지/프림 그룹 이름 또는 패턴. |
| `divisions` | `int` | `1` | 잇는 구간의 분할 수. |
| `keep_input` | `bool` | `True` | 원래 지오메트리를 함께 남길지. |
| `name` | `str \| None` | `None` | 노드 이름. 예: bridge_tower_to_wall |

#### mirror_geometry

```python
mirror_geometry(path: str, comment: str, direction: Sequence[float] | None = None, origin: Sequence[float] | None = None, keep_original: bool = True, consolidate: bool = True, group: str = '', name: str | None = None)
```

평면을 기준으로 지오메트리를 반사한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 미러하는지. 필수. 영어로. |
| `direction` | `Sequence[float] \| None` | `None` | 반사 평면의 법선 (x,y,z). 기본 (1,0,0) — YZ 평면 대칭. |
| `origin` | `Sequence[float] \| None` | `None` | 반사 평면이 지나는 점 (x,y,z). 기본 원점. |
| `keep_original` | `bool` | `True` | 원본을 함께 남길지. False 면 반사본만 남는다. |
| `consolidate` | `bool` | `True` | 평면 위에서 겹친 점을 붙일지. 대칭 모델링의 이음매를 없앤다. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: mirror_wall_east |

#### revolve_profile

```python
revolve_profile(path: str, comment: str, axis: Sequence[float] | None = None, origin: Sequence[float] | None = None, divisions: int = 16, begin_angle: float = 0.0, end_angle: float = 360.0, cap: bool = False, name: str | None = None)
```

프로파일 커브를 축 둘레로 돌려 회전체를 만든다(선반/lathe).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 프로파일 커브를 내보내는 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 만드는지. 필수. 영어로. 예: "Revolve tower profile into cone roof" |
| `axis` | `Sequence[float] \| None` | `None` | 회전축 방향 (x,y,z). 기본 (0,1,0) — Y축. |
| `origin` | `Sequence[float] \| None` | `None` | 축이 지나는 점 (x,y,z). 기본 원점. |
| `divisions` | `int` | `16` | 둘레 분할 수. 클수록 매끄럽다. |
| `begin_angle` | `float` | `0.0` | 시작 각도(도). 부분 회전체를 만들 때. |
| `end_angle` | `float` | `360.0` | 끝 각도(도). 360 이면 한 바퀴. |
| `cap` | `bool` | `False` | 부분 회전체의 끝을 막을지. |
| `name` | `str \| None` | `None` | 노드 이름. 예: revolve_tower_roof |

#### skin_sections

```python
skin_sections(path: str, comment: str, close_along_sections: bool = False, name: str | None = None)
```

단면 커브들 사이에 면을 씌운다(Skin/loft).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 단면 커브들을 내보내는 SOP 경로. 프림 순서대로 이어진다. |
| `comment` | `str` | 필수 | 무엇을 씌우는지. 필수. 영어로. |
| `close_along_sections` | `bool` | `False` | 마지막 단면과 첫 단면을 이을지. |
| `name` | `str \| None` | `None` | 노드 이름. 예: skin_roof_sections |

#### boolean_op

```python
boolean_op(path_a: str, path_b: str, comment: str, operation: str = 'union', subtract_order: str = 'aminusb', a_is_solid: bool = True, b_is_solid: bool = True, name: str | None = None)
```

두 메시로 불리언 연산을 한다(Boolean SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path_a` | `str` | 필수 | A 입력 SOP 경로. |
| `path_b` | `str` | 필수 | B 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 자르는지. 필수. 영어로. 예: "Cut window openings out of wall body" |
| `operation` | `str` | `'union'` | union / intersect / subtract / shatter / seam. |
| `subtract_order` | `str` | `'aminusb'` | operation="subtract" 일 때 aminusb / bminusa / both. |
| `a_is_solid` | `bool` | `True` | A 를 속이 찬 입체로 볼지. False 면 표면으로 본다. |
| `b_is_solid` | `bool` | `True` | B 를 속이 찬 입체로 볼지. |
| `name` | `str \| None` | `None` | 노드 이름. 예: cut_windows |

### `topology`

토폴로지를 바꾸는 툴 — 변환·삼각화·리메시·감면·트랜스폼·삭제.

#### convert_geometry

```python
convert_geometry(path: str, comment: str, to_type: str, from_type: str = 'all', group: str = '', name: str | None = None)
```

프리미티브 타입을 바꾼다(Convert SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 바꾸는지. 필수. 영어로. |
| `to_type` | `str` | 필수 | poly / polySoup / mesh / nurbCurve / nurbSurf / bezCurve / bezSurf / volume / vdb 등. 잘못 주면 쓸 수 있는 값을 알려 준다. |
| `from_type` | `str` | `'all'` | 바꿀 대상 타입. all 이면 전부. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: convert_sphere_to_poly |

#### triangulate

```python
triangulate(path: str, comment: str, max_sides: int = 3, avoid_slivers: bool = True, group: str = '', name: str | None = None)
```

폴리곤을 삼각형(또는 지정한 변 수 이하)으로 쪼갠다(Divide SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 삼각화하는지. 필수. 영어로. |
| `max_sides` | `int` | `3` | 폴리곤 한 개의 최대 변 수. 3 이면 완전 삼각화. |
| `avoid_slivers` | `bool` | `True` | 가늘고 긴 삼각형이 나오지 않게 할지. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: triangulate_for_export |

#### remesh_geometry

```python
remesh_geometry(path: str, comment: str, target_size: float = 0.1, iterations: int = 3, smoothing: float = 0.2, group: str = '', name: str | None = None)
```

삼각형 크기를 고르게 다시 짠다(Remesh SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 리메시하는지. 필수. 영어로. |
| `target_size` | `float` | `0.1` | 목표 에지 길이. 작을수록 촘촘하고 무겁다. |
| `iterations` | `int` | `3` | 반복 횟수. 클수록 고르지만 느리다. |
| `smoothing` | `float` | `0.2` | 스무딩 정도 0~1. 크면 형태가 뭉개진다. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: remesh_rock_surface |

#### reduce_polygons

```python
reduce_polygons(path: str, comment: str, target: float, mode: str = 'poly_percent', group: str = '', name: str | None = None)
```

폴리곤 수를 줄인다(PolyReduce SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 줄이는지. 필수. 영어로. |
| `target` | `float` | 필수 | mode 가 percent 계열이면 퍼센트(0~100), count 계열이면 개수. |
| `mode` | `str` | `'poly_percent'` | poly_percent / pt_percent / poly_count / pt_count. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: reduce_rock_lod1 |

#### transform_geometry

```python
transform_geometry(path: str, comment: str, translate: Sequence[float] | None = None, rotate: Sequence[float] | None = None, scale: Sequence[float] | None = None, pivot: Sequence[float] | None = None, group: str = '', group_type: str = 'guess', name: str | None = None)
```

지오메트리(또는 그 일부)를 옮기고 돌리고 키운다(Transform SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 옮기는지. 필수. 영어로. |
| `translate` | `Sequence[float] \| None` | `None` | 이동 (x,y,z). |
| `rotate` | `Sequence[float] \| None` | `None` | 회전 (rx,ry,rz) 도 단위. |
| `scale` | `Sequence[float] \| None` | `None` | 배율 (sx,sy,sz). |
| `pivot` | `Sequence[float] \| None` | `None` | 회전·배율의 기준점 (x,y,z). |
| `group` | `str` | `''` | 대상 패턴. 비우면 전부. |
| `group_type` | `str` | `'guess'` | guess / points / prims / edges / breakpoints. |
| `name` | `str \| None` | `None` | 노드 이름. 예: place_tower_northwest |

#### delete_geometry

```python
delete_geometry(path: str, comment: str, group: str, group_type: str = 'guess', keep_selected: bool = False, delete_unused_points: bool = True, name: str | None = None)
```

그룹이나 패턴에 걸린 것을 지운다(Blast SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 왜 지우는지. 필수. 영어로. |
| `group` | `str` | 필수 | 지울 대상 그룹 이름 또는 패턴. 예: "@name=debris*", "0-5" |
| `group_type` | `str` | `'guess'` | guess / points / prims / edges / breakpoints. |
| `keep_selected` | `bool` | `False` | True 면 걸린 것만 남기고 나머지를 지운다. |
| `delete_unused_points` | `bool` | `True` | 프림을 지운 뒤 남은 외톨이 점도 지울지. |
| `name` | `str \| None` | `None` | 노드 이름. 예: remove_inner_faces |

### `attribs`

어트리뷰트를 읽고 만드는 툴.

#### attrib_stats

```python
attrib_stats(path: str, name: str, owner: str = 'point', bins: int = 16)
```

어트리뷰트 전체의 분포를 통계로 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `name` | `str` | 필수 | 어트리뷰트 이름. 예: P, N, Cd, pscale |
| `owner` | `str` | `'point'` | point / prim / vertex / detail. |
| `bins` | `int` | `16` | 히스토그램 구간 수. 최대 64. |

#### export_attribute

```python
export_attribute(path: str, name: str, file_path: str, owner: str = 'point')
```

어트리뷰트 값 전체를 .npy 파일로 쓰고 경로를 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `name` | `str` | 필수 | 어트리뷰트 이름. |
| `file_path` | `str` | 필수 | 저장할 .npy 경로. 확장자가 없으면 붙여 준다. $HIP 같은 변수를 그대로 쓴다. |
| `owner` | `str` | `'point'` | point / prim / vertex. |

#### add_normals

```python
add_normals(path: str, comment: str, owner: str = 'point', cusp_angle: float = 60.0, weighting: str = 'angle', group: str = '', name: str | None = None)
```

노멀을 만든다(Normal SOP). 이미 있으면 덮어쓰기 전에 알려 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 왜 노멀이 필요한지. 필수. 영어로. |
| `owner` | `str` | `'point'` | point / vertex / prim / detail. 어디에 N 을 달지. |
| `cusp_angle` | `float` | `60.0` | 이 각도(도)보다 크게 꺾이면 날카롭게 유지한다. |
| `weighting` | `str` | `'angle'` | angle(꼭짓점 각도) / area(면적) / uniform(균등). |
| `group` | `str` | `''` | 대상 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: smooth_wall_normals |

#### create_attribute

```python
create_attribute(path: str, comment: str, attrib_name: str, owner: str = 'point', attrib_type: str = 'float', value: Sequence[float] | float | str | None = None, group: str = '', name: str | None = None)
```

어트리뷰트를 만들어 상수 값을 채운다(AttribCreate SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 이 어트리뷰트가 왜 필요한지. 필수. 영어로. |
| `attrib_name` | `str` | 필수 | 만들 어트리뷰트 이름. 예: pscale, variant, lod |
| `owner` | `str` | `'point'` | point / prim / vertex / detail. |
| `attrib_type` | `str` | `'float'` | float / int / vector / string. |
| `value` | `Sequence[float] \| float \| str \| None` | `None` | 채울 값. float/int 는 숫자 하나, vector 는 값 3개, string 은 문자열. |
| `group` | `str` | `''` | 대상 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: set_merlon_scale |

### `groups`

그룹을 만들고 들여다보는 툴.

#### create_group

```python
create_group(path: str, comment: str, group_name: str, group_type: str = 'point', pattern: str = '', bounding_box: Sequence[float] | None = None, normal_direction: Sequence[float] | None = None, normal_angle: float = 180.0, keep_by_normals: bool = False, name: str | None = None)
```

그룹을 만들고 **실제로 몇 개가 걸렸는지** 돌려준다(GroupCreate SOP).

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 이 그룹이 무엇을 위한 것인지. 필수. 영어로. 예: "Top faces of wall, for merlon placement" |
| `group_name` | `str` | 필수 | 만들 그룹 이름. 역할이 드러나게, 영어로. 예: wall_top_faces |
| `group_type` | `str` | `'point'` | point / prim / edge / vertex. |
| `pattern` | `str` | `''` | 번호 범위나 표현식. 비우고 bounding_box 나 normal_direction 만 쓸 수도 있다. |
| `bounding_box` | `Sequence[float] \| None` | `None` | (중심x, 중심y, 중심z, 크기x, 크기y, 크기z) 6개. |
| `normal_direction` | `Sequence[float] \| None` | `None` | 기준 방향 (x,y,z). |
| `normal_angle` | `float` | `180.0` | normal_direction 에서 몇 도까지 받아줄지. |
| `keep_by_normals` | `bool` | `False` | normal_direction 을 쓸지. normal_direction 을 주면 자동으로 켜진다. |
| `name` | `str \| None` | `None` | 노드 이름. 예: group_wall_top |

#### group_members

```python
group_members(path: str, group_name: str, group_type: str = 'point', max_ranges: int = 50)
```

그룹에 무엇이 들었는지 돌려준다. 큰 그룹은 범위로 접어서 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `group_name` | `str` | 필수 | 그룹 이름. |
| `group_type` | `str` | `'point'` | point / prim / edge / vertex. |
| `max_ranges` | `int` | `50` | 돌려줄 범위 개수 상한. 최대 100. |

### `uv`

UV 를 만들고 품질을 확인하는 툴.

#### uv_report

```python
uv_report(path: str, uv_attrib: str = 'uv')
```

UV 가 제대로 깔렸는지 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `uv_attrib` | `str` | `'uv'` | UV 어트리뷰트 이름. 기본 uv. |

#### uv_project

```python
uv_project(path: str, comment: str, projection: str = 'texture', uv_attrib: str = 'uv', fit_to_bounds: bool = True, translate: Sequence[float] | None = None, rotate: Sequence[float] | None = None, scale: Sequence[float] | None = None, group: str = '', name: str | None = None)
```

투영으로 UV 를 만든다(UVProject SOP). 만든 뒤 UV 품질까지 확인해 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇에 왜 UV 를 까는지. 필수. 영어로. |
| `projection` | `str` | `'texture'` | texture(정사영) / polar / cylin(원통) / torus / wrap. |
| `uv_attrib` | `str` | `'uv'` | 만들 UV 어트리뷰트 이름. |
| `fit_to_bounds` | `bool` | `True` | 투영 기준을 입력 바운딩 박스에 맞춰 UV 가 0~1 에 들어오게 할지. translate/scale 을 직접 주면 그쪽이 이긴다. |
| `translate` | `Sequence[float] \| None` | `None` | 투영 기준의 이동 (x,y,z). |
| `rotate` | `Sequence[float] \| None` | `None` | 투영 기준의 회전 (rx,ry,rz) 도 단위. 정사영 방향을 이걸로 돌린다. |
| `scale` | `Sequence[float] \| None` | `None` | 투영 기준의 배율 (sx,sy,sz). |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: uv_wall_front |

#### auto_uv

```python
auto_uv(path: str, comment: str, method: str = 'flatten', uv_attrib: str = 'uv', pack_scale: float = 1.0, padding: int = 2, group: str = '', name: str | None = None)
```

UV 를 자동으로 펴고 0~1 안에 배치한다. 결과 품질까지 확인해 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 입력 SOP 경로. |
| `comment` | `str` | 필수 | 무엇에 왜 UV 를 까는지. 필수. 영어로. |
| `method` | `str` | `'flatten'` | flatten(펴기+배치) / unwrap(육면 투영). |
| `uv_attrib` | `str` | `'uv'` | 만들 UV 어트리뷰트 이름. |
| `pack_scale` | `float` | `1.0` | 배치 후 전체 배율. 1.0 이면 0~1 을 채운다. |
| `padding` | `int` | `2` | 아일랜드 사이 여백. 텍스처 픽셀 수로 준다. UVLayout 은 픽셀을 그대로 받고, UVUnwrap 은 UV 비율만 받으므로 1024 로 나눠 넘긴다. |
| `group` | `str` | `''` | 대상 프림 패턴. 비우면 전부. |
| `name` | `str \| None` | `None` | 노드 이름. 예: uv_rock_auto |

### `query`

지오메트리에 질문하는 툴 — 근접·레이·인트린식·볼륨·파일 내보내기.

#### nearest_point

```python
nearest_point(path: str, position: Sequence[float], count: int = 1, max_radius: float | None = None, point_group: str | None = None)
```

주어진 위치에 가장 가까운 포인트를 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `position` | `Sequence[float]` | 필수 | 기준 위치 (x,y,z). |
| `count` | `int` | `1` | 몇 개를 찾을지. 최대 100. |
| `max_radius` | `float \| None` | `None` | 이 반경 밖은 보지 않는다. 생략하면 제한 없음. |
| `point_group` | `str \| None` | `None` | 이 그룹 안에서만 찾는다. 그룹 이름 또는 패턴. |

#### nearest_prim

```python
nearest_prim(path: str, position: Sequence[float])
```

주어진 위치에 가장 가까운 프리미티브와 그 위의 최근접 점을 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `position` | `Sequence[float]` | 필수 | 기준 위치 (x,y,z). |

#### ray_intersect

```python
ray_intersect(path: str, origin: Sequence[float], direction: Sequence[float], max_distance: float | None = None)
```

지오메트리에 레이를 쏴서 맞는 지점을 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `origin` | `Sequence[float]` | 필수 | 레이 시작점 (x,y,z). |
| `direction` | `Sequence[float]` | 필수 | 레이 방향 (x,y,z). 정규화하지 않아도 된다. |
| `max_distance` | `float \| None` | `None` | 이 거리까지만 본다. 생략하면 제한 없음. |

#### prim_intrinsics

```python
prim_intrinsics(path: str, prim_number: int = 0, names: Sequence[str] | None = None)
```

프리미티브의 인트린식을 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `prim_number` | `int` | `0` | 볼 프리미티브 번호. |
| `names` | `Sequence[str] \| None` | `None` | 읽을 인트린식 이름들. 생략하면 전부(최대 60개). |

#### volume_info

```python
volume_info(path: str, prim_number: int | None = None)
```

볼륨/VDB 프리미티브의 해상도·복셀 크기·값 범위를 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `prim_number` | `int \| None` | `None` | 볼 프리미티브 번호. 생략하면 볼륨 프림 전부를 돌려준다. |
