# oculairmedia/houdini-mcp 조사 보고서

- **저장소**: https://github.com/oculairmedia/houdini-mcp
- **조사 시점 커밋**: `7e5cd7a2484b899a6e9251c6f7b90228c2ec7990` (2026-07-10, `main`)
- **조사일**: 2026-09-09
- **조사 방법**: `git clone --depth 1`로 로컬 클론 후 소스 직접 열람 (WebFetch 미사용)

## 1. 툴 전수 목록

`houdini_mcp/server.py`에 `@mcp.tool()` 데코레이터로 43개 툴이 정의되어 있다 (README의 "43 MCP tools" 주장과 일치). 각 툴은 `houdini_mcp/tools/*.py`의 순수 함수를 얇게 감싸는 형태이며, 실제 로직은 15개 카테고리 모듈(`_common`, `cache`, `code`, `errors`, `geometry`, `help`, `hscript`, `layout`, `materials`, `nodes`, `pane_screenshot`, `parameters`, `rendering`, `scene`, `summarization`, `transactions`, `wiring`)에 나뉘어 있다.

### 씬/파일 관리 (scene)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_scene_info` | (없음) | 현재 Houdini 씬 정보(hip 경로, 버전, `/obj` 노드 목록) 조회 |
| `save_scene` | `file_path: str \| None` | 현재 씬 저장 |
| `load_scene` | `file_path: str` | 씬 파일 로드 |
| `new_scene` | (없음) | 새 빈 씬 생성 |
| `serialize_scene` (async) | `root_path: str = "/obj"`, `include_params: bool = False`, `summarize: bool = False` | 씬 구조를 dict로 직렬화 |
| `get_last_scene_diff` | (없음) | 마지막 `execute_code` 호출의 씬 diff 조회 |

### 노드 조작 (nodes)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `create_node` | `node_type: str`, `parent_path: str = "/obj"`, `name: str \| None` | 새 노드 생성 |
| `get_node_info` | `node_path: str`, `include_params: bool = True`, `include_input_details: bool = True`, `include_errors: bool = False`, `force_cook: bool = False`, `compact: bool = False` | 노드 상세 정보 조회 |
| `delete_node` | `node_path: str` | 노드 삭제 |
| `list_node_types` | `category: str \| None`, `max_results: int = 100`, `name_filter: str \| None`, `offset: int = 0`, `limit: int \| None`, `cursor: int \| None` | 사용 가능한 노드 타입 목록 (페이징 지원) |
| `list_children` | `node_path: str`, `recursive: bool = False`, `max_depth: int = 10`, `max_nodes: int = 1000`, `compact: bool = False`, `limit: int = 20`, `cursor: int \| None` | 자식 노드 목록(경로/타입/입력 연결 포함) |
| `find_nodes` | `root_path: str = "/obj"`, `pattern: str = "*"`, `node_type: str \| None`, `max_results: int = 100`, `offset: int = 0`, `limit: int \| None`, `cursor: int \| None` | glob/부분일치로 노드 검색 |
| `set_node_color` | `node_path: str`, `color: list[float]` | 노드 표시 색상 설정 |
| `set_node_position` | `node_path: str`, `x: float`, `y: float` | 네트워크 에디터 상 노드 위치 설정 |
| `layout_children` | `node_path: str`, `horizontal_spacing: float = 2.0`, `vertical_spacing: float = 1.0` | 자식 노드 자동 레이아웃 |
| `create_network_box` | `parent_path: str`, `node_paths: list[str]`, `label: str = ""`, `color: list[float] \| None` | 노드 그룹을 감싸는 네트워크 박스 생성 |

### 파라미터 (parameters)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `set_parameter` | `node_path: str`, `param_name: str`, `value: float\|int\|str\|bool\|list[float]\|list[int]\|list[str]` | 노드 파라미터 값 설정 |
| `get_parameter_schema` | `node_path: str`, `parm_name: str \| None`, `max_parms: int = 100` | 파라미터 메타데이터/스키마 조회 |

### 코드 실행 (code)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `execute_code` | `code: str`, `capture_diff: bool = False`, `max_stdout_size/max_stderr_size: int = 100000`, `max_diff_nodes: int = 1000`, `timeout: int = 30`, `allow_dangerous: bool = False`, `allow_heavy_geometry: bool = False`, `policy: str = "normal"` | Houdini에서 임의 Python 코드 실행. 씬 변경 추적 및 안전 정책(read-only/normal/privileged) 지원 |

### 배선/연결 (wiring)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `connect_nodes` | `src_path: str`, `dst_path: str`, `dst_input_index: int = 0`, `src_output_index: int = 0` | 소스 노드 출력을 대상 노드 입력에 연결 |
| `disconnect_node_input` | `node_path: str`, `input_index: int = 0` | 입력 연결 해제 |
| `set_node_flags` | `node_path: str`, `display/render/bypass: bool \| None` | 디스플레이/렌더/바이패스 플래그 설정 |
| `reorder_inputs` | `node_path: str`, `new_order: list[int]` | merge 노드 등의 입력 순서 재정렬 |

### 렌더링 (rendering)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `render_viewport` | `camera_position/rotation: list[float] \| None`, `look_at: str \| None`, `resolution: list[int] \| None`, `renderer: str = "opengl"`, `output_format: str = "png"`, `auto_frame: bool = True`, `orthographic: bool = False`, `karma_engine: str = "cpu"` | 뷰포트 렌더 후 base64 이미지 반환 |
| `render_quad_view` | `resolution: list[int] \| None`, `renderer: str = "opengl"`, `output_format: str = "png"`, `orthographic: bool = True`, `include_perspective: bool = True`, `karma_engine: str = "cpu"` | Front/Left/Top/Perspective 4분할 렌더 |
| `list_render_nodes` | (없음) | `/out` 컨텍스트의 ROP 노드 목록 |
| `get_render_settings` | `rop_path: str` | ROP 렌더 설정 조회 |
| `set_render_settings` | `rop_path: str`, `settings: dict[str, Any]` | ROP 렌더 설정 수정 |
| `create_render_node` | `rop_type: str`, `name: str \| None`, `settings: dict[str, Any] \| None` | ROP 노드 생성(+설정) |

### 에러/연결 상태 (errors, connection)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `find_error_nodes` (async) | `root_path: str = "/"`, `include_warnings: bool = True`, `max_results: int = 100`, `summarize: bool = False` | 쿡 에러/경고가 있는 모든 노드 검색 |
| `check_connection` | (없음) | Houdini 연결 상태 상세 조회 |
| `ping_houdini` | (없음) | 빠른 연결성 테스트 |

### 지오메트리/헬프 (geometry, help)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_geo_summary` (async) | `node_path: str`, `max_sample_points: int = 16`, `include_attributes: bool = True`, `include_groups: bool = True`, `summarize: bool = False` | 지오메트리 통계/메타데이터(검증용) |
| `get_houdini_help` | `help_type: str`, `item_name: str`, `timeout: int = 10` | SideFX 웹사이트에서 Houdini 문서 스크래핑(`requests`+`beautifulsoup4`) |

### 머티리얼 (materials)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `create_material` | `material_type: str = "principledshader"`, `name: str \| None`, `parent_path: str = "/mat"`, `parameters: dict \| None` | 머티리얼/셰이더 노드 생성 |
| `assign_material` | `geometry_path: str`, `material_path: str`, `group: str = ""` | 지오메트리에 머티리얼 할당 |
| `get_material_info` | `material_path: str` | 머티리얼 노드 상세 정보 |

### 캐시/요약 상태 (cache, summarization)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `manage_cache` | `action: str = "stats"` | 노드 타입 캐시(TTL) 관리 |
| `get_summarization_status` | (없음) | AI 요약(응답 축약) 설정/상태 조회 |

### 패널 스크린샷 (pane_screenshot)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `capture_pane_screenshot` | `pane_type_name: str = "NetworkEditor"`, `save_path: str \| None`, `fit_contents: bool = False` | 지정 pane 탭 스크린샷 캡처 |
| `list_visible_panes` | (없음) | 현재 레이아웃의 표시된 pane 탭 목록 |
| `capture_multiple_panes` | `pane_types: list[str]`, `save_dir: str \| None` | 여러 pane 타입 스크린샷 일괄 캡처 |
| `render_node_network` | `node_path: str = "/obj"`, `fit_contents: bool = True` | 특정 노드의 자식들을 보여주는 네트워크 스크린샷 |

**합계: 43개** (`grep -c "^@mcp.tool" houdini_mcp/server.py` = 43)

## 2. 아키텍처

### (a) 트랜스포트

- 기본은 **HTTP**(`run_server(transport="http", port=3055)`, FastMCP `mcp.run(transport="http", host="0.0.0.0", port=port)`). `FastMCP`가 `Literal["stdio", "http", "sse", "streamable-http"]`를 받으므로 stdio/SSE/streamable-http로도 전환 가능.
- 별도로 **Houdini 플러그인(`houdini_plugin/`)**을 설치하면 MCP 서버가 Houdini 프로세스 **내부에서 stdio 모드**로 직접 실행되는 옵션도 제공한다 (shelf 툴 `mcp_start`가 `houdini_mcp_plugin.start_server(use_thread=True)`를 호출, README의 "Option 1: Houdini Plugin (stdio mode)").
- `/health` 커스텀 라우트(GET)로 컨테이너 헬스체크 지원. Docker(`Dockerfile`, `compose.yaml`) 배포를 전제로 한 구조.

### (b) Houdini와의 통신

- README 제목 그대로 **`hrpyc`(Houdini 내장 RPyC classic 서버) 기반**. 다만 `houdini_mcp/connection.py`는 `hrpyc` 모듈 자체가 아니라 **`rpyc.classic.connect()`를 직접 사용**한다 (hrpyc는 PyPI에 없고 Houdini 번들 전용이라 rpyc 5.x로 대체). `rpyc`는 반드시 5.x여야 하며 6.x는 Houdini의 hrpyc와 프로토콜 비호환이라고 명시.
- 연결 대상은 `HOUDINI_HOST`/`HOUDINI_PORT`(기본 `localhost:18811`) 환경 변수로 설정.
- 재시도: `retry_with_backoff` 데코레이터로 지수 백오프 + 지터, 최대 재시도/지연 상한 설정 가능.
- 최근 추가된 `houdini_plugin/python/houdini_mcp_plugin/listener.py`는 **원격에서 접근 가능한 hrpyc 리스너를 Houdini 쪽에서 안전하게 활성화**하는 기능(“remote mode”)을 제공한다. 루프백 외 바인드는 `HOUDINI_RPC_TRUSTED_NETWORK=1` 또는 `HOUDINI_RPC_TOKEN` 없이는 거부되도록 보안 정책이 하드코딩되어 있다 (`docs/remote-listener.md`).

### (c) 메인 스레드 안전성

- 코드베이스 전체에서 `hdefereval`, `executeInMainThreadWithResult`, `executeDeferred` 같은 명시적 메인 스레드 마샬링 API 사용을 찾지 못했다. 즉 **MCP 서버 프로세스가 `hrpyc`/rpyc RPC를 통해 Houdini 프로세스 안의 SlaveService(또는 원격 리스너) 스레드에서 직접 `hou` 객체를 조작**하며, 별도의 메인 스레드 큐잉 계층은 두지 않는다.
- `execute_code` 툴은 대신 **애플리케이션 레벨 안전장치**를 둔다: 정책 프로파일(`read-only`/`normal`/`privileged`), 위험 패턴 탐지(`eval`/`exec`/`compile`/`__import__`, `socket`/`urllib`/`requests`/`http` 등 네트워크 egress, 공백 난독화 탐지), 서버 측 게이트(`HOUDINI_MCP_ALLOW_BYPASS=true`)와 요청 플래그의 AND 조건, 실행 후 구조화된 `audit` 블록(정책·요청된 우회·탐지 패턴·코드 해시·타임아웃/롤백 상태) 반환. 타임아웃 시 `hou.undos.performUndo()`를 자동 호출하지 않고 `rollback.thread_still_running=true`만 보고한다(사람의 이전 작업을 실수로 되돌리지 않기 위함).
- `houdini_plugin`의 원격 리스너 쪽도 스레드/소켓 관리(`threading`, `socket`)는 있으나 이는 hrpyc 리스너의 바인드/보안 관리이지, `hou` 호출 자체를 메인 스레드로 마샬링하는 계층은 아니다.

### (d) 툴 등록 방식

- **하드코딩**. `houdini_mcp/server.py`에 43개 `@mcp.tool()` 함수가 직접 나열되어 있으며, 각 함수는 `houdini_mcp/tools/<category>.py`의 순수 함수를 호출하는 얇은 래퍼다. 플러그인/레지스트리 기반 동적 등록 메커니즘은 없다.

### (e) Houdini 쪽 설치 방식

- **패키지 JSON 방식**: `houdini_plugin/houdini_mcp.json`(env: `HOUDINI_MCP_ROOT`, `PYTHONPATH` prepend)을 `%USERPROFILE%\Documents\houdini20.5\packages\`에 복사하고 `houdini_plugin` 폴더 자체를 패키지 경로로 등록.
- **셸프 툴**도 함께 제공(`houdini_plugin/toolbar/houdini_mcp.shelf`): `mcp_start`/`mcp_stop`/`mcp_status`/`hrpyc_start`/`hrpyc_stop`/`hrpyc_status`/`hrpyc_selftest` 7개 버튼.
- 원격/Docker 배포 시에는 Houdini 쪽에서 `import hrpyc; hrpyc.start_server(port=18811)`을 수동 실행(또는 `123.py` 시작 스크립트에 추가)하는 **수동 방식**도 병행 지원.

## 3. 의존성

`pyproject.toml` / `requirements.txt` 기준:

- `fastmcp>=0.1.0` — MCP 서버 프레임워크(공식 `mcp` SDK가 아닌 FastMCP 사용)
- `rpyc>=5.0.0,<6.0.0` — Houdini hrpyc와의 통신 (6.x 명시적 배제)
- `python-dotenv>=1.0.0`
- `requests>=2.28.0`, `beautifulsoup4>=4.11.0` — `get_houdini_help`의 SideFX 문서 스크래핑용
- 개발 의존성: `pytest`, `pytest-cov`, `pytest-asyncio`, `hypothesis`(속성 기반/상태 기계 테스트), `ruff`, `mypy`, `pre-commit`, `bandit[toml]`
- `pydantic`은 직접 명시되어 있지 않음(FastMCP의 전이 의존성으로 포함될 것으로 추정, 코드에서 직접 pydantic import는 확인하지 못함)
- Python `>=3.10` 요구

## 4. 지원 버전 / 활동성

- **지원 Houdini 버전**: README/패키지 예시가 `houdini20.5` 경로를 사용(Houdini 20.5 기준 문서화). 코드 자체는 `hou` 모듈 버전에 종속적이지 않게 작성되어 있어 특정 버전에 하드 종속되지는 않음.
- **마지막 커밋(조사 시점)**: 2026-07-10 (`7e5cd7a2`), 저장소 `pushed_at`은 2026-07-29.
- **GitHub 스타 수**: 64 (조사 시점, `gh api repos/oculairmedia/houdini-mcp`).
- CI(`ci.yml`), GHCR 퍼블리시(`publish-ghcr.yml`), 릴리스 워크플로(`release.yml`)를 갖춘 비교적 성숙한 저장소이며, ADR(`docs/adr/0001-language-and-process-boundaries.md`)로 아키텍처 의사결정을 문서화하는 등 엔지니어링 프로세스가 상세하다.
