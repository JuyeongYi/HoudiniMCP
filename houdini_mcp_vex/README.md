# houdini_mcp_vex

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `houdini_mcp_vex.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 8개 |
| 모듈 (`TOOL_MODULES`) | `validate`, `wrangle`, `reference` |

## 개요

```text
VEX 전문 툴 팩.

VEX 코드를 쓰고, **컴파일해 보고**, 진단한다. 핵심은 검증에 노드를 쓰지 않는
것이다. Houdini 는 VEX 컴파일러를 `$HFS/bin/vcc` 에 실행 파일로 갖고 있으므로,
씬을 건드리지 않고 줄·열 번호까지 정확한 진단을 받을 수 있다.

    compiler   vcc 발견·호출·진단 파싱 (툴 없음)
    snippet    wrangle 의 @어트리뷰트 문법을 순수 VEX 로 옮기는 번역기 (툴 없음)
    validate   validate_vex, wrangle_attribs - 노드를 만들지 않는 검증
    wrangle    create_wrangle, update_wrangle, list_wrangles, diagnose_wrangle
    reference  list_vex_contexts, vex_function_info - VEX 언어 자체의 레퍼런스

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다. compiler 와
snippet 은 툴이 없으므로 목록에 없다 - 툴 모듈이 알아서 import 한다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`validate_vex`](#validate_vex) | `validate` | wrangle 코드를 컴파일해서 검증한다. 노드를 만들지 않고 씬도 안 건드린다. |  |
| [`wrangle_attribs`](#wrangle_attribs) | `validate` | 코드가 읽고 쓰는 어트리뷰트를 뽑고, 입력에 실제로 있는지 대조한다. |  |
| [`create_wrangle`](#create_wrangle) | `wrangle` | wrangle 노드를 만들고 VEX 코드를 넣는다. 넣기 전에 먼저 컴파일해 본다. | ✓ |
| [`update_wrangle`](#update_wrangle) | `wrangle` | wrangle 의 VEX 코드를 갈아 끼운다. 넣기 전에 먼저 컴파일해 본다. | ✓ |
| [`list_wrangles`](#list_wrangles) | `wrangle` | 범위 안의 wrangle 과 그 코드를 훑는다. |  |
| [`diagnose_wrangle`](#diagnose_wrangle) | `wrangle` | wrangle 하나를 컴파일 에러·쿡 에러·어트리뷰트 세 방향에서 본다. |  |
| [`list_vex_contexts`](#list_vex_contexts) | `reference` | VEX 컨텍스트 목록. 하나를 지정하면 그 컨텍스트의 전역 변수까지 준다. |  |
| [`vex_function_info`](#vex_function_info) | `reference` | VEX 함수의 시그니처를 찾는다. 이름이 정확하지 않으면 비슷한 것을 준다. |  |

## 모듈별 상세

### `validate`

노드를 만들지 않고 VEX 를 검증한다.

#### validate_vex

```python
validate_vex(code: str, mode: str = MODE_SNIPPET, context: str = DEFAULT_CONTEXT, attrib_types: dict[str, str] | None = None, include_dirs: list[str] | None = None)
```

wrangle 코드를 컴파일해서 검증한다. 노드를 만들지 않고 씬도 안 건드린다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `code` | `str` | 필수 | 검증할 코드. mode 에 따라 VEXpression 이거나 순수 VEX 소스다. |
| `mode` | `str` | `MODE_SNIPPET` | "snippet" 이면 wrangle 에 넣는 VEXpression(`@P.y += 1;`)으로 본다. "source" 면 컨텍스트 함수까지 직접 쓴 순수 VEX 파일로 본다. |
| `context` | `str` | `DEFAULT_CONTEXT` | VEX 컨텍스트. wrangle 스니펫은 전부 "cvex" 다. 셰이더 소스를 볼 때만 "surface" 등으로 바꾼다. list_vex_contexts 로 목록을 본다. |
| `attrib_types` | `dict[str, str] \| None` | `None` | 접두사를 쓰지 않은 어트리뷰트의 타입을 직접 지정한다. 예: {"myvec": "vector"}. 주지 않으면 Houdini 와 같은 규칙으로 추론하고, 모르는 이름은 float 로 본다. |
| `include_dirs` | `list[str] \| None` | `None` | `#include "..."` 를 찾을 추가 디렉토리. |

#### wrangle_attribs

```python
wrangle_attribs(code: str, input_path: str | None = None, run_over: str = 'point', attrib_types: dict[str, str] | None = None)
```

코드가 읽고 쓰는 어트리뷰트를 뽑고, 입력에 실제로 있는지 대조한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `code` | `str` | 필수 | wrangle 스니펫. |
| `input_path` | `str \| None` | `None` | 대조할 입력 노드 경로. 보통 wrangle 의 첫 입력이다. 쿡되지 않았으면 쿡한다. |
| `run_over` | `str` | `'point'` | wrangle 이 도는 요소. "point", "prim", "vertex", "detail". 여기서 먼저 찾고 없으면 다른 클래스에서 찾는다. |
| `attrib_types` | `dict[str, str] \| None` | `None` | 접두사를 쓰지 않은 어트리뷰트의 타입 지정. |

### `wrangle`

wrangle 노드를 만들고, 고치고, 찾고, 진단한다.

#### create_wrangle

```python
create_wrangle(parent: str, code: str, comment: str, node_type: str = 'attribwrangle', name: str | None = None, run_over: str = 'point', group: str | None = None, input_path: str | None = None, attrib_types: dict[str, str] | None = None)
```

wrangle 노드를 만들고 VEX 코드를 넣는다. 넣기 전에 먼저 컴파일해 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 부모 네트워크 경로. 예: /obj/geo1 |
| `code` | `str` | 필수 | wrangle 스니펫. `@P.y += 1;` 처럼 `@` 문법을 그대로 쓴다. |
| `comment` | `str` | 필수 | 이 wrangle 이 무엇을 하는지. 필수. 씬 파일에 저장되므로 영어로 쓴다. 예: "Push points up by noise" |
| `node_type` | `str` | `'attribwrangle'` | 만들 노드 타입. attribwrangle, pointwrangle, volumewrangle, deformationwrangle, popwrangle, geometrywrangle, channelwrangle 등. |
| `name` | `str \| None` | `None` | 노드 이름. 역할이 드러나게, 영어로. 생략하면 Houdini 가 정한다. |
| `run_over` | `str` | `'point'` | 도는 요소. "point", "prim", "vertex", "detail". class 파라미터가 있는 노드에만 적용된다. |
| `group` | `str \| None` | `None` | 처리할 그룹 이름. 생략하면 전부. |
| `input_path` | `str \| None` | `None` | 첫 입력으로 연결할 노드 경로. |
| `attrib_types` | `dict[str, str] \| None` | `None` | 접두사를 쓰지 않은 어트리뷰트의 타입 지정. 예: {"myvec": "vector"} |

#### update_wrangle

```python
update_wrangle(path: str, code: str, comment: str | None = None, attrib_types: dict[str, str] | None = None)
```

wrangle 의 VEX 코드를 갈아 끼운다. 넣기 전에 먼저 컴파일해 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | wrangle 노드 경로. |
| `code` | `str` | 필수 | 새 스니펫. |
| `comment` | `str \| None` | `None` | 코멘트도 함께 바꾼다. 하는 일이 달라졌으면 같이 고친다. 씬에 저장되므로 영어로 쓴다. |
| `attrib_types` | `dict[str, str] \| None` | `None` | 접두사를 쓰지 않은 어트리뷰트의 타입 지정. |

#### list_wrangles

```python
list_wrangles(root: str = '/obj', depth: int = 3, contains: str | None = None)
```

범위 안의 wrangle 과 그 코드를 훑는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `root` | `str` | `'/obj'` | 훑기 시작할 경로. |
| `depth` | `int` | `3` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |
| `contains` | `str \| None` | `None` | 코드에 이 문자열이 든 것만. 예: "@Cd" |

#### diagnose_wrangle

```python
diagnose_wrangle(path: str, cook: bool = True)
```

wrangle 하나를 컴파일 에러·쿡 에러·어트리뷰트 세 방향에서 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | wrangle 노드 경로. |
| `cook` | `bool` | `True` | 노드를 쿡해서 실제 에러도 볼지. 무거우면 False 로 둔다. |

### `reference`

VEX 언어 자체의 레퍼런스 — 컨텍스트, 전역 변수, 함수 시그니처.

#### list_vex_contexts

```python
list_vex_contexts(context: str | None = None)
```

VEX 컨텍스트 목록. 하나를 지정하면 그 컨텍스트의 전역 변수까지 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `context` | `str \| None` | `None` | 전역 변수를 볼 컨텍스트. 예: sop, cvex, surface. 생략하면 목록만 준다. |

#### vex_function_info

```python
vex_function_info(name: str, context: str = 'sop')
```

VEX 함수의 시그니처를 찾는다. 이름이 정확하지 않으면 비슷한 것을 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 함수 이름. 일부만 줘도 된다. 예: "noise", "pcopen", "prim" |
| `context` | `str` | `'sop'` | 어느 컨텍스트에서 쓸 수 있는지 볼지. sop, cvex, surface 등. 컨텍스트마다 쓸 수 있는 함수가 조금씩 다르다. |
