# houdini_mcp_mat

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `houdini_mcp_mat.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 20개 |
| 모듈 (`TOOL_MODULES`) | `build`, `query`, `assign`, `texture`, `color`, `preset` |

## 개요

```text
머티리얼·룩데브 전문 툴 팩.

셰이더를 만들고, 잇고, 할당하고, 텍스처를 붙이는 것을 담는다. 노드를 만들고
잇는 데서 끝내지 않고 Houdini 22 에 번들된 전문 라이브러리로 결과를 확인한다.

    MaterialX 1.39.5   셰이더 그래프 검증과 프리셋 저장 포맷
    OpenImageIO 2.5    텍스처 파일을 실제로 열어 해상도·채널·통계 확인
    pxr (OpenUSD)      UsdShade 로 실제 바인딩 질의
    PyOpenColorIO 2.5  컬러스페이스 목록을 OCIO 설정에서

    build      머티리얼·셰이더 노드 저작과 연결
    query      머티리얼 조회·그래프 구조·MaterialX 검증
    assign     머티리얼 할당과 실제 바인딩 확인 (SOP 어트리뷰트 / LOP UsdShade)
    texture    텍스처 부착과 OIIO 검사
    color      OCIO 컬러스페이스 조회와 지정
    preset     MaterialX 문서로 저장·불러오기

`houdini_mcp_lop` 와의 경계: **머티리얼 자체는 이 팩, 스테이지 일반은 lop.**
이 팩이 USD 를 건드리는 것은 UsdShade(머티리얼·바인딩)에 한정한다. 프림 조회,
레이어 스택, 컴포지션, 라이트, 배리언트는 lop 팩이 맡는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`create_material`](#create_material) | `build` | 머티리얼을 만든다. 셰이더 노드와 출력 배선까지 갖춘 채로 나온다. | ✓ |
| [`connect_shader`](#connect_shader) | `build` | 셰이더 노드의 출력을 다른 셰이더의 입력에 **이름으로** 잇는다. | ✓ |
| [`disconnect_shader`](#disconnect_shader) | `build` | 셰이더 입력 하나를 이름으로 끊는다. | ✓ |
| [`set_material_parms`](#set_material_parms) | `build` | 셰이더 파라미터를 건다. 색·벡터는 리스트로 한 번에 준다. | ✓ |
| [`shader_inputs`](#shader_inputs) | `build` | 셰이더 노드가 받을 수 있는 입력과 낼 수 있는 출력을 타입과 함께 준다. |  |
| [`list_materials`](#list_materials) | `query` | 씬의 머티리얼을 나열한다. 코멘트와 계열을 함께 준다. |  |
| [`material_info`](#material_info) | `query` | 머티리얼 하나를 전부 본다 — 셰이더, 연결, 텍스처, 이 머티리얼을 거는 노드. |  |
| [`shader_graph`](#shader_graph) | `query` | 머티리얼 안의 셰이더 그래프 구조 — 노드와 연결. |  |
| [`validate_material`](#validate_material) | `query` | 머티리얼이 실제로 유효한지 검증한다. MaterialX 라이브러리가 판정한다. |  |
| [`assign_material`](#assign_material) | `assign` | 머티리얼을 지오메트리에 걸고, **실제로 걸렸는지 확인해서** 돌려준다. | ✓ |
| [`list_assignments`](#list_assignments) | `assign` | 무엇에 어떤 머티리얼이 걸려 있는지 본다. 파라미터가 아니라 결과를 읽는다. |  |
| [`texture_info`](#texture_info) | `texture` | 텍스처 파일을 실제로 열어 해상도·채널·비트뎁스·컬러스페이스를 읽는다. |  |
| [`assign_texture`](#assign_texture) | `texture` | 텍스처를 셰이더 입력에 붙인다. 붙이기 전에 **파일을 열어 확인한다.** | ✓ |
| [`reload_textures`](#reload_textures) | `texture` | 텍스처 캐시를 비운다. 디스크에서 텍스처를 바꿨을 때 쓴다. | ✓ |
| [`list_color_spaces`](#list_color_spaces) | `color` | 쓸 수 있는 컬러스페이스를 OCIO 설정에서 읽어 돌려준다. |  |
| [`texture_parm_colorspaces`](#texture_parm_colorspaces) | `color` | 텍스처 노드의 컬러스페이스 파라미터가 실제로 받는 값 목록. |  |
| [`set_color_space`](#set_color_space) | `color` | 텍스처 노드의 컬러스페이스를 건다. 메뉴에 없는 값이면 거절한다. | ✓ |
| [`save_material`](#save_material) | `preset` | 머티리얼을 MaterialX 문서(.mtlx)로 저장하고, 저장한 것을 다시 읽어 검증한다. |  |
| [`list_presets`](#list_presets) | `preset` | 디렉토리의 MaterialX 문서를 나열한다. 안에 무엇이 들었는지까지. |  |
| [`load_material`](#load_material) | `preset` | MaterialX 문서를 읽어 머티리얼로 세운다. save_material 의 반대다. | ✓ |

## 모듈별 상세

### `build`

머티리얼과 셰이더 그래프를 만드는 툴.

#### create_material

```python
create_material(parent: str, name: str, comment: str, kind: str = 'materialx')
```

머티리얼을 만든다. 셰이더 노드와 출력 배선까지 갖춘 채로 나온다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 머티리얼을 담을 네트워크. 예: /mat, /stage/materiallibrary1 |
| `name` | `str` | 필수 | 머티리얼 이름. 역할이 드러나게. 예: wall_stone |
| `comment` | `str` | 필수 | 이 머티리얼이 무엇을 위한 것인지. 필수. 영어로. 예: "Weathered sandstone for the castle wall" |
| `kind` | `str` | `'materialx'` | materialx / karma / usdpreview / principled 중 하나. |

#### connect_shader

```python
connect_shader(source: str, target: str, to_input: str, from_output: str = 'out')
```

셰이더 노드의 출력을 다른 셰이더의 입력에 **이름으로** 잇는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `source` | `str` | 필수 | 값을 내보내는 노드. 예: /mat/wall_stone/base_color_tex |
| `target` | `str` | 필수 | 값을 받는 노드. 예: /mat/wall_stone/mtlxstandard_surface |
| `to_input` | `str` | 필수 | target 의 입력 이름. 예: base_color, specular_roughness |
| `from_output` | `str` | `'out'` | source 의 출력 이름. MaterialX 노드는 대개 "out" 이다. |

#### disconnect_shader

```python
disconnect_shader(target: str, to_input: str)
```

셰이더 입력 하나를 이름으로 끊는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | 입력을 끊을 노드 경로. |
| `to_input` | `str` | 필수 | 끊을 입력 이름. 예: base_color |

#### set_material_parms

```python
set_material_parms(path: str, parms: dict[str, Any])
```

셰이더 파라미터를 건다. 색·벡터는 리스트로 한 번에 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 셰이더 노드 경로. 예: /mat/wall_stone/mtlxstandard_surface |
| `parms` | `dict[str, Any]` | 필수 | 이름과 값. 예: {"base_color": [0.4, 0.25, 0.1], "specular_roughness": 0.55, "metalness": 0.0} |

#### shader_inputs

```python
shader_inputs(path: str)
```

셰이더 노드가 받을 수 있는 입력과 낼 수 있는 출력을 타입과 함께 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 셰이더 노드 경로. |

### `query`

머티리얼을 들여다보고 검증하는 툴.

#### list_materials

```python
list_materials(root: str = '/', lop: str = '', max_results: int = 100)
```

씬의 머티리얼을 나열한다. 코멘트와 계열을 함께 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `root` | `str` | `'/'` | 어디부터 훑을지. 기본은 씬 전체. 예: /mat, /obj/castle |
| `lop` | `str` | `''` | LOP 노드 경로를 주면 USD 머티리얼을 대신 읽는다. 예: /stage/assign_wood |
| `max_results` | `int` | `100` | 돌려줄 최대 개수. |

#### material_info

```python
material_info(path: str)
```

머티리얼 하나를 전부 본다 — 셰이더, 연결, 텍스처, 이 머티리얼을 거는 노드.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 머티리얼 노드 경로. 예: /mat/wall_stone |

#### shader_graph

```python
shader_graph(path: str, max_nodes: int = 100)
```

머티리얼 안의 셰이더 그래프 구조 — 노드와 연결.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 머티리얼 노드 경로. |
| `max_nodes` | `int` | `100` | 돌려줄 노드 수 상한. |

#### validate_material

```python
validate_material(path: str)
```

머티리얼이 실제로 유효한지 검증한다. MaterialX 라이브러리가 판정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 머티리얼 노드 경로. 예: /mat/wall_stone |

### `assign`

머티리얼을 지오메트리에 걸고, 실제로 걸렸는지 확인하는 툴.

#### assign_material

```python
assign_material(target: str, material: str, comment: str, group: str = '', prim_pattern: str = '')
```

머티리얼을 지오메트리에 걸고, **실제로 걸렸는지 확인해서** 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | 머티리얼을 걸 노드. SOP / LOP / OBJ 경로. |
| `material` | `str` | 필수 | 머티리얼 경로. VOP 노드 경로를 주면 LOP 에서는 USD 프림 경로로 알아서 바꾼다. 예: /mat/wall_stone, /materials/wall_stone |
| `comment` | `str` | 필수 | 만들어지는 할당 노드에 달 코멘트. 필수. 영어로. 예: "Stone material on the wall body" |
| `group` | `str` | `''` | SOP 일 때만. 프리미티브 그룹이나 패턴. 비우면 전부. |
| `prim_pattern` | `str` | `''` | LOP 일 때만. 프림 패턴. 비우면 %type:Mesh. |

#### list_assignments

```python
list_assignments(path: str, max_prims: int = 200)
```

무엇에 어떤 머티리얼이 걸려 있는지 본다. 파라미터가 아니라 결과를 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 또는 LOP 노드 경로. |
| `max_prims` | `int` | `200` | LOP 일 때 훑을 프림 수 상한. |

### `texture`

텍스처를 붙이고, 붙이기 전에 **파일을 실제로 열어 확인하는** 툴.

#### texture_info

```python
texture_info(file: str, usage: str = '', stats: bool = False)
```

텍스처 파일을 실제로 열어 해상도·채널·비트뎁스·컬러스페이스를 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file` | `str` | 필수 | 텍스처 경로. $HIP 같은 Houdini 변수를 써도 된다. UDIM 은 <UDIM> 토큰으로. 예: $HIP/tex/wall_basecolor.<UDIM>.exr |
| `usage` | `str` | `''` | color / scalar / normal 중 하나. 비우면 판정하지 않는다. |
| `stats` | `bool` | `False` | True 면 픽셀 통계(최소·최대·평균)까지 계산한다. 큰 파일은 느리다. |

#### assign_texture

```python
assign_texture(material: str, to_input: str, file: str, comment: str, usage: str = '', colorspace: str = '', name: str = '')
```

텍스처를 셰이더 입력에 붙인다. 붙이기 전에 **파일을 열어 확인한다.**

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `material` | `str` | 필수 | 머티리얼 노드 경로. 예: /mat/wall_stone |
| `to_input` | `str` | 필수 | 붙일 입력 이름. 예: base_color, specular_roughness, normal |
| `file` | `str` | 필수 | 텍스처 경로. UDIM 은 <UDIM> 토큰으로. |
| `comment` | `str` | 필수 | 만들어지는 텍스처 노드의 코멘트. 필수. 영어로. 예: "Sandstone base color, 4K sRGB" |
| `usage` | `str` | `''` | color / scalar / normal. 주면 파일이 용도에 맞는지 판정한다. |
| `colorspace` | `str` | `''` | mtlximage 의 filecolorspace 에 걸 값. 비우면 건드리지 않는다. 쓸 수 있는 값은 list_color_spaces 로 본다. |
| `name` | `str` | `''` | 만들 텍스처 노드 이름. 비우면 입력 이름에서 만든다. |

#### reload_textures

```python
reload_textures()
```

텍스처 캐시를 비운다. 디스크에서 텍스처를 바꿨을 때 쓴다.

### `color`

컬러 매니지먼트 툴. 목록을 하드코딩하지 않고 OCIO 설정에서 읽는다.

#### list_color_spaces

```python
list_color_spaces(pattern: str = '')
```

쓸 수 있는 컬러스페이스를 OCIO 설정에서 읽어 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `pattern` | `str` | `''` | 이름이나 별칭에 이 문자열이 든 것만. 비우면 전부. |

#### texture_parm_colorspaces

```python
texture_parm_colorspaces(path: str = '', parm: str = '')
```

텍스처 노드의 컬러스페이스 파라미터가 실제로 받는 값 목록.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | `''` | 텍스처 노드 경로. 비우면 임시 mtlximage 로 기본 메뉴를 본다. |
| `parm` | `str` | `''` | 파라미터 이름. 비우면 filecolorspace 등을 자동으로 찾는다. |

#### set_color_space

```python
set_color_space(path: str, colorspace: str, parm: str = '')
```

텍스처 노드의 컬러스페이스를 건다. 메뉴에 없는 값이면 거절한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 텍스처 노드 경로. 예: /mat/wall_stone/base_color_tex |
| `colorspace` | `str` | 필수 | 걸 값. 예: srgb_texture, lin_rec709, Raw |
| `parm` | `str` | `''` | 파라미터 이름. 비우면 filecolorspace 등을 자동으로 찾는다. |

### `preset`

머티리얼을 파일로 저장하고 다시 읽는 툴. 포맷은 **MaterialX 문서**다.

#### save_material

```python
save_material(material: str, file: str)
```

머티리얼을 MaterialX 문서(.mtlx)로 저장하고, 저장한 것을 다시 읽어 검증한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `material` | `str` | 필수 | 머티리얼 노드 경로. 예: /mat/wall_stone |
| `file` | `str` | 필수 | 저장할 경로. 확장자가 없으면 .mtlx 를 붙인다. 예: $HIP/materials/wall_stone.mtlx |

#### list_presets

```python
list_presets(directory: str = '$HIP/materials')
```

디렉토리의 MaterialX 문서를 나열한다. 안에 무엇이 들었는지까지.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `directory` | `str` | `'$HIP/materials'` | 훑을 디렉토리. 예: $HIP/materials |

#### load_material

```python
load_material(file: str, parent: str, name: str, comment: str, nodegraph: str = '')
```

MaterialX 문서를 읽어 머티리얼로 세운다. save_material 의 반대다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file` | `str` | 필수 | 읽을 MaterialX 문서. 예: $HIP/materials/wall_stone.mtlx |
| `parent` | `str` | 필수 | 머티리얼을 만들 네트워크. 예: /mat |
| `name` | `str` | 필수 | 만들 머티리얼 이름. 역할이 드러나게. 영어로. |
| `comment` | `str` | 필수 | 이 머티리얼이 무엇인지. 필수. 영어로. |
| `nodegraph` | `str` | `''` | 문서에 노드그래프가 여럿일 때 고를 이름. 비우면 첫 번째. |
