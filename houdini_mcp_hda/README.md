# houdini_mcp_hda

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `houdini_mcp_hda.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 19개 |
| 모듈 (`TOOL_MODULES`) | `create`, `interface`, `sections`, `manage`, `vcs`, `check` |

## 개요

```text
HDA 저작·관리 툴 팩 — 서브넷을 디지털 에셋으로 굽고, 인터페이스를 짓고,
설치하고, 버전 관리한다.

    create      서브넷 → HDA, 정의 복사
    interface   HDA **정의**의 파라미터 인터페이스 — 추가·승격·삭제·재배치
    sections    정의 안의 섹션 — PythonModule, OnCreated 등 콜백 스크립트
    manage      설치·해제·리로드·조회
    vcs         Git 친화 디렉토리로 펼치고 다시 접기
    check       인스턴스를 실제로 놓고 쿡해서 검증

`houdini_mcp_base` 의 parmedit 과 경계가 다르다. 거기는 **노드 인스턴스 하나**에
스페어 파라미터를 붙인다(그 노드에만 남는다). 여기는 **HDA 정의**의 인터페이스를
고친다(그 타입의 모든 인스턴스가 함께 바뀌고 .hda 파일에 저장된다).

파라미터 템플릿을 만드는 일은 base 의 `parmtemplate` 헬퍼를 그대로 쓴다.
DialogScript 문자열을 손으로 조립하지 않는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`create_hda`](#create_hda) | `create` | 서브넷을 디지털 에셋(HDA)으로 굽는다. | ✓ |
| [`save_as_hda`](#save_as_hda) | `create` | 이미 있는 HDA 정의를 다른 .hda 파일로 복사한다. 이름도 바꿀 수 있다. | ✓ |
| [`hda_interface`](#hda_interface) | `interface` | HDA 정의의 파라미터 인터페이스를 폴더까지 펼쳐 읽는다. |  |
| [`add_hda_parm`](#add_hda_parm) | `interface` | HDA 정의의 인터페이스에 파라미터를 새로 붙이고 .hda 파일에 저장한다. | ✓ |
| [`promote_parm`](#promote_parm) | `interface` | 내부 노드의 파라미터를 HDA 인터페이스로 끌어올리고 식으로 묶는다. | ✓ |
| [`remove_hda_parm`](#remove_hda_parm) | `interface` | HDA 인터페이스에서 파라미터나 폴더를 뗀다. | ✓ |
| [`reorder_hda_parms`](#reorder_hda_parms) | `interface` | HDA 인터페이스의 최상위 항목 순서를 바꾼다. | ✓ |
| [`hda_sections`](#hda_sections) | `sections` | HDA 정의 안의 섹션을 나열한다. 크기와 언어, 내용 앞부분까지. |  |
| [`get_hda_section`](#get_hda_section) | `sections` | 섹션 하나의 내용을 통째로 읽는다. |  |
| [`set_hda_section`](#set_hda_section) | `sections` | 섹션 내용을 쓰고 .hda 파일에 저장한다. 없으면 만든다. | ✓ |
| [`remove_hda_section`](#remove_hda_section) | `sections` | 섹션을 지우고 .hda 파일에 저장한다. | ✓ |
| [`install_hda`](#install_hda) | `manage` | .hda 라이브러리를 이 세션에 설치한다. 무엇이 들어오는지 함께 돌려준다. | ✓ |
| [`uninstall_hda`](#uninstall_hda) | `manage` | .hda 라이브러리를 이 세션에서 뺀다. 파일은 그대로 둔다. | ✓ |
| [`reload_hda`](#reload_hda) | `manage` | .hda 파일을 디스크에서 다시 읽는다. 씬의 인스턴스가 새 정의로 갱신된다. | ✓ |
| [`list_installed_hdas`](#list_installed_hdas) | `manage` | 이 세션에 설치된 HDA 라이브러리와 그 안의 에셋들을 나열한다. |  |
| [`hda_info`](#hda_info) | `manage` | HDA 정의 하나를 자세히 읽는다 — 메타데이터·옵션·섹션·인스턴스까지. |  |
| [`expand_hda`](#expand_hda) | `vcs` | .hda 파일을 디렉토리로 펼친다. Git 에 올릴 수 있는 모양으로. | ✓ |
| [`collapse_hda`](#collapse_hda) | `vcs` | 펼쳐 둔 디렉토리를 다시 .hda 파일로 접는다. | ✓ |
| [`validate_hda`](#validate_hda) | `check` | HDA 를 실제로 인스턴스화하고 쿡해서 동작하는지 확인한다. 임시 노드는 지운다. | ✓ |

## 모듈별 상세

### `create`

서브넷을 디지털 에셋으로 굽고, 정의를 다른 파일로 옮긴다.

#### create_hda

```python
create_hda(path: str, name: str, hda_file: str, comment: str, namespace: str | None = None, version: str | None = None, label: str | None = None, icon: str | None = None, min_inputs: int = 0, max_inputs: int = 0)
```

서브넷을 디지털 에셋(HDA)으로 굽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 구울 서브넷 노드 경로. 예: /obj/castle/wall_builder |
| `name` | `str` | 필수 | 노드 타입의 핵심 이름. `::` 를 넣지 않는다. 예: brick_maker |
| `hda_file` | `str` | 필수 | 저장할 .hda 파일 경로. 없으면 만든다. |
| `comment` | `str` | 필수 | 이 에셋이 무엇을 하는지. 영어로. 노드와 정의 양쪽에 달린다. |
| `namespace` | `str \| None` | `None` | 타입 이름의 네임스페이스. 예: krafton |
| `version` | `str \| None` | `None` | 타입 이름의 버전. 예: "1.0" |
| `label` | `str \| None` | `None` | Tab 메뉴에 뜨는 이름. 영어로. 생략하면 Houdini 가 정한다. |
| `icon` | `str \| None` | `None` | 아이콘 이름. 예: SOP_box |
| `min_inputs` | `int` | `0` | 최소 입력 개수. |
| `max_inputs` | `int` | `0` | 최대 입력 개수. 0 이면 입력이 없다. |

#### save_as_hda

```python
save_as_hda(target: str, hda_file: str, name: str | None = None, namespace: str | None = None, version: str | None = None, label: str | None = None, install: bool = True)
```

이미 있는 HDA 정의를 다른 .hda 파일로 복사한다. 이름도 바꿀 수 있다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | 원본. HDA 인스턴스의 노드 경로거나 노드 타입 이름 (Sop/ns::brick_maker::1.0). |
| `hda_file` | `str` | 필수 | 복사해 넣을 .hda 파일 경로. 없으면 만든다. |
| `name` | `str \| None` | `None` | 새 핵심 이름. 생략하면 원본 이름 그대로. |
| `namespace` | `str \| None` | `None` | 새 네임스페이스. 생략하면 원본 그대로. |
| `version` | `str \| None` | `None` | 새 버전. 생략하면 원본 그대로. |
| `label` | `str \| None` | `None` | Tab 메뉴 이름. 영어로. |
| `install` | `bool` | `True` | True 면 복사한 뒤 그 파일을 이 세션에 설치한다. |

### `interface`

HDA **정의**의 파라미터 인터페이스를 짓는다.

#### hda_interface

```python
hda_interface(target: str)
```

HDA 정의의 파라미터 인터페이스를 폴더까지 펼쳐 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름 (Sop/ns::brick_maker::1.0). |

#### add_hda_parm

```python
add_hda_parm(target: str, kind: str, name: str, label: str, size: int = 1, default: Any = None, min_value: float | None = None, max_value: float | None = None, menu_items: list[str] | None = None, menu_labels: list[str] | None = None, string_type: str = 'regular', help_text: str | None = None, folder: list[str] | None = None)
```

HDA 정의의 인터페이스에 파라미터를 새로 붙이고 .hda 파일에 저장한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름. |
| `kind` | `str` | 필수 | float / int / string / toggle / menu / button / ramp_float / ramp_color / separator. |
| `name` | `str` | 필수 | 내부 이름. 식과 set_parms 가 쓴다. 예: wall_height |
| `label` | `str` | 필수 | UI 에 뜨는 이름. 영어로. 예: "Wall Height" |
| `size` | `int` | `1` | 성분 수. float/int/string 에만 의미가 있다. |
| `default` | `Any` | `None` | 기본값. 벡터면 목록으로 주거나 값 하나로 전부 채운다. |
| `min_value` | `float \| None` | `None` | 슬라이더 최솟값. |
| `max_value` | `float \| None` | `None` | 슬라이더 최댓값. |
| `menu_items` | `list[str] \| None` | `None` | menu 종류일 때 고를 값들. |
| `menu_labels` | `list[str] \| None` | `None` | 그 값들의 표시 이름. |
| `string_type` | `str` | `'regular'` | string 종류일 때 regular / file / node / node_list. |
| `help_text` | `str \| None` | `None` | 파라미터 툴팁. 영어로. |
| `folder` | `list[str] \| None` | `None` | 넣을 폴더 경로. 예: ["Controls"]. 없으면 만든다. |

#### promote_parm

```python
promote_parm(path: str, inner: str, parm: str, name: str | None = None, label: str | None = None, folder: list[str] | None = None, link: bool = True)
```

내부 노드의 파라미터를 HDA 인터페이스로 끌어올리고 식으로 묶는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | HDA 인스턴스의 노드 경로. 내부 노드에 닿으려면 인스턴스가 필요하다. |
| `inner` | `str` | 필수 | 그 안쪽 노드의 상대 경로. 예: brick_body |
| `parm` | `str` | 필수 | 올릴 파라미터 이름. 벡터는 튜플 이름으로 준다. 예: size |
| `name` | `str \| None` | `None` | 인터페이스에서 쓸 새 이름. 생략하면 원래 이름 그대로. |
| `label` | `str \| None` | `None` | UI 에 뜨는 이름. 영어로. 생략하면 원래 라벨 그대로. |
| `folder` | `list[str] \| None` | `None` | 넣을 폴더 경로. 예: ["Controls"]. 없으면 만든다. |
| `link` | `bool` | `True` | True 면 내부 파라미터에 식을 걸어 묶는다. False 면 올리기만 한다. |

#### remove_hda_parm

```python
remove_hda_parm(target: str, name: str)
```

HDA 인터페이스에서 파라미터나 폴더를 뗀다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름. |
| `name` | `str` | 필수 | 뗄 파라미터/폴더의 내부 이름. 벡터는 튜플 이름으로. |

#### reorder_hda_parms

```python
reorder_hda_parms(target: str, order: list[str])
```

HDA 인터페이스의 최상위 항목 순서를 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름. |
| `order` | `list[str]` | 필수 | 최상위 항목 이름들을 원하는 순서로. 예: ["size", "controls"] |

### `sections`

HDA 정의 안의 섹션 — 콜백 스크립트와 헬프를 읽고 쓴다.

#### hda_sections

```python
hda_sections(target: str)
```

HDA 정의 안의 섹션을 나열한다. 크기와 언어, 내용 앞부분까지.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름 (Sop/ns::brick_maker::1.0). |

#### get_hda_section

```python
get_hda_section(target: str, name: str)
```

섹션 하나의 내용을 통째로 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름. |
| `name` | `str` | 필수 | 섹션 이름. 예: PythonModule |

#### set_hda_section

```python
set_hda_section(target: str, name: str, contents: str, language: str = 'python')
```

섹션 내용을 쓰고 .hda 파일에 저장한다. 없으면 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름. |
| `name` | `str` | 필수 | 섹션 이름. 예: PythonModule, OnCreated, Help |
| `contents` | `str` | 필수 | 넣을 내용. 스크립트라면 영어 주석으로 쓴다. |
| `language` | `str` | `'python'` | python / hscript / text. text 는 스크립트가 아닌 섹션. |

#### remove_hda_section

```python
remove_hda_section(target: str, name: str)
```

섹션을 지우고 .hda 파일에 저장한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름. |
| `name` | `str` | 필수 | 지울 섹션 이름. |

### `manage`

HDA 라이브러리를 세션에 설치·해제·리로드하고 무엇이 들어 있는지 읽는다.

#### install_hda

```python
install_hda(file_path: str)
```

.hda 라이브러리를 이 세션에 설치한다. 무엇이 들어오는지 함께 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file_path` | `str` | 필수 | .hda 또는 .otl 파일 경로. |

#### uninstall_hda

```python
uninstall_hda(file_path: str, force: bool = False)
```

.hda 라이브러리를 이 세션에서 뺀다. 파일은 그대로 둔다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file_path` | `str` | 필수 | .hda 파일 경로. 또는 "Embedded". |
| `force` | `bool` | `False` | True 면 인스턴스가 있어도 해제한다. |

#### reload_hda

```python
reload_hda(file_path: str)
```

.hda 파일을 디스크에서 다시 읽는다. 씬의 인스턴스가 새 정의로 갱신된다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file_path` | `str` | 필수 | .hda 파일 경로. |

#### list_installed_hdas

```python
list_installed_hdas(pattern: str | None = None, category: str | None = None, limit: int = 60)
```

이 세션에 설치된 HDA 라이브러리와 그 안의 에셋들을 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `pattern` | `str \| None` | `None` | 글롭 패턴. 예: "*brick*", "*/castle/*" |
| `category` | `str \| None` | `None` | 노드 카테고리로 거른다. 예: Sop, Object, Lop |
| `limit` | `int` | `60` | 돌려줄 라이브러리 최대 개수. |

#### hda_info

```python
hda_info(target: str)
```

HDA 정의 하나를 자세히 읽는다 — 메타데이터·옵션·섹션·인스턴스까지.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름 (Sop/ns::brick_maker::1.0). |

### `vcs`

HDA 를 Git 이 다룰 수 있는 디렉토리로 펼치고 다시 접는다.

#### expand_hda

```python
expand_hda(file_path: str, directory: str, uncompress_contents: bool = True)
```

.hda 파일을 디렉토리로 펼친다. Git 에 올릴 수 있는 모양으로.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file_path` | `str` | 필수 | 펼칠 .hda 파일 경로. |
| `directory` | `str` | 필수 | 펼쳐 넣을 디렉토리. 없으면 만든다. |
| `uncompress_contents` | `bool` | `True` | True 면 먼저 압축을 풀어 저장한다. |

#### collapse_hda

```python
collapse_hda(directory: str, file_path: str, install: bool = True)
```

펼쳐 둔 디렉토리를 다시 .hda 파일로 접는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `directory` | `str` | 필수 | `expand_hda` 가 만든 디렉토리. |
| `file_path` | `str` | 필수 | 만들 .hda 파일 경로. 이미 있으면 덮어쓴다. |
| `install` | `bool` | `True` | True 면 접은 뒤 이 세션에 설치한다. |

### `check`

만든 HDA 가 실제로 도는지 확인한다.

#### validate_hda

```python
validate_hda(target: str, parms: dict[str, Any] | None = None, frame: float | None = None)
```

HDA 를 실제로 인스턴스화하고 쿡해서 동작하는지 확인한다. 임시 노드는 지운다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target` | `str` | 필수 | HDA 인스턴스의 노드 경로거나 노드 타입 이름 (Sop/ns::brick_maker::1.0). |
| `parms` | `dict[str, Any] \| None` | `None` | 쿡하기 전에 걸어 볼 파라미터. 예: {"size": 2.0} |
| `frame` | `float \| None` | `None` | 검증할 프레임. 생략하면 현재 프레임. |
