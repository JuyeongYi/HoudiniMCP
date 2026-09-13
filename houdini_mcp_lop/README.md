# houdini_mcp_lop

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_lop.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 22개 |
| 모듈 (`TOOL_MODULES`) | `stage`, `attrs`, `layers`, `composition`, `lights`, `check` |

## 개요

```text
LOPs / Solaris / USD 전문 툴 팩.

이 팩은 USD 를 **LOP 노드의 파라미터가 아니라 컴포지션이 끝난 스테이지로**
다룬다. `hou.LopNode.stage()` 가 주는 `pxr.Usd.Stage` 를 직접 질의하므로,
서브레이어·레퍼런스·페이로드·배리언트·인헤릿이 겹친 뒤의 **실제 값**을 본다.
노드 파라미터를 읽는 방식은 컴포지션을 무시하기 때문에 틀린 답을 준다.

    stage        스테이지 조회 - 요약, 계층, 검색, 프림 상세
    attrs        USD 어트리뷰트 읽기·쓰기
    layers       레이어 스택과 값의 출처 추적 (prim_origin)
    composition  컴포지션 아크 - 레퍼런스·페이로드·서브레이어·배리언트
    lights       UsdLux 라이트
    check        스테이지 검증

usdcommon 은 툴이 없는 공용 헬퍼라 TOOL_MODULES 에 넣지 않는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`stage_info`](#stage_info) | `stage` | 스테이지 요약 - 프림 수, 타입별 분포, 레이어 수, up axis, 단위, 시간 범위. |  |
| [`list_prims`](#list_prims) | `stage` | 계층을 깊이·개수 제한을 두고 훑는다. |  |
| [`find_prims`](#find_prims) | `stage` | Houdini 의 프림 패턴으로 프림을 찾는다. |  |
| [`prim_info`](#prim_info) | `stage` | 프림 하나의 전부 - 타입, 스키마, 가시성, 바운드, 머티리얼 바인딩, 배리언트. |  |
| [`prim_stats`](#prim_stats) | `stage` | 프림 아래의 통계 - 타입별 개수, 지오메트리 양, kind, 페이로드 로드 상태. |  |
| [`list_usd_attributes`](#list_usd_attributes) | `attrs` | 프림의 어트리뷰트 목록 - 이름, 타입, 값이 걸렸는지, 시간에 따라 변하는지. |  |
| [`get_usd_attribute`](#get_usd_attribute) | `attrs` | 어트리뷰트 값을 컴포지션이 끝난 뒤의 값으로 읽는다. |  |
| [`set_usd_attribute`](#set_usd_attribute) | `attrs` | 어트리뷰트에 값을 건다. `pythonscript` LOP 을 끼워 넣는 방식이다. | ✓ |
| [`layer_stack`](#layer_stack) | `layers` | 스테이지의 루트 레이어 스택 - 어떤 레이어가 어떤 순서로 겹쳐 있는가. |  |
| [`layer_contents`](#layer_contents) | `layers` | 레이어의 실제 내용을 USDA 텍스트로 본다. |  |
| [`prim_origin`](#prim_origin) | `layers` | 이 프림(또는 어트리뷰트) 값이 **어느 레이어의 어느 아크에서 왔는가**. |  |
| [`composition_arcs`](#composition_arcs) | `composition` | 이 프림에 걸린 컴포지션 아크 전부 - 무엇이 어디서 끌려왔는가. |  |
| [`list_variants`](#list_variants) | `composition` | 프림의 배리언트 셋과 각각의 선택지, 현재 선택. |  |
| [`set_variant`](#set_variant) | `composition` | 배리언트를 고른다. `setvariant` LOP 을 끼워 넣는다. | ✓ |
| [`add_reference`](#add_reference) | `composition` | 레퍼런스·페이로드·인헤릿·스페셜라이즈를 건다. `reference` LOP 을 끼워 넣는다. | ✓ |
| [`add_sublayer`](#add_sublayer) | `composition` | USD 파일을 서브레이어로 깐다. `sublayer` LOP 을 끼워 넣는다. | ✓ |
| [`list_lights`](#list_lights) | `lights` | 스테이지의 라이트 전부 - 타입, 세기, 색, 위치. |  |
| [`light_info`](#light_info) | `lights` | 라이트 하나의 전부 - 세기, 색, 모양, 셰이핑, 그림자, 변환. |  |
| [`create_light`](#create_light) | `lights` | UsdLux 라이트를 만든다. | ✓ |
| [`create_light_rig`](#create_light_rig) | `lights` | 3점 조명(key / fill / rim)과 환경 돔을 한 번에 만든다. | ✓ |
| [`set_light`](#set_light) | `lights` | 이미 있는 라이트 프림의 속성을 바꾼다. `pythonscript` LOP 을 끼워 넣는다. | ✓ |
| [`validate_stage`](#validate_stage) | `check` | 스테이지를 훑어 흔한 문제를 찾는다 - 깨진 에셋 경로, 빈 프림, 바인딩 누락. |  |

## 모듈별 상세

### `stage`

컴포지션이 끝난 USD 스테이지를 조회하는 툴들.

#### stage_info

```python
stage_info(lop: str = DEFAULT_LOP, frame: float | None = None)
```

스테이지 요약 - 프림 수, 타입별 분포, 레이어 수, up axis, 단위, 시간 범위.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 경로. LOP 네트워크(기본값 /stage)를 주면 디스플레이 노드의 스테이지를 본다. |
| `frame` | `float \| None` | `None` | 이 프레임에서 쿡한 스테이지를 본다. 생략하면 현재 프레임. |

#### list_prims

```python
list_prims(lop: str = DEFAULT_LOP, root: str = '/', depth: int = 2, limit: int = 200, include_inactive: bool = False, frame: float | None = None)
```

계층을 깊이·개수 제한을 두고 훑는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `root` | `str` | `'/'` | 순회를 시작할 프림 경로. "/" 는 스테이지 전체. |
| `depth` | `int` | `2` | root 아래로 몇 단계까지 내려갈지. 1 이면 바로 아래 자식만. |
| `limit` | `int` | `200` | 돌려줄 프림 수 상한. 스테이지는 크므로 반드시 건다. |
| `include_inactive` | `bool` | `False` | True 면 비활성 프림도 포함한다. |
| `frame` | `float \| None` | `None` | 이 프레임에서 쿡한 스테이지를 본다. |

#### find_prims

```python
find_prims(lop: str = DEFAULT_LOP, pattern: str = '/**', limit: int = 200, traversal: str = 'default')
```

Houdini 의 프림 패턴으로 프림을 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `pattern` | `str` | `'/**'` | 프림 패턴. |
| `limit` | `int` | `200` | 돌려줄 프림 수 상한. |
| `traversal` | `str` | `'default'` | 순회 조건. "default"(활성·정의·로드됨), "all"(전부), "defined", "active", "loaded" 중 하나. |

#### prim_info

```python
prim_info(lop: str = DEFAULT_LOP, primpath: str = '/', include_attributes: bool = True, frame: float | None = None)
```

프림 하나의 전부 - 타입, 스키마, 가시성, 바운드, 머티리얼 바인딩, 배리언트.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 프림 경로. 예: /world/ball |
| `include_attributes` | `bool` | `True` | True 면 어트리뷰트 이름과 값이 있는지 여부를 함께 준다. 값 자체는 get_attribute 로 읽는다. |
| `frame` | `float \| None` | `None` | 이 프레임에서 쿡한 스테이지를 본다. |

#### prim_stats

```python
prim_stats(lop: str = DEFAULT_LOP, primpath: str = '/', geometry_counts: bool = True, frame: float | None = None)
```

프림 아래의 통계 - 타입별 개수, 지오메트리 양, kind, 페이로드 로드 상태.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 통계를 낼 프림 경로. "/" 면 스테이지 전체. |
| `geometry_counts` | `bool` | `True` | True 면 점·폴리곤 수까지 센다. 무거우면 끈다. |
| `frame` | `float \| None` | `None` | 이 프레임에서 쿡한 스테이지를 본다. |

### `attrs`

USD 어트리뷰트를 읽고 쓴다.

#### list_usd_attributes

```python
list_usd_attributes(lop: str = DEFAULT_LOP, primpath: str = '/', authored_only: bool = True, frame: float | None = None)
```

프림의 어트리뷰트 목록 - 이름, 타입, 값이 걸렸는지, 시간에 따라 변하는지.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 프림 경로. |
| `authored_only` | `bool` | `True` | True 면 실제로 값이 걸린 것만. False 면 스키마가 정의한 것까지 전부(수십 개가 된다). |
| `frame` | `float \| None` | `None` | 이 프레임에서 쿡한 스테이지를 본다. |

#### get_usd_attribute

```python
get_usd_attribute(lop: str = DEFAULT_LOP, primpath: str = '/', name: str = '', frame: float | None = None, max_array: int = 16)
```

어트리뷰트 값을 컴포지션이 끝난 뒤의 값으로 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 프림 경로. |
| `name` | `str` | `''` | 어트리뷰트 이름. 예: radius, points, inputs:intensity |
| `frame` | `float \| None` | `None` | 이 시각의 값을 읽는다. 생략하면 default 값. |
| `max_array` | `int` | `16` | 배열 값에서 돌려줄 원소 수 상한. |

#### set_usd_attribute

```python
set_usd_attribute(lop: str, primpath: str, name: str, value: UsdValue, comment: str, type_name: str | None = None, frame: float | None = None, node_name: str | None = None)
```

어트리뷰트에 값을 건다. `pythonscript` LOP 을 끼워 넣는 방식이다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 편집의 입력이 될 LOP 노드 경로. 네트워크를 주면 디스플레이 노드. |
| `primpath` | `str` | 필수 | 값을 걸 프림 경로. |
| `name` | `str` | 필수 | 어트리뷰트 이름. 예: radius, inputs:intensity, visibility |
| `value` | `UsdValue` | 필수 | 넣을 값. 벡터와 배열은 리스트로. 예: 2.5, [1,0,0], [[0,0,0],[1,1,1]] |
| `comment` | `str` | 필수 | 이 편집이 왜 필요한지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `type_name` | `str \| None` | `None` | 새 어트리뷰트를 만들 때의 USD 타입. 예: double, float3, token, float3[], asset |
| `frame` | `float \| None` | `None` | 값을 이 시각의 시간 샘플로 건다. 생략하면 default 값. |
| `node_name` | `str \| None` | `None` | 만들 노드 이름. 생략하면 어트리뷰트 이름에서 짓는다. |

### `layers`

레이어 스택과 **값의 출처**.

#### layer_stack

```python
layer_stack(lop: str = DEFAULT_LOP, include_session: bool = False)
```

스테이지의 루트 레이어 스택 - 어떤 레이어가 어떤 순서로 겹쳐 있는가.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `include_session` | `bool` | `False` | True 면 세션 레이어(뷰포트 오버라이드, 솔로, 가시성 토글 등)도 함께 준다. 보통은 볼 필요가 없다. |

#### layer_contents

```python
layer_contents(lop: str = DEFAULT_LOP, identifier: str = '', primpath: str | None = None, max_chars: int = MAX_LAYER_CHARS)
```

레이어의 실제 내용을 USDA 텍스트로 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `identifier` | `str` | `''` | 레이어 identifier. layer_stack 이나 prim_origin 이 돌려준 것을 그대로 넣는다. 비우면 그 LOP 노드의 active layer. |
| `primpath` | `str \| None` | `None` | 이 프림 스펙만 본다. 생략하면 레이어 전체. |
| `max_chars` | `int` | `MAX_LAYER_CHARS` | 돌려줄 텍스트 길이 상한. |

#### prim_origin

```python
prim_origin(lop: str = DEFAULT_LOP, primpath: str = '/', attribute: str | None = None, frame: float | None = None)
```

이 프림(또는 어트리뷰트) 값이 **어느 레이어의 어느 아크에서 왔는가**.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 프림 경로. |
| `attribute` | `str \| None` | `None` | 어트리뷰트 이름을 주면 그 어트리뷰트의 의견 스택을 본다. 생략하면 프림 자체의 스펙 스택. |
| `frame` | `float \| None` | `None` | 어트리뷰트 의견을 이 시각 기준으로 본다. |

### `composition`

컴포지션 아크 - 레퍼런스, 페이로드, 서브레이어, 배리언트, 인헤릿.

#### composition_arcs

```python
composition_arcs(lop: str = DEFAULT_LOP, primpath: str = '/', arc_types: list[str] | None = None, include_ancestral: bool = True)
```

이 프림에 걸린 컴포지션 아크 전부 - 무엇이 어디서 끌려왔는가.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 프림 경로. |
| `arc_types` | `list[str] \| None` | `None` | 이 종류만 본다. 예: ["reference", "payload", "variant"] 생략하면 전부. |
| `include_ancestral` | `bool` | `True` | False 면 상위에서 상속된 아크를 뺀다. 이 프림에 직접 걸린 것만 보고 싶을 때. |

#### list_variants

```python
list_variants(lop: str = DEFAULT_LOP, primpath: str = '/')
```

프림의 배리언트 셋과 각각의 선택지, 현재 선택.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `'/'` | 프림 경로. |

#### set_variant

```python
set_variant(lop: str, primpath: str, variant_set: str, variant: str, comment: str, node_name: str | None = None)
```

배리언트를 고른다. `setvariant` LOP 을 끼워 넣는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 입력이 될 LOP 노드 경로. |
| `primpath` | `str` | 필수 | 배리언트 셋을 가진 프림 경로. |
| `variant_set` | `str` | 필수 | 배리언트 셋 이름. |
| `variant` | `str` | 필수 | 고를 배리언트 이름. |
| `comment` | `str` | 필수 | 왜 이 배리언트인지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `node_name` | `str \| None` | `None` | 만들 노드 이름. 생략하면 배리언트 이름에서 짓는다. |

#### add_reference

```python
add_reference(lop: str, primpath: str, comment: str, file_path: str | None = None, reference_type: str = 'file', source_prim: str | None = None, create_prims: bool = True, node_name: str | None = None)
```

레퍼런스·페이로드·인헤릿·스페셜라이즈를 건다. `reference` LOP 을 끼워 넣는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 입력이 될 LOP 노드 경로. |
| `primpath` | `str` | 필수 | 아크를 걸 프림 경로. 예: /world/props/chair |
| `comment` | `str` | 필수 | 이 아크가 무엇인지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `file_path` | `str \| None` | `None` | 끌어올 USD 파일 경로. file / payload 에만 쓴다. |
| `reference_type` | `str` | `'file'` | "file"(레퍼런스), "payload"(지연 로드), "prim"(같은 스테이지 안의 프림), "inherit", "specialize". |
| `source_prim` | `str \| None` | `None` | file / payload 면 파일 안에서 끌어올 프림 경로(생략하면 defaultPrim). prim / inherit / specialize 면 같은 스테이지 안의 원본 프림 경로이며 반드시 필요하다. |
| `create_prims` | `bool` | `True` | 대상 프림이 없으면 만든다. |
| `node_name` | `str \| None` | `None` | 만들 노드 이름. 생략하면 대상 프림 이름에서 짓는다. |

#### add_sublayer

```python
add_sublayer(lop: str, file_path: str, comment: str, node_name: str | None = None)
```

USD 파일을 서브레이어로 깐다. `sublayer` LOP 을 끼워 넣는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 입력이 될 LOP 노드 경로. |
| `file_path` | `str` | 필수 | 깔 USD 파일 경로. |
| `comment` | `str` | 필수 | 이 레이어가 무엇인지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `node_name` | `str \| None` | `None` | 만들 노드 이름. 생략하면 파일 이름에서 짓는다. |

### `lights`

UsdLux 라이트.

#### list_lights

```python
list_lights(lop: str = DEFAULT_LOP, limit: int = 200)
```

스테이지의 라이트 전부 - 타입, 세기, 색, 위치.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `limit` | `int` | `200` | 돌려줄 라이트 수 상한. |

#### light_info

```python
light_info(lop: str = DEFAULT_LOP, primpath: str = '')
```

라이트 하나의 전부 - 세기, 색, 모양, 셰이핑, 그림자, 변환.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `primpath` | `str` | `''` | 라이트 프림 경로. list_lights 로 찾는다. |

#### create_light

```python
create_light(lop: str, light_type: str, primpath: str, comment: str, intensity: float | None = None, exposure: float | None = None, color: list[float] | None = None, translate: list[float] | None = None, rotate: list[float] | None = None, texture: str | None = None, node_name: str | None = None)
```

UsdLux 라이트를 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 입력이 될 LOP 노드 경로. 네트워크를 주면 디스플레이 노드 뒤에 붙는다. |
| `light_type` | `str` | 필수 | distant, sphere, point, disk, rect, cylinder, dome 중 하나. |
| `primpath` | `str` | 필수 | 만들 라이트 프림 경로. 예: /world/lights/key |
| `comment` | `str` | 필수 | 이 라이트가 무엇을 하는지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `intensity` | `float \| None` | `None` | 세기. |
| `exposure` | `float \| None` | `None` | 노출(스톱). 세기에 2^exposure 가 곱해진다. |
| `color` | `list[float] \| None` | `None` | RGB. 예: [1.0, 0.95, 0.9] |
| `translate` | `list[float] \| None` | `None` | 위치 [x, y, z]. |
| `rotate` | `list[float] \| None` | `None` | 회전 [rx, ry, rz] (도). |
| `texture` | `str \| None` | `None` | 돔/렉트 라이트의 텍스처(HDRI) 파일 경로. |
| `node_name` | `str \| None` | `None` | 만들 노드 이름. 생략하면 프림 이름에서 짓는다. |

#### create_light_rig

```python
create_light_rig(lop: str, comment: str, root: str = '/lights', key_intensity: float = 3.0, fill_intensity: float = 1.0, rim_intensity: float = 2.0, dome_texture: str | None = None, dome_intensity: float = 0.3)
```

3점 조명(key / fill / rim)과 환경 돔을 한 번에 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 입력이 될 LOP 노드 경로. |
| `comment` | `str` | 필수 | 이 리그가 무엇을 비추는지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `root` | `str` | `'/lights'` | 라이트를 담을 프림 경로. 예: /world/lights |
| `key_intensity` | `float` | `3.0` | 키 라이트 세기. |
| `fill_intensity` | `float` | `1.0` | 필 라이트 세기. |
| `rim_intensity` | `float` | `2.0` | 림 라이트 세기. |
| `dome_texture` | `str \| None` | `None` | 환경 돔에 걸 HDRI 파일 경로. 없으면 균일한 색. |
| `dome_intensity` | `float` | `0.3` | 환경 돔 세기. |

#### set_light

```python
set_light(lop: str, primpath: str, comment: str, properties: dict[str, Any] | None = None, node_name: str | None = None)
```

이미 있는 라이트 프림의 속성을 바꾼다. `pythonscript` LOP 을 끼워 넣는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | 필수 | 입력이 될 LOP 노드 경로. |
| `primpath` | `str` | 필수 | 고칠 라이트 프림 경로. |
| `comment` | `str` | 필수 | 왜 이렇게 바꾸는지. 노드 코멘트로 남는다. 영어로 쓴다. |
| `properties` | `dict[str, Any] \| None` | `None` | 속성 이름과 값. 예: {"intensity": 5.0, "color": [1, 0.9, 0.8]} |
| `node_name` | `str \| None` | `None` | 만들 노드 이름. 생략하면 프림 이름에서 짓는다. |

### `check`

스테이지 검증 - 렌더를 걸기 전에 무엇이 빠졌는지 찾는다.

#### validate_stage

```python
validate_stage(lop: str = DEFAULT_LOP, check_materials: bool = True, check_render: bool = True)
```

스테이지를 훑어 흔한 문제를 찾는다 - 깨진 에셋 경로, 빈 프림, 바인딩 누락.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `lop` | `str` | `DEFAULT_LOP` | LOP 노드 또는 LOP 네트워크 경로. |
| `check_materials` | `bool` | `True` | 머티리얼 바인딩이 없는 지오메트리를 찾는다. 머티리얼 자체를 만들고 고치는 것은 houdini_mcp_mat 의 일이다. |
| `check_render` | `bool` | `True` | 렌더 설정과 카메라가 있는지 본다. 렌더를 실제로 거는 것은 houdini_mcp_render 의 일이다. |
