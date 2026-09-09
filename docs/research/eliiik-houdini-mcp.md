# eliiik/houdini-mcp 조사 문서

- **저장소**: https://github.com/eliiik/houdini-mcp
- **조사 시점 커밋**: `68207c60ec1c9ca27dee22801614f067ff0cba2f` (2026-03-08 10:42:01 +08:00)
- **조사일**: 2026-09-09
- **스타 수**: 0 (조사 시점, `gh api repos/eliiik/houdini-mcp` 기준)
- **마지막 push**: 2026-03-08T02:46:13Z
- **조사 방법**: `git clone --depth 1`로 로컬에 clone하여 소스 코드(`server.py`, `houdini_setup.py`, `pyproject.toml`, `README.md`)를 직접 읽어 추출. WebFetch 대체 없이 전량 코드 확인.

---

## 1. 툴 전수 목록

전부 단일 파일 `server.py`(총 1,108줄)에 정의되어 있고, 모든 툴이 `@mcp.tool()` 데코레이터가 붙은 평범한 함수다. 코드에서 실측한 `@mcp.tool()` 개수는 **33개**다. README는 "35 tools"라고 명시하지만, README 자체의 카테고리 표를 합산해도 33개(30 + 문서 툴 3개)로 나와 문서와 실제 코드/문서 표 사이에 불일치가 있다. 아래 목록은 코드 기준 33개 전량이다.

### Connection (연결)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_connect` | `host: str = "localhost"`, `port: int = 18811` | Houdini의 RPYC 서버(`hrpyc`)에 연결. 최초 호출 필수 |
| `houdini_disconnect` | (없음) | RPYC 연결 종료 |

### Scene / HIP 파일

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_scene_info` | (없음) | 현재 hip 파일 경로/이름/미저장 여부/프레임/프레임레인지/fps/버전/`/obj` 노드 개수 반환 |
| `houdini_scene_new` | (없음) | 새 빈 씬 생성 (`hou.hipFile.clear`) |
| `houdini_scene_open` | `path: str` | `.hip`/`.hipnc`/`.hiplc` 파일 열기 |
| `houdini_scene_save` | `path: str = ""` | 현재 씬 저장(경로 없으면 현재 위치에) |
| `houdini_set_frame` | `frame: float` | 현재 프레임 설정 |

### Node — 탐색

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_node_info` | `path: str` | 노드 상세 정보(타입/카테고리/네트워크 여부/플래그/자식 수/입출력 연결/에러·경고) |
| `houdini_node_children` | `path: str = "/obj"`, `recursive: bool = False` | 네트워크 노드의 자식 목록 (재귀 옵션) |
| `houdini_node_find` | `node_type: str = ""`, `name_pattern: str = ""`, `root: str = "/"` | 타입/이름 glob 패턴으로 노드 검색 (최대 200개) |

### Node — 조작

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_node_create` | `parent_path: str`, `node_type: str`, `name: str = ""` | 네트워크 안에 새 노드 생성 |
| `houdini_node_delete` | `path: str` | 노드 삭제 (`node.destroy()`) |
| `houdini_node_connect` | `from_path: str`, `to_path: str`, `from_output: int = 0`, `to_input: int = 0` | 노드 간 입출력 와이어 연결 |
| `houdini_node_set_flags` | `path: str`, `display: Optional[bool]`, `render: Optional[bool]`, `bypass: Optional[bool]` | display/render/bypass 플래그 설정 |
| `houdini_node_cook` | `path: str` | 강제 쿡(force cook) 후 에러/경고 반환 |
| `houdini_node_rename` | `path: str`, `new_name: str` | 노드 이름 변경 |
| `houdini_node_layout` | `path: str` | 네트워크 자식 노드 자동 정렬(`layoutChildren`) |

### Parameters (파라미터)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_parm_get` | `node_path: str`, `parm_name: str` | 파라미터 값 조회 (벡터는 튜플명으로 배열 반환) |
| `houdini_parm_set` | `node_path: str`, `parm_name: str`, `value: str` | 파라미터 값 설정 (문자열로 받아 JSON/숫자/문자 자동 파싱) |
| `houdini_parm_list` | `node_path: str` | 노드의 전체 파라미터(이름/라벨/타입/값) 나열 |
| `houdini_parm_set_expression` | `node_path: str`, `parm_name: str`, `expression: str`, `language: str = "python"` | 파라미터에 Python/HScript 표현식 설정 |

### Geometry (지오메트리)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_geo_info` | `node_path: str` | 점/프리미티브/버텍스 카운트, 바운딩박스, 속성 목록(포인트/프림/버텍스/디테일) 요약 |
| `houdini_geo_read_points` | `node_path: str`, `attribs: str = "P"`, `start: int = 0`, `limit: int = 100` | 지정 속성(`P,N,Cd,uv` 등)의 포인트 값 읽기 (최대 10000개) |
| `houdini_geo_read_prims` | `node_path: str`, `start: int = 0`, `limit: int = 100` | 프리미티브 타입/버텍스 수/포인트 인덱스 읽기 (최대 5000개) |
| `houdini_geo_export` | `node_path: str`, `output_path: str` | 지오메트리를 파일로 저장 (확장자로 포맷 결정: `.geo`/`.bgeo`/`.obj`/`.ply`) |
| `houdini_geo_bbox` | `node_path: str` | 바운딩 박스(min/max/center/size) 조회 |

### Transforms (오브젝트 트랜스폼)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_transform_get` | `node_path: str`, `space: str = "world"` | OBJ 노드의 T/R/S 및 world/local 매트릭스 조회 |
| `houdini_transform_set` | `node_path: str`, `tx,ty,tz,rx,ry,rz,sx,sy,sz: Optional[float]` (각 개별 옵션) | OBJ 노드 트랜스폼 파라미터 개별 설정 (지정된 값만 변경) |

### Execution — 탈출구(escape hatch)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_execute` | `code: str` | Houdini Python 환경에서 임의 코드 실행 (`hou` 전체 접근, `result` 변수로 값 반환) |
| `houdini_hscript` | `command: str` | HScript 명령 실행 |

### Local Documentation (로컬 문서, Houdini 연결 불필요)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `houdini_docs_list` | (없음) | `docs/` 하위 문서 토픽 목록 나열 (doc/ 상세본 + index/ 요약본) |
| `houdini_docs_read` | `topic: str` | 지정 문서 파일 읽기 (5만자 초과 시 잘림) |
| `houdini_docs_search` | `query: str` | 로컬 Houdini Python 문서 키워드 검색 (파일당 최대 5개, 최대 10개 파일) |

이 로컬 문서 기능은 저장소에 포함된 `docs/doc/*.md`(hou 모듈, 노드, 파라미터, 지오메트리, SOP/OBJ/VOP/COP/DOP 노드, 스크립팅 패턴, SOP verbs 등 11개)와 `docs/index/*.md`(5개 색인)를 그대로 서빙하는 방식이며, Houdini MCP 자체 기능이라기보다 "내장 레퍼런스 검색기"에 가깝다.

---

## 2. 아키텍처

**(a) 트랜스포트**: `stdio`. `server.py` 맨 아래 `mcp.run(transport="stdio")`로 고정. HTTP/SSE 옵션 없음. `mcp[cli]` (Python MCP SDK, `FastMCP`)를 그대로 사용.

**(b) Houdini와의 통신 방식**: `rpyc` (RPYC, Remote Python Call) classic 모드. Houdini 안에서 사용자가 직접 `import hrpyc; hrpyc.start_server(port=18811)`를 실행해 RPYC 서버를 띄우면, MCP 서버(외부 프로세스)가 `rpyc.classic.connect(host, port)`로 접속해 원격 `hou` 모듈 프록시(`_conn.modules.hou`)를 얻는다. 이후 모든 툴은 이 프록시를 통해 `hou.node(...)`, `parm.set(...)` 등을 그대로 호출하며, 프록시 객체를 로컬로 끌어올 때는 `rpyc.utils.classic.obtain()`을 사용(`_obtain()` 헬퍼).

**(c) Houdini 메인 스레드 안전성**: 별도 처리가 전혀 없다. `hdefereval`이나 `executeInMainThreadWithResult` 같은 메인스레드 디퍼럴 메커니즘을 사용하지 않으며, RPYC 서버가 Houdini 프로세스 내부에서 요청을 받는 스레드에서 곧바로 `hou` API를 호출한다. 즉 Houdini의 이벤트 루프/메인스레드와의 동기화는 RPYC 서버 자체의 스레딩 모델에 전적으로 의존하고, MCP 서버 코드 쪽에서는 아무 안전장치도 추가하지 않는다.

**(d) 툴 등록 방식**: 하드코딩. 플러그인이나 레지스트리 패턴 없이, `server.py` 한 파일에 `@mcp.tool()` 데코레이터가 붙은 함수를 순서대로 나열한 것이 전부다.

**(e) Houdini 쪽 설치 방식**: 수동. Houdini 패키지 JSON이나 셸프 툴을 통한 자동 설치가 없고, 사용자가 Houdini의 Python Shell(`Windows > Python Shell`)에서 직접 `import hrpyc; hrpyc.start_server(port=18811)`를 실행하거나, 저장소에 포함된 `houdini_setup.py`를 `exec(open(...).read())`로 붙여넣어 실행해야 한다. MCP 클라이언트(예: Claude Code) 쪽 설정은 `.mcp.json`에 `"command": "uv", "args": ["--directory", "/path/to/houdini-mcp", "run", "server.py"]` 형태로 등록한다.

**통신 다이어그램** (README 인용):
```
AI Client ── MCP(stdio) ── MCP Server(server.py) ── RPYC(TCP) ── Houdini(port 18811)
```

---

## 3. 의존성

`pyproject.toml` 기준:
- `mcp[cli]>=1.2.0` (Python MCP SDK, `FastMCP` 사용)
- `rpyc>=6.0.0`
- `requires-python = ">=3.10"`
- 빌드 시스템: `hatchling`
- pydantic은 `pyproject.toml`에 직접 명시되어 있지 않음(`mcp[cli]`의 전이 의존성으로만 존재할 가능성)

---

## 4. 지원 Houdini 버전 / 커밋 / 스타

- **지원 Houdini 버전**: README에 명시적 버전 제약 없음. "Houdini (any edition — Apprentice, Indie, Core, FX)"라고만 기술되어 있고, 특정 메이저 버전(20.x 등) 요구사항은 코드/문서 어디에도 없음. `hrpyc`가 표준 Houdini Python 배포에 포함되어 있으면 동작하는 구조.
- **마지막 커밋**: `68207c60ec1c9ca27dee22801614f067ff0cba2f`, 2026-03-08 10:42:01 +08:00 (같은 날 초기 push, 사실상 단일 커밋짜리 초기 릴리스로 보임)
- **스타 수**: 0 (2026-09-09 조사 시점)
