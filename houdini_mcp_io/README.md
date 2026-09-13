# houdini_mcp_io

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_io.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 8개 |
| 모듈 (`TOOL_MODULES`) | `export`, `usd`, `interchange`, `load` |

## 개요

```text
임포트·익스포트·의존성 툴 팩 — 씬과 디스크 사이를 오간다.

    export       네이티브 지오메트리 내보내기와 포맷 안내. 전부 **쓴 뒤 다시 읽어 검증**한다
    usd          USD 내보내기. LOP 스테이지를 pxr 로 쓰고 다시 연다
    interchange  Alembic·FBX 내보내기. abcinfo·시그니처로 검증한다
    load         파일을 씬으로 들이기(`import` 는 예약어라 모듈명이 load 다)

이 팩이 기존 구현과 갈라지는 지점은 쓰고 끝내지 않는다는 것이다.

1. **쓰고 끝내지 않는다.** 내보낸 파일을 포맷에 맞는 리더로 다시 열어
   점·프리미티브 수를 대조한다. 안 맞으면 안 맞는다고 돌려준다.
   `hou.Geometry.saveToFile()` 은 `.usd` / `.abc` / `.fbx` 확장자를 받고도
   내용은 ASCII `.geo` 를 쓴다(실측 확인). 다시 읽어 보지 않으면 이 거짓말을
   못 잡는다.
씬의 파일 참조 목록·수집·경로 치환·이식성 판정은 컨텍스트를 가리지 않아
houdini_mcp_base 의 `deps` / `portability` 로 옮겼다. 이미지 텍스처의 내용은
houdini_mcp_mat 의 `texture_info` 가 다룬다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`write_geometry`](#write_geometry) | `export` | SOP 지오메트리를 네이티브 포맷으로 쓰고, 다시 읽어 맞는지 확인한다. |  |
| [`export_formats`](#export_formats) | `export` | 어떤 포맷을 어느 툴로 써야 하는지, 이 설치에서 무엇이 되는지 알려 준다. |  |
| [`export_usd`](#export_usd) | `usd` | SOP 이나 LOP 을 USD 로 내보내고, pxr 로 다시 열어 확인한다. | ✓ |
| [`export_alembic`](#export_alembic) | `interchange` | SOP 을 Alembic 으로 내보내고, abcinfo 로 다시 열어 확인한다. | ✓ |
| [`export_fbx`](#export_fbx) | `interchange` | OBJ 서브트리나 SOP 을 FBX 로 내보내고, 헤더를 확인한다. | ✓ |
| [`probe_file`](#probe_file) | `load` | 파일을 **실제로 열어** 안에 무엇이 들었는지 돌려준다. |  |
| [`import_geometry`](#import_geometry) | `load` | 지오메트리 파일을 읽는 SOP 을 만들고, 쿡해서 무엇이 들어왔는지 돌려준다. | ✓ |
| [`import_scene`](#import_scene) | `load` | 다른 .hip 의 노드를 현재 씬에 합친다. 무엇이 들어왔는지 세어 준다. | ✓ |

## 모듈별 상세

### `export`

내보내기 툴 — 쓰고 나서 **반드시 다시 읽어 검증한다.**

#### write_geometry

```python
write_geometry(path: str, file_path: str, overwrite: bool = False, frame_range: Sequence[float] | None = None, verify: bool = True)
```

SOP 지오메트리를 네이티브 포맷으로 쓰고, 다시 읽어 맞는지 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 내보낼 SOP 노드 경로. |
| `file_path` | `str` | 필수 | 저장할 경로. $HIP 같은 Houdini 변수를 써도 된다. 쓸 수 있는 확장자: .bgeo.sc(권장) / .bgeo / .geo / .obj / .ply / .stl / .vdb |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |
| `frame_range` | `Sequence[float] \| None` | `None` | [start, end] 또는 [start, end, step]. 주면 프레임마다 쿡해서 쓴다. 이때 file_path 에 $F4 같은 프레임 토큰이 있어야 한다. |
| `verify` | `bool` | `True` | False 면 다시 읽지 않는다. 아주 큰 캐시에만 쓴다. |

#### export_formats

```python
export_formats()
```

어떤 포맷을 어느 툴로 써야 하는지, 이 설치에서 무엇이 되는지 알려 준다.

### `usd`

USD 내보내기 - LOP 스테이지를 pxr 로 직접 쓰고 다시 열어 대조한다.

#### export_usd

```python
export_usd(path: str, file_path: str, overwrite: bool = False, flatten: bool = True, set_metadata: bool = True, run_usdchecker: bool = False)
```

SOP 이나 LOP 을 USD 로 내보내고, pxr 로 다시 열어 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 내보낼 SOP 또는 LOP 노드 경로. |
| `file_path` | `str` | 필수 | 저장할 경로. .usd / .usda(텍스트) / .usdc(바이너리) / .usdz |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |
| `flatten` | `bool` | `True` | True 면 컴포지션을 평탄화해서 한 파일로 쓴다(참조·서브레이어가 풀린 자립 파일). False 면 루트 레이어만 쓴다 — 참조가 상대 경로로 남으므로 옮기면 깨질 수 있다. |
| `set_metadata` | `bool` | `True` | True(기본)면 쓴 뒤 upAxis 와 defaultPrim 을 채운다. pxr 의 Export 는 이 둘을 저자하지 않아서, 그냥 두면 다른 DCC 가 읽을 때 방향과 진입 프림을 모른다. |
| `run_usdchecker` | `bool` | `False` | True 면 $HFS/bin/usdchecker 로 규격 검사까지 돌린다. |

### `interchange`

Alembic·FBX 내보내기 - DCC 교환 포맷. 둘 다 ROP 으로 쓴다.

#### export_alembic

```python
export_alembic(path: str, file_path: str, overwrite: bool = False, frame_range: Sequence[float] | None = None)
```

SOP 을 Alembic 으로 내보내고, abcinfo 로 다시 열어 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 내보낼 SOP 노드 경로. |
| `file_path` | `str` | 필수 | 저장할 .abc 경로. |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |
| `frame_range` | `Sequence[float] \| None` | `None` | [start, end] 또는 [start, end, step]. 생략하면 현재 프레임만. Alembic 한 파일 안에 프레임들이 시간 샘플로 들어간다. |

#### export_fbx

```python
export_fbx(path: str, file_path: str, overwrite: bool = False, frame_range: Sequence[float] | None = None, ascii_format: bool = False)
```

OBJ 서브트리나 SOP 을 FBX 로 내보내고, 헤더를 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 내보낼 노드 경로. OBJ 노드(서브트리 통째로) 또는 SOP. |
| `file_path` | `str` | 필수 | 저장할 .fbx 경로. |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |
| `frame_range` | `Sequence[float] \| None` | `None` | [start, end] 또는 [start, end, step]. 생략하면 현재 프레임만. |
| `ascii_format` | `bool` | `False` | True 면 텍스트 FBX 로 쓴다. 디버깅용이고 파일이 커진다. |

### `load`

들이는 툴 — 파일을 씬으로, 그리고 들이기 전에 파일을 열어 본다.

#### probe_file

```python
probe_file(file_path: str, detail: bool = False)
```

파일을 **실제로 열어** 안에 무엇이 들었는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file_path` | `str` | 필수 | 열어 볼 파일 경로. $HIP 같은 Houdini 변수를 써도 된다. |
| `detail` | `bool` | `False` | True 면 더 깊게 본다(USD 는 해석된 레이어 목록, Alembic 은 어트리뷰트와 페이스셋까지). 느려진다. |

#### import_geometry

```python
import_geometry(parent: str, file_path: str, comment: str, name: str | None = None)
```

지오메트리 파일을 읽는 SOP 을 만들고, 쿡해서 무엇이 들어왔는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 노드를 만들 네트워크 경로. 예: /obj 또는 /obj/castle |
| `file_path` | `str` | 필수 | 읽을 파일 경로. $HIP 같은 Houdini 변수를 써도 된다. |
| `comment` | `str` | 필수 | 이 노드가 왜 있는지 영어로. 씬을 여는 사람이 읽는다. |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 짓는다. 역할이 드러나게 지으세요. |

#### import_scene

```python
import_scene(file_path: str, node_pattern: str = '*', overwrite_on_conflict: bool = False)
```

다른 .hip 의 노드를 현재 씬에 합친다. 무엇이 들어왔는지 세어 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `file_path` | `str` | 필수 | 합칠 .hip / .hipnc / .hiplc 경로. |
| `node_pattern` | `str` | `'*'` | 이 패턴에 맞는 노드만 들인다. 기본은 전부. |
| `overwrite_on_conflict` | `bool` | `False` | 같은 경로의 노드를 덮어쓴다. 되돌리기 어려우므로 명시적으로 요구한다. |
