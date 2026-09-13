# houdini_mcp_dop

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `houdini_mcp_dop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 18개 |
| 모듈 (`TOOL_MODULES`) | `setup`, `objects`, `fields`, `run`, `cache`, `check` |

## 개요

```text
DOP 공통 툴 팩 — 시뮬레이션을 짓고, 돌려 보고, 무슨 일이 일어났는지 안다.

솔버별 전문(파이로 소스 플러밍, FLIP 화이트워터, RBD 프랙처)은 하위 팩으로
뺀다. 여기는 솔버를 가리지 않는 것만 담는다.

    setup    dopnet 생성, 오브젝트 편입, 힘 추가 — 만든 것을 전부 설명한다
    objects  시뮬 오브젝트·릴레이션십·솔버 구성 조회
    fields   볼륨 필드 목록과 통계 — 복셀을 통째로 넘기지 않는다
    run      프레임 진행, 저해상도 시험 주행, 리셋, 메모리
    cache    .sim 캐시 쓰기와 상태
    check    돌리기 전에 무엇이 빠졌는지 찾는다

툴이 없는 헬퍼는 둘로 나눠 뒀다. `_common` 은 씬을 만지는 쪽(레시피 표, 노드
해석과 조립, dopnet 구조), `_state` 는 쿡된 결과를 읽는 쪽(오브젝트 요약, 필드
통계, 프레임 진행과 발산 감지)이다.

이 팩의 셋업 툴은 블랙박스 매크로가 아니다. 만든 노드마다 역할과 건 파라미터,
그리고 다음에 무엇을 하면 되는지를 함께 돌려준다. 모델이 이어서 손볼 수
있어야 하기 때문이다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`create_dopnet`](#create_dopnet) | `setup` | 빈 DOP 네트워크를 만들고 중력·머지·출력을 이어 돌려준다. | ✓ |
| [`add_dop_object`](#add_dop_object) | `setup` | /obj 의 지오메트리를 시뮬에 편입시키고, 만든 것을 전부 설명해 돌려준다. | ✓ |
| [`add_dop_force`](#add_dop_force) | `setup` | 시뮬 전체에 걸리는 힘을 체인 끝에 끼워 넣고 무엇이 바뀌었는지 돌려준다. | ✓ |
| [`list_dop_objects`](#list_dop_objects) | `objects` | 쿡된 시뮬 안의 오브젝트들과 각각의 상태. |  |
| [`dop_object_info`](#dop_object_info) | `objects` | 시뮬 오브젝트 하나를 깊게. 레코드, 서브데이터, 만든 노드, 솔버. |  |
| [`dop_relationships`](#dop_relationships) | `objects` | 시뮬의 릴레이션십 — 무엇이 무엇에 영향을 주고 어떤 컨스트레인트가 있는지. |  |
| [`simulation_info`](#simulation_info) | `objects` | 시뮬 구성 전체 — 솔버, 타임스텝, 서브스텝, 캐시 설정, 현재 상태. |  |
| [`dop_node_info`](#dop_node_info) | `objects` | dopnet 안의 DOP 노드 하나가 실제로 시뮬에 참여하는지와 그 연결. |  |
| [`list_dop_fields`](#list_dop_fields) | `fields` | 시뮬 오브젝트가 가진 볼륨 필드 목록 — 종류, 해상도, 복셀 수, 메모리. |  |
| [`field_stats`](#field_stats) | `fields` | 필드 하나의 값 통계. 복셀을 통째로 넘기지 않는다. |  |
| [`field_data_types`](#field_data_types) | `fields` | 오브젝트의 서브데이터를 종류별로 갈라 준다 — 필드, 솔버, 힘, 그 밖. |  |
| [`step_simulation`](#step_simulation) | `run` | 현재 프레임에서 N 프레임 진행시키고 프레임별 상태를 돌려준다. |  |
| [`test_simulation`](#test_simulation) | `run` | 저해상도로 N 프레임 돌려 보고 프레임별 리포트를 돌려준다. |  |
| [`reset_simulation`](#reset_simulation) | `run` | 시뮬 캐시를 버리고 처음 상태로 돌린다. 버린 메모리를 돌려준다. | ✓ |
| [`sim_memory`](#sim_memory) | `run` | 시뮬 메모리를 오브젝트별·서브데이터별로 갈라 준다. |  |
| [`write_sim_cache`](#write_sim_cache) | `cache` | 시뮬을 프레임 범위만큼 돌리면서 프레임마다 .sim 파일로 굽는다. | ✓ |
| [`sim_cache_status`](#sim_cache_status) | `cache` | 이 시뮬의 캐시 상태 — 메모리 캐시와 디스크의 .sim 파일 양쪽. |  |
| [`validate_simulation`](#validate_simulation) | `check` | 돌리기 전에 시뮬 셋업을 점검하고, 무엇이 빠졌고 어떻게 고치는지 돌려준다. |  |

## 모듈별 상세

### `setup`

시뮬레이션 네트워크를 짓는 툴.

#### create_dopnet

```python
create_dopnet(parent: str, name: str, comment: str, gravity: float = -9.81, start_frame: int | None = None, substeps: int | None = None, cache_size_mb: int | None = None)
```

빈 DOP 네트워크를 만들고 중력·머지·출력을 이어 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | dopnet 을 담을 네트워크. 보통 /obj |
| `name` | `str` | 필수 | dopnet 이름. 무엇을 시뮬하는지 드러나게. 예: castle_collapse_sim |
| `comment` | `str` | 필수 | 이 시뮬이 무엇을 위한 것인지. 필수. 씬에 저장되므로 영어로. |
| `gravity` | `float` | `-9.81` | 중력 가속도 Y 성분. 0 이면 중력 노드를 만들지 않는다. |
| `start_frame` | `int \| None` | `None` | 시뮬 시작 프레임. 생략하면 dopnet 기본값(1). |
| `substeps` | `int \| None` | `None` | 프레임당 서브스텝. 생략하면 1. 관통이 생기면 올린다. |
| `cache_size_mb` | `int \| None` | `None` | 시뮬 캐시 상한(MB). 생략하면 기본값(5000). |

#### add_dop_object

```python
add_dop_object(dopnet: str, source_object: str, object_type: str, comment: str, name: str | None = None, solver_type: str | None = None, parms: dict[str, Any] | None = None, create_import: bool = True)
```

/obj 의 지오메트리를 시뮬에 편입시키고, 만든 것을 전부 설명해 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. 예: /obj/castle_collapse_sim |
| `source_object` | `str` | 필수 | 시뮬에 넣을 /obj 아래 geo 노드. 예: /obj/falling_box |
| `object_type` | `str` | 필수 | DOP 오브젝트 타입. rbdobject(강체), staticobject(충돌체), rbdpackedobject(패킹된 조각들), clothobject::2.0(천), wireobject(와이어), sandobject(모래), smokeobject(스모크 컨테이너), popobject(파티클), vellumobject(벨럼) 등. |
| `comment` | `str` | 필수 | 이 오브젝트가 시뮬에서 무슨 역할인지. 필수. 영어로. 예: "Tower blocks, active rigid bodies" |
| `name` | `str \| None` | `None` | DOP 노드 이름. 역할이 드러나게. 예: tower_blocks_rbd |
| `solver_type` | `str \| None` | `None` | 솔버를 직접 지정할 때만. 생략하면 표에서 고른다. 예: bulletrbdsolver (rigidbodysolver 대신 불릿을 쓰고 싶을 때) |
| `parms` | `dict[str, Any] \| None` | `None` | DOP 오브젝트 노드에 걸 파라미터. 예: {"divsize": 0.05} |
| `create_import` | `bool` | `True` | 원본 오브젝트에 DOP Import SOP 을 만들지. 정적 충돌체는 시뮬 결과를 되읽을 필요가 없으므로 자동으로 꺼진다. |

#### add_dop_force

```python
add_dop_force(dopnet: str, force_type: str, comment: str, name: str | None = None, parms: dict[str, Any] | None = None, affect_objects: str | None = None)
```

시뮬 전체에 걸리는 힘을 체인 끝에 끼워 넣고 무엇이 바뀌었는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `force_type` | `str` | 필수 | DOP 힘 노드 타입. gravity, windforce, drag, fan, pointforce, vortexforce, magnetforce, uniformforce 등. |
| `comment` | `str` | 필수 | 이 힘이 무엇을 하는지. 필수. 영어로. 예: "Side wind pushing the smoke east" |
| `name` | `str \| None` | `None` | 노드 이름. 예: side_wind |
| `parms` | `dict[str, Any] \| None` | `None` | 힘 노드 파라미터. 벡터는 성분 이름이 따로다 — windforce 는 velx/vely/velz, uniformforce 는 forcex/forcey/forcez. 예: {"velx": 5.0}. 이름이 틀리면 무엇이 있는지 알려 준다. |
| `affect_objects` | `str \| None` | `None` | 이 힘을 받을 오브젝트 이름 패턴. 생략하면 전부. 예: "tower_*" |

### `objects`

시뮬레이션 안을 들여다보는 툴 — 오브젝트, 릴레이션십, 솔버 구성.

#### list_dop_objects

```python
list_dop_objects(dopnet: str, pattern: str = '*')
```

쿡된 시뮬 안의 오브젝트들과 각각의 상태.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. 예: /obj/castle_collapse_sim |
| `pattern` | `str` | `'*'` | 오브젝트 이름 패턴. 예: "tower_*". 기본은 전부. |

#### dop_object_info

```python
dop_object_info(dopnet: str, name: str)
```

시뮬 오브젝트 하나를 깊게. 레코드, 서브데이터, 만든 노드, 솔버.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `name` | `str` | 필수 | 오브젝트 이름. list_dop_objects 로 확인한 이름. |

#### dop_relationships

```python
dop_relationships(dopnet: str)
```

시뮬의 릴레이션십 — 무엇이 무엇에 영향을 주고 어떤 컨스트레인트가 있는지.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |

#### simulation_info

```python
simulation_info(dopnet: str)
```

시뮬 구성 전체 — 솔버, 타임스텝, 서브스텝, 캐시 설정, 현재 상태.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |

#### dop_node_info

```python
dop_node_info(path: str)
```

dopnet 안의 DOP 노드 하나가 실제로 시뮬에 참여하는지와 그 연결.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | DOP 노드 경로. 예: /obj/castle_collapse_sim/rbd_solver |

### `fields`

볼륨 필드를 통계로 읽는 툴.

#### list_dop_fields

```python
list_dop_fields(dopnet: str, name: str, include_temp: bool = False)
```

시뮬 오브젝트가 가진 볼륨 필드 목록 — 종류, 해상도, 복셀 수, 메모리.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `name` | `str` | 필수 | 오브젝트 이름. 예: smoke_container |
| `include_temp` | `bool` | `False` | 솔버 내부 임시 필드(__tempfield_*)도 포함할지. |

#### field_stats

```python
field_stats(dopnet: str, name: str, field: str, deep: bool = False, bins: int = 16)
```

필드 하나의 값 통계. 복셀을 통째로 넘기지 않는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `name` | `str` | 필수 | 오브젝트 이름. 예: smoke_container |
| `field` | `str` | 필수 | 필드 이름. 예: density, temperature, vel, pressure |
| `deep` | `bool` | `False` | 복셀을 다 읽어 히스토그램과 NaN 개수까지 낼지. |
| `bins` | `int` | `16` | deep=True 일 때 히스토그램 구간 수. |

#### field_data_types

```python
field_data_types(dopnet: str, name: str)
```

오브젝트의 서브데이터를 종류별로 갈라 준다 — 필드, 솔버, 힘, 그 밖.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `name` | `str` | 필수 | 오브젝트 이름. |

### `run`

시뮬을 실제로 돌려 보고 무슨 일이 일어났는지 돌려주는 툴.

#### step_simulation

```python
step_simulation(dopnet: str, frames: int = 1, deep_fields: bool = False, speed_limit: float = 100000.0)
```

현재 프레임에서 N 프레임 진행시키고 프레임별 상태를 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `frames` | `int` | `1` | 진행할 프레임 수. 1이면 다음 한 프레임만. |
| `deep_fields` | `bool` | `False` | 필드를 복셀까지 읽어 히스토그램과 NaN 개수를 낼지. 필드가 크면 느려진다. 기본은 싼 min/max/mean 만. |
| `speed_limit` | `float` | `100000.0` | 점 속도가 이 값을 넘으면 발산으로 표시한다. |

#### test_simulation

```python
test_simulation(dopnet: str, start: int = 1, end: int = 10, resolution_factor: float = 2.0, substeps: int | None = None, deep_fields: bool = False, speed_limit: float = 100000.0)
```

저해상도로 N 프레임 돌려 보고 프레임별 리포트를 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `start` | `int` | `1` | 시작 프레임. |
| `end` | `int` | `10` | 끝 프레임. start 와 가까울수록 빨리 끝난다. |
| `resolution_factor` | `float` | `2.0` | 복셀/파티클 간격을 몇 배로 키울지. 1이면 원래 해상도 그대로 돈다. |
| `substeps` | `int \| None` | `None` | 시험 주행 동안 쓸 서브스텝. 생략하면 그대로. |
| `deep_fields` | `bool` | `False` | 필드를 복셀까지 읽을지. 저해상도라 대개 감당된다. |
| `speed_limit` | `float` | `100000.0` | 점 속도가 이 값을 넘으면 발산으로 표시한다. |

#### reset_simulation

```python
reset_simulation(dopnet: str, cook_first_frame: bool = True)
```

시뮬 캐시를 버리고 처음 상태로 돌린다. 버린 메모리를 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `cook_first_frame` | `bool` | `True` | 리셋한 뒤 시작 프레임을 한 번 쿡할지. 켜면 리셋 직후의 초기 상태를 바로 확인할 수 있다. |

#### sim_memory

```python
sim_memory(dopnet: str, top: int = 15)
```

시뮬 메모리를 오브젝트별·서브데이터별로 갈라 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `top` | `int` | `15` | 가장 큰 서브데이터를 몇 개까지 보여줄지. |

### `cache`

시뮬 결과를 .sim 파일로 굽고 상태를 읽는 툴.

#### write_sim_cache

```python
write_sim_cache(dopnet: str, directory: str, start: int, end: int, comment: str, filename: str | None = None, compress: bool = True, deep_fields: bool = False)
```

시뮬을 프레임 범위만큼 돌리면서 프레임마다 .sim 파일로 굽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `directory` | `str` | 필수 | .sim 파일을 담을 디렉토리. 없으면 만든다. $HIP 같은 변수를 그대로 쓴다 - File DOP 에 원문으로 걸려 씬을 옮겨도 풀린다. |
| `start` | `int` | 필수 | 시작 프레임. |
| `end` | `int` | 필수 | 끝 프레임. |
| `comment` | `str` | 필수 | File DOP 에 달 코멘트. 필수. 씬에 저장되므로 영어로. 예: "Bake tower collapse, frames 1-120" |
| `filename` | `str \| None` | `None` | 파일 이름 패턴. 생략하면 "<dopnet 이름>.$SF.sim". 프레임 번호 자리에 $SF(시뮬 프레임)를 넣어야 한다. |
| `compress` | `bool` | `True` | .sim 파일을 압축할지. 끄면 커지지만 읽기가 조금 빠르다. |
| `deep_fields` | `bool` | `False` | 프레임 리포트에 필드 히스토그램까지 넣을지. |

#### sim_cache_status

```python
sim_cache_status(dopnet: str, start: int | None = None, end: int | None = None)
```

이 시뮬의 캐시 상태 — 메모리 캐시와 디스크의 .sim 파일 양쪽.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
| `start` | `int \| None` | `None` | 확인할 시작 프레임. 생략하면 플레이바 시작. |
| `end` | `int \| None` | `None` | 확인할 끝 프레임. 생략하면 플레이바 끝. |

### `check`

돌리기 전에 무엇이 빠졌는지 찾는 툴.

#### validate_simulation

```python
validate_simulation(dopnet: str)
```

돌리기 전에 시뮬 셋업을 점검하고, 무엇이 빠졌고 어떻게 고치는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `dopnet` | `str` | 필수 | DOP 네트워크 경로. |
