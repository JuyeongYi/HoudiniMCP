# HoudiniMCP 소스 작성 규칙

## 멀티플랫폼

이 프로젝트는 **Windows / Linux / macOS 를 모두 지원한다.** 개발은 Windows 에서
하지만, 플랫폼에 묶인 코드를 쓰지 않는다.

### 경로와 구분자는 하드코딩하지 않는다

경로 문자열을 손으로 조립하지 말고 표준 라이브러리에서 얻어온다.

| 필요한 것 | 쓸 것 | 쓰지 말 것 |
|---|---|---|
| 경로 결합·조작 | `pathlib.Path` | `"a" + "\\" + "b"`, `"a/b"` 문자열 |
| 경로 구분자 | `os.sep` | `"\\"`, `"/"` |
| PATH 류 목록 구분자 | `os.pathsep` | `";"`, `":"` |
| 줄바꿈 | `os.linesep` (파일 출력 시) | `"\r\n"` |
| 임시 디렉토리 | `tempfile` | `"C:\\Temp"`, `"/tmp"` |
| 사용자 홈 | `Path.home()` | `"C:\\Users\\..."` |

`HOUDINI_PATH` 나 `HOUDINI_PACKAGE_DIR` 처럼 여러 경로를 담는 환경변수를 가를
때는 반드시 `os.pathsep` 을 쓴다. Windows 는 `;`, 나머지는 `:` 다.

```python
# 나쁘다
for entry in hou.text.expandString("$HOUDINI_PATH").split(";"):

# 좋다
for entry in hou.text.expandString("$HOUDINI_PATH").split(os.pathsep):
```

경로의 마지막 요소를 꺼낼 때도 문자열을 자르지 않는다.

```python
name = path.split("/")[-1]   # 나쁘다
name = Path(path).name       # 좋다
```

### 플랫폼 분기는 명시적으로

분기가 정말 필요하면 `sys.platform` 으로 드러내고 이유를 주석으로 남긴다.
암묵적으로 한 플랫폼을 가정하지 않는다.

```python
if sys.platform == "win32":
    return asyncio.ProactorEventLoop()
return asyncio.SelectorEventLoop()
```

### 예외: Houdini 패키지 JSON

Houdini 패키지 JSON(`*.json`) 의 `hpath` / `env` 값은 **모든 플랫폼에서 슬래시**를
쓴다. Houdini 자체 규약이므로 여기서만 `str(path).replace(os.sep, "/")` 로 바꿔
넣고, 그 이유를 주석에 남긴다.

### Houdini 파이썬 버전

`python3.13libs` 디렉토리 이름은 Houdini 가 쓰는 파이썬 버전에 묶인다.
코드에서 이 이름이 필요하면 설치본에서 유도한다(`tests/package_order/harness.py`
의 `python_tag()` 참고). 하드코딩하면 Houdini 가 파이썬을 올릴 때 조용히 깨진다.

---

## 툴 팩 분리 규칙

**관련 있는 툴끼리 묶어 별도 패키지로 분리한다.** 팩 하나에 이것저것 담지
않는다. 경계는 Houdini 의 컨텍스트·도메인 계층을 따른다.

```
houdini_mcp                  서버 + 레지스트리 (툴 없음)
├─ houdini_mcp_base          모든 작업의 토대 (아래 참고)
├─ houdini_mcp_sop           SOP 전문
├─ houdini_mcp_dop           DOP 공통
│  ├─ houdini_mcp_dop_pyro   솔버별 전문
│  ├─ houdini_mcp_dop_flip
│  └─ houdini_mcp_dop_rbd
├─ houdini_mcp_example       툴 팩 만드는 법을 보여주는 최소 예시
└─ ...
```

`houdini_mcp_base` 는 예외다. **어떤 컨텍스트에서 무엇을 하든 쓰이는 것**을 모두
담고, 팩이 아니라 모듈로만 나눈다.

| 모듈 | 담는 것 |
|---|---|
| `info` | 씬·노드·그래프 조회 |
| `edit` | 네트워크 종류를 가리지 않는 노드 생성·조작·연결 |
| `parms` | 파라미터 조회 |
| `geometry` | 지오메트리 통계·어트리뷰트 — SOP 뿐 아니라 DOP 등에서도 필요하다 |
| `viewport` | 뷰포트 캡처와 프레이밍 — 만든 결과를 눈으로 확인한다 |

컨텍스트를 가리지 않는지가 기준이다. 어느 하나에서만 의미가 있으면 전용 팩으로
분리한다.

규칙:

- 이름은 `houdini_mcp_<도메인>` 이고, 계층이 깊어지면 밑줄로 잇는다
  (`houdini_mcp_dop_pyro`). Houdini 패키지 JSON 파일명, 디렉토리명, Python
  패키지명이 **모두 같아야** 한다. `requires` 와 로그 `category` 가 이 이름을
  그대로 쓴다.
- 모든 툴 팩은 `"requires": ["houdini_mcp"]` 를 넣는다. 하위 전문 팩은 상위 팩도
  함께 넣는다: `"requires": ["houdini_mcp", "houdini_mcp_base"]`,
  `"requires": ["houdini_mcp", "houdini_mcp_dop"]`.
  순서 보장이 아니라 **존재 보장**이 목적이다.
- 툴 팩은 서버를 import 하지 않는다. `houdini_mcp` 의 레지스트리만 안다.
- 팩이 커지면 도메인을 더 쪼갠다. 다만 크기 경계는 파일 단위로 본다(전역 규칙).
  `houdini_mcp_base` 처럼 모듈이 여럿인 팩은 합계가 아니라 모듈 하나의 크기를 본다.

새 팩을 만들 때 필요한 파일은 넷뿐이다:

```
houdini_mcp_<도메인>.json                                패키지 정의
houdini_mcp_<도메인>/python3.13libs/pythonrc.py          등록 진입점
houdini_mcp_<도메인>/python3.13libs/houdini_mcp_<도메인>/__init__.py
houdini_mcp_<도메인>/python3.13libs/houdini_mcp_<도메인>/<모듈>.py
```

## 툴 작성 규칙

### 씬을 바꾸는 툴은 `@undoable` 로 감싼다

툴 호출 하나가 Undo 하나가 되어야 한다. 사용자가 Ctrl+Z 한 번으로 모델이 한 일을
되돌릴 수 있어야 하기 때문이다. 툴 안에서 노드를 만들고 파라미터를 걸고 연결까지
했더라도 마찬가지다.

```python
@tool()
@undoable("노드 생성")
def create_node(...):
    ...
```

데코레이터 순서가 중요하다. `@undoable` 이 아래(먼저 적용)에 와야 레지스트리에
등록되는 것이 Undo 로 감싼 함수가 된다. 함수 안에서 `with hou.undos.group(...)` 을
직접 쓰지 않는다.

### 노드를 만들 때 코멘트를 강제한다

`comment` 를 **기본값 없는 인자**로 둔다. 그래야 MCP 입력 스키마에서 required 가
되어 빠뜨릴 수 없다. 나중에 이 씬을 여는 사람이 노드가 왜 있는지 알 수 있어야
한다.

```python
def create_node(parent: str, node_type: str, comment: str, name: str | None = None):
```

코멘트는 `setComment` 로 달고 `hou.nodeFlag.DisplayComment` 를 켜서 네트워크
뷰에도 보이게 한다. 노드 생성 시점에는 넣을 수 없으므로 만든 직후에 지정한다.

### 노드를 읽는 툴은 코멘트를 함께 준다

`node_info`, `list_children`, `network_graph`, `find_nodes`, `get_parms`,
`list_parms`, `parm_info` 처럼 노드를 돌려주는 것은 전부 `comment` 를 포함한다.
이름과 타입만으로는 그 노드가 왜 있는지 알 수 없다.

### 노드 이름은 역할이 드러나게

`box1`, `geo2` 같은 기본 이름을 쓰지 않는다. `wall_body`, `merlon_points`,
`copy_merlons` 처럼 무엇을 하는지 드러나게 짓는다. 툴 docstring 에 이 지침을
적어 두어 모델이 읽게 한다.

### Houdini 로 들어가는 문자열은 영어로

씬 파일에 저장되거나 Houdini UI 에 뜨는 문자열은 영어로 쓴다. 노드 이름, 노드
코멘트, `@undoable` 레이블이 여기 해당한다. 씬을 여는 사람의 로케일과 무관해야
하고, 다른 도구에서도 읽히기 때문이다.

코드 주석과 docstring 은 한국어를 그대로 쓴다. 그것은 이 저장소 안에만 있다.

### 실패는 다음에 무엇을 할지 알려 준다

툴 예외 메시지는 그대로 모델에게 간다(`adapter` 가 `ToolError` 로 감싼다).
무엇이 잘못됐는지만이 아니라 어떻게 고치는지까지 적는다.

```
't' 은 벡터 파라미터입니다. 성분 이름으로 거세요: tx, ty, tz
```

### 팩은 서버가 없어도 Houdini 를 막지 않는다

- `pythonrc.py` 는 `except Exception` 으로 받는다. `ImportError` 만 잡으면 서버
  패키지가 다른 이유로 깨졌을 때 Houdini 기동이 막힌다.
- 팩의 `__init__.py` 는 모듈을 import 하지 않고 `TOOL_MODULES` 로 선언만 한다.
  `register_pack` 이 하나씩 격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은
  등록된다.

## 그 밖의 규칙

전역 규칙(파일 크기 경계, 코드 스멜 감지, 주기적 리팩토링)은 사용자 전역
`CLAUDE.md` 를 따른다.

설계 결정과 그 근거는 `docs/design/decisions.md` 에 있다. 구조를 바꾸기 전에
먼저 읽는다 — 대부분 실측으로 확인한 Houdini 동작에 기대고 있고,
`tests/package_order/` 의 회귀 테스트가 그것을 고정하고 있다.
