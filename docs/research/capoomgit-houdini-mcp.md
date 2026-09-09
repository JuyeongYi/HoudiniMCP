# capoomgit/houdini-mcp 조사 보고서

- **저장소**: https://github.com/capoomgit/houdini-mcp
- **조사 시점 커밋**: `de4fd93acc207fc57c02b330d421461f5963a945` (2026-06-11, `main`)
- **조사일**: 2026-09-09
- **조사 방법**: `git clone --depth 1`로 로컬 클론 후 소스 직접 열람 (WebFetch 미사용)

README에 명시되어 있듯 이 저장소는 [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp)를 그대로 본떠 만든 구조다("Houdini-MCP was built following blender-mcp"). Houdini 플러그인(TCP 소켓 서버) + 별도 프로세스로 뜨는 MCP 브리지 스크립트(stdio)의 2-프로세스 구성.

## 1. 툴 전수 목록

`houdini_mcp_server.py`(MCP 브리지, `mcp[cli]` SDK 사용)에 `@mcp.tool()`로 25개 툴이 정의되어 있다. 모든 툴의 첫 인자는 FastMCP `Context` 객체(`ctx: Context`)이며, 각 툴 내부에서 `_houdini_call(cmd_type, params)`을 통해 TCP 소켓으로 Houdini 쪽 `server.py`(`HoudiniMCPServer`)에 커맨드를 보낸다.

### 씬/노드 기본 조작

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_scene_info` | `ctx` | Houdini에 씬 정보 요청, JSON 문자열 반환 |
| `create_node` | `ctx`, `node_type: str`, `parent_path: str = "/obj"`, `name: str = None` | Houdini에 새 노드 생성 |
| `execute_houdini_code` | `ctx`, `code: str` | Houdini 환경에서 임의 Python 코드 실행 ("LAST RESORT"로 문서화) |
| `connect_nodes` | `ctx`, `from_path: str`, `to_path: str`, `input_index: int = 0`, `output_index: int = 0` | 한 노드의 출력을 다른 노드의 입력에 배선 |
| `disconnect_node_input` | `ctx`, `path: str`, `input_index: int = 0` | 노드 입력 연결 해제(이전 연결 정보 보고) |
| `delete_node` | `ctx`, `path: str` | 경로로 노드 삭제 |
| `set_parameters` | `ctx`, `path: str`, `parameters: Dict[str, Any]` | 한 번의 undo 가능한 호출로 노드 파라미터 1개 이상 설정 |
| `get_parameter_schema` | `ctx`, `path: str`, `pattern: str = None`, `offset: int = 0`, `limit: int = 50` | 노드 파라미터의 이름/라벨/타입/튜플 크기/현재값 설명 |
| `set_node_flags` | `ctx`, `path: str`, `display/render/bypass/template: bool = None` | 노드 플래그 설정(전달한 플래그만 변경) |
| `layout_network` | `ctx`, `path: str` | 네트워크 노드의 자식들을 자동 정렬 |
| `find_error_nodes` | `ctx`, `root_path: str = "/obj"`, `include_warnings: bool = False` | 마지막 쿡에서 에러/경고가 발생한 노드 스캔 |
| `cook_node` | `ctx`, `path: str` | 노드를 강제 쿡하고 에러 여부 보고 |

### VEX / 지오메트리

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `create_wrangle` | `ctx`, `parent_path: str`, `vex_code: str`, `name: str = None`, `run_over: str = "points"`, `input_node: str = None` | VEX 스니펫을 담은 Attribute Wrangle SOP 생성 |
| `set_wrangle_code` | `ctx`, `path: str`, `vex_code: str`, `validate: bool = True` | 기존 wrangle 노드의 VEX 스니펫 교체 |
| `get_geometry_info` | `ctx`, `path: str` | 포인트/프리미티브/버텍스 카운트, 바운딩 박스 등 지오메트리 요약 |
| `get_geometry_data` | `ctx`, `path: str`, `element: str = "points"`, `attributes: List[str] = None`, `start: int = 0`, `limit: int = 100` | 지오메트리 속성값을 페이징하여 실제로 읽음(limit 상한 있음) |

### 렌더링

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `render_single_view` | `ctx`, `orthographic: bool = False`, `rotation: List[float] = [0,90,0]`, `render_path: str = "C:/temp/"`, `render_engine: str = "opengl"`, `karma_engine: str = "cpu"` | 단일 뷰 렌더 후 이미지 경로 반환 |
| `render_quad_views` | `ctx`, `render_path: str = "C:/temp/"`, `render_engine: str = "opengl"`, `karma_engine: str = "cpu"` | 4분할 캐노니컬 뷰 렌더 |
| `render_specific_camera` | `ctx`, `camera_path: str`, `render_path: str = "C:/temp/"`, `render_engine: str = "opengl"`, `karma_engine: str = "cpu"` | 특정 카메라 경로 기준 렌더 |

### OPUS 에셋 생성 (RapidAPI 연동, 선택적)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `opus_get_model_names` | `ctx` | 사용 가능한 OPUS 컴포넌트/구조 이름 목록 |
| `opus_get_model_params_schema` | `ctx`, `structure: str` | 특정 OPUS 모델 구조의 파라미터 스키마/포맷 안내 |
| `opus_create_model` | `ctx`, `structure: str`, `parameters: Dict[str, Any]`, `count: int = 1` | OPUS API로 3D 모델 생성 배치 작업 시작 |
| `opus_variate_model` | `ctx`, `result_id: str`, `count: int = 12` | 기존 OPUS 결과의 변형(variation) 배치 작업 시작 |
| `opus_check_job_status` | `ctx`, `batch_id: str` | OPUS 배치 작업 상태 확인 |
| `opus_import_model_url` | `ctx`, `download_url: str`, `node_name: str = None` | URL에서 모델(USD zip)을 다운로드해 씬에 임포트 |

**합계: 25개** (`grep -c "^@mcp.tool" houdini_mcp_server.py` = 25). OPUS는 [RapidAPI](https://rapidapi.com/genel-gi78OM1rB/api/opus5) 키가 필요한 서드파티 절차적 에셋(가구/환경) 생성 서비스 연동이며, 키가 없어도 서버는 기동하고 OPUS 6개 툴만 비활성화된다.

## 2. 아키텍처

### (a) 트랜스포트

- MCP 브리지(`houdini_mcp_server.py`)는 **stdio**로 실행된다. `mcp[cli]` SDK를 사용하며 Claude Desktop / Cursor의 `claude_desktop_config.json`에 `"command": "uv", "args": ["run","python","houdini_mcp_server.py"]` 형태로 등록.
- Houdini 쪽(`server.py`)은 MCP 프로토콜과 무관한 **자체 TCP 소켓 서버**(기본 `localhost:9876`)로, 브리지 프로세스와 1:1로 통신한다.

### (b) Houdini와의 통신

- **소켓 기반**(hrpyc 아님). `HoudiniMCPServer`가 `socket.socket(AF_INET, SOCK_STREAM)`으로 논블로킹 리스닝 소켓을 열고, 브리지 스크립트가 클라이언트로 접속한다.
- 프로토콜: **4바이트 빅엔디안 길이 프리픽스 + UTF-8 JSON** 페이로드(소켓 코드 주석에 명시).
- 브리지 쪽 `_houdini_call(cmd_type, params)` 헬퍼가 명령을 보내고 응답을 받는 저수준 클라이언트 역할을 한다.
- 새 클라이언트가 접속하면 기존(유휴/방치된) 클라이언트를 밀어내고 최신 접속이 슬롯을 차지하도록 설계되어 있다("the newest client wins").

### (c) 메인 스레드 안전성

- **`QtCore.QTimer` 기반 폴링**으로 메인 스레드 안전성을 확보한다. `HoudiniMCPServer.start()`가 100ms 주기 `QTimer`를 설치하고 `timeout` 시그널을 `_process_server`에 연결한다. 이 타이머는 Houdini의 Qt 이벤트 루프에서 실행되므로, 소켓 accept/read 및 `hou` 호출이 전부 **Houdini 메인 스레드**에서 일어난다.
- `_process_server` 도크스트링에 명시: *"This runs in the main Houdini thread to avoid concurrency issues."*
- 워커 스레드에서 `hou`를 직접 건드리는 코드 경로는 없음 — blender-mcp의 `bpy.app.timers` 패턴과 동일한 접근이다.
- 파라미터 설정 시 `hou.undos.group(f"MCP: {cmd_type}")`로 언두 그룹을 감싸 원자적 undo 단위를 제공한다.

### (d) 툴 등록 방식

- **하드코딩**. `houdini_mcp_server.py`에 25개 `@mcp.tool()` 함수가 나열되어 있으며, 플러그인/레지스트리 방식의 동적 등록은 없다.

### (e) Houdini 쪽 설치 방식

- **수동/셸프 방식**. `houdinimcp` Python 패키지 폴더(`__init__.py`, `server.py`, `houdini_mcp_server.py`, `pyproject.toml`)를 `Documents/houdini19.5/scripts/python/houdinimcp/`에 직접 복사.
- **셸프 툴**을 수동으로 만들어(`shelf_tool_start_mcp.py`/`shelf_tool_stop_mcp.py` 참고) `houdinimcp.start_server()`/`stop_server()` 토글.
- **패키지 JSON**(`houdinimcp.json`)을 통한 자동 로드 옵션도 문서화되어 있음(`packages/` 폴더에 배치, `PYTHONPATH` 확장).
- MCP 쪽 Python 패키지(`mcp[cli]`)는 `uv add` 또는 `pip`로 별도 설치.

## 3. 의존성

`pyproject.toml` / `uv.lock` 기준:

- `mcp[cli]>=1.4.1` (lock 고정 버전: **`mcp==1.4.1`**) — 공식 Anthropic MCP Python SDK 사용(FastMCP 아님, `mcp.server.fastmcp`의 표준 SDK 내장 FastMCP 사용)
- `requests>=2.31.0`
- `python-dotenv>=1.0.0`
- `langchain>=0.1.0`, `langchain-classic>=1.0.0` — OPUS 파라미터 포맷팅/변환 로직에 사용되는 것으로 추정(직접적인 LLM 체인 호출은 상단 코드에서 확인되지 않음, OPUS 관련 헬퍼 함수들과 함께 위치)
- lock 파일 기준 `pydantic==2.10.6`
- Python `>=3.12` 요구 (`.python-version` = `3.12`)

## 4. 지원 버전 / 활동성

- **지원 Houdini 버전**: README 예시 경로가 전부 `houdini19.5` 기준(Houdini 19.5). 코드 자체(`hou.Vector2/3/4`, `hou.Quaternion`, `hou.SopNode`, `hou.OperationFailed` 등 표준 HOM API만 사용)는 특정 버전에 강하게 종속되지 않아 실제로는 더 넓은 범위에서 동작할 가능성이 있으나, 문서화된 버전은 19.5뿐이다.
- **마지막 커밋(조사 시점)**: 2026-06-11 (`de4fd93a`), `pushed_at` 동일.
- **GitHub 스타 수**: 292 (조사 시점, `gh api repos/capoomgit/houdini-mcp`) — 세 저장소 중 스타 수가 가장 많다.
- CI/릴리스 워크플로, 테스트 스위트(`tests/test_tools.py`, `tests/headless_host.py`)는 있으나 oculairmedia 저장소만큼 프로세스 문서(ADR 등)가 풍부하지는 않다.
