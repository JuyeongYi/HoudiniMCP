# healkeiser/fxhoudinimcp 조사 문서

- **저장소**: https://github.com/healkeiser/fxhoudinimcp
- **조사 시점 커밋**: `4462529063ecb88561b3c62596680db62ca51f2b` (2026-07-29 18:17:21 +00:00)
- **조사일**: 2026-09-09
- **스타 수**: 202 (조사 시점, `gh api repos/healkeiser/fxhoudinimcp` 기준)
- **마지막 push**: 2026-07-29T18:17:45Z
- **조사 방법**: `git clone --depth 1`로 로컬에 clone한 뒤, `python/fxhoudinimcp/tools/*.py`(23개 파일) 전체를 Python `ast` 모듈로 파싱해 `@mcp.tool()`이 붙은 함수 188개 전량을 기계적으로 추출. Houdini 플러그인 쪽(`houdini/scripts/python/fxhoudinimcp_server/`)과 `README.md`, `pyproject.toml`도 직접 읽어 확인. WebFetch 대체 없이 전량 코드 확인.

---

## 1. 툴 전수 목록

`python/fxhoudinimcp/tools/__init__.py`가 23개 서브모듈을 임포트하며, 각 서브모듈이 임포트 시점에 `@mcp.tool()` 데코레이터로 툴을 등록한다(부작용 기반 등록). 실제 코드에서 `@mcp.tool()` 개수를 세면 **188개**로, README가 주장하는 "188 tools across 23 categories"와 정확히 일치한다(파일 1개 = 카테고리 1개로 1:1 대응). 단, `pyproject.toml`의 `description` 필드는 "179 tools"라고 적혀 있어 실제 코드/README와 어긋나는 낡은 값이다.

모든 툴 함수는 첫 인자로 FastMCP가 주입하는 `ctx: Context`를 받는다(아래 표에서는 지면상 생략하고 그 외 파라미터만 표기). 파라미터 타입은 코드의 타입 힌트를 그대로 옮겼다(`Value`는 `fxhoudinimcp._types`가 정의하는, JSON 스칼라/리스트/딕트를 아우르는 파라미터 값 타입).

README의 카테고리별 툴 개수 표와 실제 코드를 대조한 결과, **두 카테고리에서 불일치가 발견**되었다(총합 188은 우연히 유지됨):
- **Scene Management**: README "7" vs 실제 `scene.py` 8개 (`get_houdini_connection_status`가 표에 누락된 것으로 보임)
- **Materials**: README "5" vs 실제 `materials.py` 4개

아래 표는 실제 코드(`ast` 파싱) 기준이며, 위 두 곳은 실제 값으로 표기했다.

### Graph Intelligence — `tools/graph.py` (6개)

네트워크 단위의 원자적 구축/검증/프로파일링을 담당하는, README가 "시니어 아티스트 툴셋"이라 부르는 카테고리.

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `build_network` | `parent_path:str`, `nodes:list[dict[str, Any]]`, `dry_run:bool`, `layout:bool` | 노드 3개 이상의 네트워크를 하나의 원자적 호출로 구축 — 노드별 개별 호출보다 훨씬 빠르고 전체가 성공하거나 전체가 실패한다. `dry_run=True`로 씬을 건드리지 않고 사전 검증 가능 |
| `verify_network` | `parent_path:str` | 네트워크의 모든 노드를 한 번에 점검 — 에러/경고/플래그, 디스플레이 노드의 쿡된 지오메트리 카운트 |
| `get_node_card` | `node_type:str`, `context:str`, `parm_filter:str \| None` | 실행 중인 Houdini에서 노드 타입의 공식 문서 카드(실제 커넥터 라벨, 실제 파라미터 이름/기본값/메뉴, 노드 자체의 내장 도움말)를 가져옴 |
| `find_expensive_nodes` | `root_path:str`, `frame:float \| None`, `limit:int` | 쿡 프로파일링을 수행해 가장 느린 노드를 순위별로 나열 |
| `cook_frame_range` | `node_path:str`, `start:float \| None`, `end:float \| None`, `step:float`, `attribs:list[str] \| None`, `volumes:bool` | 노드를 프레임 단위로 쿡하며 각 프레임에서 변한 내용을 보고 |
| `get_cook_status` | `node_path:str` | 노드가 쿡되었는지, 얼마나 자주, 시간 종속적인지 여부 확인 |

### Documentation — `tools/help.py` (2개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `search_help` | `query:str`, `scope:str \| None`, `limit:int` | 실행 중인 Houdini 자체의 문서(개념/워크플로우/VEX 함수/표현식 함수/HOM API, SideFX가 제공하는 모든 이펙트 매뉴얼)를 전문 검색 — 설치본 버전과 정확히 일치 |
| `get_help_page` | `path:str` | Houdini에 내장된 문서에서 경로로 지정한 페이지 하나를 가져옴 |

### Scene Management — `tools/scene.py` (8개, README 표기는 7)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_houdini_connection_status` | (없음) | 연결 끊김에도 예외를 던지지 않고 브리지 상태를 확인 |
| `get_scene_info` | (없음) | 현재 Houdini 씬 정보 조회 |
| `new_scene` | `save_current:bool` | 새 빈 씬 생성 |
| `save_scene` | `file_path:str \| None` | 현재 씬을 디스크에 저장 |
| `load_scene` | `file_path:str`, `merge:bool` | hip 파일 열기 또는 병합 |
| `import_file` | `file_path:str`, `parent_path:str`, `node_name:str \| None` | 지오메트리/USD/Alembic 파일을 씬으로 임포트 |
| `export_file` | `node_path:str`, `file_path:str`, `frame_range:list[float] \| None` | 노드 출력을 파일로 내보내고 실제로 생성되었는지 보고 |
| `get_context_info` | `context:str` | Houdini 네트워크 컨텍스트 정보 조회 |

### Node Operations — `tools/nodes.py` (17개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `create_node` | `parent_path:str`, `node_type:str`, `name:str \| None`, `position:list[float] \| None` | 부모 네트워크 안에 노드 생성 |
| `delete_node` | `node_path:str` | 노드 삭제 |
| `rename_node` | `node_path:str`, `new_name:str` | 노드 이름 변경 |
| `copy_node` | `node_path:str`, `dest_parent:str \| None`, `new_name:str \| None` | 노드 복사(다른 부모 네트워크로도 가능) |
| `move_node` | `node_path:str`, `dest_parent:str` | 노드를 다른 부모 네트워크로 이동 |
| `get_node_info` | `node_path:str` | 타입, 연결, 플래그, 에러, 쿡 시간, 기본값과 다른 파라미터 정보 조회 |
| `list_children` | `parent_path:str`, `recursive:bool`, `filter_type:str \| None` | 네트워크 노드의 자식 목록 |
| `find_nodes` | `pattern:str \| None`, `node_type:str \| None`, `context:str \| None`, `inside:str` | 이름 패턴/타입/컨텍스트로 노드 검색 |
| `list_node_types` | `context:str`, `filter:str \| None`, `limit:int` | 컨텍스트 카테고리의 사용 가능한 노드 타입 목록 |
| `connect_nodes` | `source_path:str`, `dest_path:str`, `output_index:int`, `input_index:int` | 두 노드 연결 |
| `connect_nodes_batch` | `connections:list[dict[str, Any]]` | 여러 노드 쌍을 한 번에 연결 |
| `disconnect_node` | `node_path:str`, `input_index:int \| None`, `disconnect_all:bool` | 노드의 입력 하나 또는 전체 연결 해제 |
| `reorder_inputs` | `node_path:str`, `new_order:list[int]` | 노드 입력 연결 순서 재배열 |
| `set_node_flags` | `node_path:str`, `display:bool \| None`, `render:bool \| None`, `bypass:bool \| None`, `template:bool \| None`, `lock:bool \| None` | 노드 플래그(display/render/bypass/template/lock) 설정 |
| `layout_children` | `parent_path:str`, `spacing:float \| None` | 네트워크 자식 노드 자동 정렬 |
| `set_node_position` | `node_path:str`, `x:float`, `y:float` | 네트워크 에디터에서 노드 위치 설정 |
| `set_node_color` | `node_path:str`, `r:float`, `g:float`, `b:float` | 네트워크 에디터에서 노드 색상 설정 |

### Parameters — `tools/parameters.py` (12개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_parameter` | `node_path:str`, `parm_name:str` | 파라미터 값/메타데이터 조회 |
| `set_parameter` | `node_path:str`, `parm_name:str`, `value:Value` | 파라미터 값 설정 |
| `set_parameters` | `node_path:str`, `params:dict[str, Any]` | 노드의 여러 파라미터 일괄 설정 |
| `get_parameter_schema` | `node_path:str`, `parm_name:str \| None`, `filter:str \| None` | 노드 파라미터의 템플릿 스키마 조회 |
| `set_expression` | `node_path:str`, `parm_name:str`, `expression:str`, `language:str` | 파라미터에 표현식 설정 |
| `get_expression` | `node_path:str`, `parm_name:str` | 파라미터의 표현식 조회 |
| `revert_parameter` | `node_path:str`, `parm_name:str` | 파라미터를 기본값으로 되돌림 |
| `link_parameters` | `source_path:str`, `source_parm:str`, `dest_path:str`, `dest_parm:str` | 한 파라미터에서 다른 파라미터로 채널 참조 생성 |
| `lock_parameter` | `node_path:str`, `parm_name:str`, `locked:bool` | 파라미터 잠금/해제 |
| `create_spare_parameter` | `node_path:str`, `parm_name:str`, `parm_type:str`, `label:str`, `default_value:Value \| None`, `min_val:float \| None`, `max_val:float \| None` | 노드에 spare 파라미터 추가 |
| `create_spare_parameters` | `node_path:str`, `parameters:list[dict[str, Any]]`, `folder_name:str \| None`, `folder_type:str` | 여러 spare 파라미터를 한 번에 생성(폴더 탭 옵션 포함) |
| `get_parameters` | `node_path:str`, `patterns:list[str] \| None`, `include_defaults:bool` | 이름 또는 라벨 부분 일치로 여러 파라미터 값을 한 번에 읽기 |

### Geometry (SOPs) — `tools/geometry.py` (14개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_geometry_info` | `node_path:str` | SOP 노드의 지오메트리 요약 정보 |
| `get_points` | `node_path:str`, `attributes:list[str] \| None`, `start:int`, `count:int`, `group:str \| None` | 페이지네이션과 함께 포인트 위치/속성 읽기 |
| `get_prims` | `node_path:str`, `attributes:list[str] \| None`, `start:int`, `count:int`, `group:str \| None` | 페이지네이션과 함께 프리미티브 데이터/속성 읽기 |
| `get_attrib_values` | `node_path:str`, `attrib_name:str`, `attrib_class:str`, `start:int`, `count:int` | 페이지네이션과 함께 속성 값을 평탄한 배열로 읽기 |
| `set_detail_attrib` | `node_path:str`, `attrib_name:str`, `value:Value` | SOP 노드에 detail 속성 설정 |
| `get_groups` | `node_path:str` | SOP 노드의 모든 지오메트리 그룹 목록 |
| `get_group_members` | `node_path:str`, `group_name:str`, `group_type:str`, `start:int`, `count:int` | 지오메트리 그룹의 요소 인덱스를 페이지네이션과 함께 조회 |
| `get_bounding_box` | `node_path:str` | SOP 노드 지오메트리의 바운딩 박스 조회 |
| `get_attribute_info` | `node_path:str`, `attrib_name:str`, `attrib_class:str` | 지오메트리 속성의 메타데이터 조회 |
| `sample_geometry` | `node_path:str`, `sample_count:int`, `seed:int` | SOP 노드 지오메트리에서 균등 분포 포인트 샘플링 |
| `get_prim_intrinsics` | `node_path:str`, `prim_index:int \| None` | 프리미티브의 intrinsic 값 조회 |
| `find_nearest_point` | `node_path:str`, `position:list[float]`, `max_results:int` | 주어진 위치에서 가장 가까운 포인트 검색 |
| `get_attrib_stats` | `node_path:str`, `attribs:list[str] \| None`, `attrib_class:str` | 수치 속성의 집계 통계(최소/최대/평균/합계) |
| `get_volume_info` | `node_path:str`, `max_volumes:int` | 볼륨별 이름/해상도/활성 복셀 수/값 범위 |

### LOPs/USD — `tools/lops.py` (18개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_stage_info` | `node_path:str` | LOP 노드의 USD 스테이지 정보 |
| `get_usd_prim` | `node_path:str`, `prim_path:str` | USD prim 상세 정보 |
| `list_usd_prims` | `node_path:str`, `root_path:str`, `prim_type:str \| None`, `kind:str \| None`, `depth:int \| None` | 필터링과 함께 스테이지의 USD prim 목록 |
| `get_usd_attribute` | `node_path:str`, `prim_path:str`, `attr_name:str`, `time:float \| None` | prim에서 USD 속성 값 읽기 |
| `get_usd_layers` | `node_path:str` | USD 스테이지의 모든 레이어 목록 |
| `get_usd_prim_stats` | `node_path:str`, `prim_path:str` | 루트 경로 하위의 USD 타입별 prim 카운트 |
| `get_last_modified_prims` | `node_path:str` | 마지막 LOP 노드 쿡에서 수정된 prim 조회 |
| `create_lop_node` | `parent_path:str`, `lop_type:str`, `name:str \| None`, `prim_path:str \| None` | 새 LOP 노드 생성 |
| `set_usd_attribute` | `node_path:str`, `prim_path:str`, `attr_name:str`, `value:Value` | 인라인 Python LOP을 통해 USD 속성 값 설정 |
| `get_usd_materials` | `node_path:str` | 스테이지의 모든 USD 머티리얼 목록 |
| `find_usd_prims` | `node_path:str`, `pattern:str` | 경로 패턴으로 USD prim 검색 |
| `get_usd_composition` | `node_path:str`, `prim_path:str` | USD prim의 컴포지션 아크 조회 |
| `get_usd_variants` | `node_path:str`, `prim_path:str` | USD prim의 variant set과 선택값 조회 |
| `inspect_usd_layer` | `node_path:str`, `layer_index:int` | 인덱스로 USD 레이어 검사 |
| `create_light` | `parent_path:str`, `light_type:str`, `name:str \| None`, `intensity:float`, `color:list[float] \| None`, `position:list[float] \| None` | LOP 네트워크에 USD 라이트 생성 |
| `list_lights` | `node_path:str` | LOP 스테이지의 모든 USD 라이트 목록 |
| `set_light_properties` | `node_path:str`, `prim_path:str`, `properties:dict[str, Any]` | 인라인 Python LOP을 통해 USD 라이트 prim 속성 설정 |
| `create_light_rig` | `parent_path:str`, `preset:str`, `intensity_mult:float` | LOP 네트워크에 프리셋 라이팅 리그 생성 |

### DOPs — `tools/dops.py` (8개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_simulation_info` | `node_path:str` | DOP 네트워크 시뮬레이션 상태 |
| `list_dop_objects` | `node_path:str` | 시뮬레이션의 모든 DOP 오브젝트 목록 |
| `get_dop_object` | `node_path:str`, `object_name:str` | 특정 DOP 오브젝트의 상세 데이터 |
| `get_dop_field` | `node_path:str`, `object_name:str`, `data_path:str`, `field_name:str` | DOP 레코드에서 특정 필드 값 읽기 |
| `get_dop_relationships` | `node_path:str` | DOP 오브젝트 간 모든 관계 목록 |
| `step_simulation` | `node_path:str`, `steps:int` | 시뮬레이션을 지정 프레임 수만큼 진행 |
| `reset_simulation` | `node_path:str` | 시뮬레이션을 초기 상태로 리셋 |
| `get_sim_memory_usage` | `node_path:str` | 시뮬레이션의 상세 메모리 사용량 |

### PDG/TOPs — `tools/tops.py` (10개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_top_network_info` | `node_path:str` | TOP 네트워크 개요 |
| `cook_top_node` | `node_path:str`, `block:bool`, `generate_only:bool` | TOP 노드를 쿡해 워크 아이템 실행 |
| `cancel_top_cook` | `node_path:str` | TOP 네트워크의 진행 중인 쿡 취소 |
| `pause_top_cook` | `node_path:str` | TOP 네트워크 쿡 일시정지 |
| `dirty_work_items` | `node_path:str`, `remove_outputs:bool` | TOP 노드의 워크 아이템을 dirty 처리(재생성 가능하도록) |
| `get_work_item_states` | `node_path:str` | TOP 노드의 워크 아이템 상태별 카운트 |
| `get_work_item_info` | `node_path:str`, `work_item_index:int` | 특정 워크 아이템의 상세 정보 |
| `get_pdg_graph` | `node_path:str` | TOP 네트워크의 PDG 의존성 그래프 구조 |
| `generate_static_items` | `node_path:str` | 쿡 없이 TOP 노드의 정적 워크 아이템 생성 |
| `get_top_scheduler_info` | `node_path:str` | 네트워크의 TOP 스케줄러 노드 정보 |

### COPs (Copernicus) — `tools/cops.py` (7개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_cop_info` | `node_path:str` | COP 노드 정보 조회 |
| `get_cop_geometry` | `node_path:str`, `output_index:int` | COP 노드에서 지오메트리 표현 가져오기 |
| `get_cop_layer` | `node_path:str`, `output_index:int` | COP 노드에서 이미지 레이어 데이터 가져오기 |
| `create_cop_node` | `parent_path:str`, `cop_type:str`, `name:str \| None` | 지정 네트워크에 COP 노드 생성 |
| `set_cop_flags` | `node_path:str`, `display:bool \| None`, `export_flag:bool \| None`, `compress:bool \| None` | COP 노드 플래그(display/export/compress) 설정 |
| `list_cop_node_types` | `filter:str \| None` | 사용 가능한 COP 노드 타입 목록 |
| `get_cop_vdb` | `node_path:str`, `output_index:int` | COP 노드에서 VDB 볼륨 데이터 가져오기 |

### HDAs — `tools/hda.py` (10개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `list_installed_hdas` | `filter:str \| None` | 설치된 모든 HDA 파일과 정의 목록 |
| `get_hda_info` | `node_path:str \| None`, `hda_file:str \| None`, `type_name:str \| None` | HDA 정의의 상세 정보 |
| `install_hda` | `file_path:str`, `force:bool` | 현재 세션에 HDA 파일 설치 |
| `uninstall_hda` | `file_path:str` | 현재 세션에서 HDA 파일 제거 |
| `reload_hda` | `file_path:str` | 디스크에서 HDA 파일 재로드 |
| `create_hda` | `node_path:str`, `hda_file:str`, `type_name:str`, `label:str`, `version:str` | 기존 subnet 노드로부터 새 HDA 생성 |
| `update_hda` | `node_path:str` | 현재 노드 내용을 HDA 정의에 저장 |
| `get_hda_sections` | `node_path:str` | HDA 정의의 모든 섹션 목록 |
| `get_hda_section_content` | `node_path:str`, `section_name:str` | HDA 정의의 특정 섹션 내용 읽기 |
| `set_hda_section_content` | `node_path:str`, `section_name:str`, `content:str` | HDA 정의의 특정 섹션에 내용 쓰기 |

### Animation — `tools/animation.py` (9개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `set_keyframe` | `node_path:str`, `parm_name:str`, `frame:float`, `value:float`, `slope:float \| None`, `accel:float \| None` | 파라미터에 단일 키프레임 설정 |
| `set_keyframes` | `node_path:str`, `parm_name:str`, `keyframes:list[dict]` | 파라미터에 여러 키프레임 일괄 설정 |
| `delete_keyframe` | `node_path:str`, `parm_name:str`, `frame:float` | 특정 프레임의 키프레임 삭제 |
| `get_keyframes` | `node_path:str`, `parm_name:str` | 파라미터의 모든 키프레임 조회 |
| `set_frame` | `frame:float` | 타임라인의 현재 프레임 설정 |
| `get_frame` | (없음) | 현재 프레임과 FPS 조회 |
| `set_frame_range` | `start:float`, `end:float` | 전역 프레임 범위 설정 |
| `set_playback_range` | `start:float`, `end:float` | 재생 범위(타임라인 초록 바) 설정 |
| `playbar_control` | `action:str`, `real_time:bool \| None`, `fps:float \| None` | 재생 제어(재생/정지/역재생) |

### Rendering — `tools/rendering.py` (9개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `render_viewport` | `output_path:str`, `resolution:list[int] \| None`, `camera:str \| None` | 현재 3D 뷰포트를 이미지 파일로 캡처 |
| `render_quad_view` | `output_path:str`, `resolution:list[int] \| None` | 4분할 뷰포트 전체를 각각의 이미지로 캡처 |
| `list_render_nodes` | (없음) | 씬의 모든 렌더(ROP/드라이버) 노드 목록 |
| `get_render_settings` | `node_path:str` | ROP 노드의 렌더 설정 조회 |
| `set_render_settings` | `node_path:str`, `settings:dict[str, Any] \| None` | ROP 노드에 렌더 파라미터 설정 |
| `create_render_node` | `renderer:str`, `name:str \| None`, `camera:str \| None`, `output_path:str \| None` | `/out`에 새 렌더(ROP) 노드 생성 |
| `start_render` | `node_path:str`, `frame_range:list[float] \| None` | 렌더링/파일 출력을 수행하는 노드 실행 |
| `render_node_network` | `node_path:str`, `output_path:str` | 노드의 네트워크 에디터 뷰 스크린샷 캡처 |
| `get_render_progress` | `node_path:str` | ROP 노드의 렌더 진행률/상태 조회 |

### VEX — `tools/vex.py` (5개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `create_wrangle` | `parent_path:str`, `vex_code:str`, `justification:str`, `run_over:str`, `name:str \| None` | VEX 코드로 Attribute Wrangle 노드 생성 |
| `set_wrangle_code` | `node_path:str`, `vex_code:str` | 기존 Attribute Wrangle 노드에 VEX 코드 설정 |
| `get_wrangle_code` | `node_path:str` | Attribute Wrangle 노드의 VEX 코드 읽기 |
| `create_vex_expression` | `node_path:str`, `parm_name:str`, `vex_code:str` | 파라미터에 VEX 표현식 설정 |
| `validate_vex` | `node_path:str` | 노드를 쿡해 에러를 확인함으로써 VEX 코드 검증 |

### Code Execution — `tools/code.py` (4개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `execute_python` | `code:str`, `justification:str`, `return_expression:str \| None` | Houdini 내부에서 임의 Python 코드 실행 — 문서상 "최후의 수단(LAST RESORT only)"으로만 사용하도록 명시 |
| `execute_hscript` | `command:str` | Houdini에서 HScript 명령 실행 |
| `evaluate_expression` | `expression:str`, `language:str` | Houdini에서 표현식을 평가해 결과 반환 |
| `get_env_variable` | `var_name:str` | Houdini 환경 변수 값 조회 |

### Viewport/UI — `tools/viewport.py` (14개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `list_panes` | (없음) | Houdini UI에서 보이는 모든 pane tab 목록 |
| `get_viewport_info` | `pane_name:str \| None` | pane tab의 뷰포트 설정 조회 |
| `set_viewport_camera` | `camera_path:str`, `pane_name:str \| None` | 뷰포트가 특정 카메라를 보도록 설정 |
| `set_viewport_display` | `display_mode:str`, `pane_name:str \| None` | 뷰포트 셰이딩 모드 설정 |
| `set_viewport_renderer` | `renderer:str`, `pane_name:str \| None` | 라이브 프리뷰용 뷰포트의 Hydra 렌더 delegate 설정 |
| `frame_selection` | `pane_name:str \| None` | 현재 선택 항목을 뷰포트에 프레임 |
| `frame_all` | `pane_name:str \| None` | 뷰포트에 모든 지오메트리를 프레임 |
| `set_viewport_direction` | `direction:str`, `pane_name:str \| None` | 뷰포트를 표준 시점 방향으로 설정 |
| `capture_screenshot` | `output_path:str`, `pane_name:str \| None` | 뷰포트 또는 특정 pane tab 스크린샷 캡처 |
| `capture_network_editor` | `output_path:str`, `node_path:str \| None` | 네트워크 에디터 스크린샷 캡처 |
| `set_current_network` | `network_path:str` | 네트워크 에디터를 특정 네트워크 경로로 이동 |
| `find_error_nodes` | `root_path:str` | 씬에서 에러/경고가 있는 모든 노드 검색 |
| `log_status` | `message:str`, `severity:str` | Houdini 상태 표시줄에 메시지 표시 |
| `set_viewer_context` | `network_path:str`, `current_node:str \| None`, `pane_name:str \| None` | Scene Viewer를 특정 네트워크(및 선택적으로 그 안의 노드)로 지정 |

### Scene Context — `tools/context.py` (8개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_network_overview` | `path:str`, `depth:int` | 네트워크의 축약된 개요 조회 |
| `get_cook_chain` | `node_path:str` | 노드의 쿡 의존성 체인 추적 |
| `explain_node` | `node_path:str` | 노드를 사람이 읽기 쉬운 형태로 설명 |
| `get_selection` | (없음) | 현재 노드 선택 상태 조회 |
| `set_selection` | `node_paths:list[str] \| None` | 노드 선택 상태 설정 |
| `get_scene_summary` | (없음) | 씬의 상위 레벨 요약 |
| `compare_snapshots` | `action:str`, `snapshot_name:str` | 씬 상태 스냅샷을 찍거나 비교 |
| `get_node_errors_detailed` | `node_path:str \| None`, `root_path:str` | 노드의 상세 에러 분석 |

### Workflows — `tools/workflows.py` (8개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `setup_pyro_sim` | `source_geo:str`, `container:str`, `res_scale:float`, `substeps:int`, `name:str` | 소스 지오메트리로부터 Pyro 연기/불 시뮬레이션 네트워크 구축 |
| `setup_rbd_sim` | `geo_path:str`, `ground:bool`, `pieces_type:str`, `name:str` | 파괴/솔버를 포함한 RBD 강체 시뮬레이션 네트워크 구축 |
| `setup_flip_sim` | `source_geo:str`, `domain:str`, `particle_sep:float`, `name:str` | 소스 지오메트리로부터 FLIP 유체 시뮬레이션 네트워크 구축 |
| `setup_vellum_sim` | `geo_path:str`, `sim_type:str`, `substeps:int`, `name:str` | configure 노드와 솔버를 포함한 Vellum 시뮬레이션 네트워크 구축 |
| `create_material` | `name:str`, `mat_type:str`, `base_color:list[float] \| None`, `roughness:float`, `metallic:float`, `opacity:float` | 조정 가능한 서페이스 속성을 가진 머티리얼을 `/mat`에 생성 |
| `assign_material` | `geo_path:str`, `material_path:str` | Material SOP을 통해 지오메트리 노드에 머티리얼 할당 |
| `build_sop_chain` | `parent_path:str`, `steps:list[dict[str, Any]] \| None` | 한 번의 호출로 순차 연결된 SOP 노드 체인 구축 |
| `setup_render` | `renderer:str`, `camera:str \| None`, `output_path:str`, `resolution:list[int] \| None`, `samples:int`, `name:str` | 카메라와 ROP 노드를 포함한 렌더 구성 설정 |

### Materials — `tools/materials.py` (4개, README 표기는 5)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `list_materials` | `root_path:str` | 루트 경로 하위의 모든 머티리얼 노드 목록 |
| `get_material_info` | `node_path:str` | 머티리얼 노드의 상세 정보 |
| `create_material_network` | `name:str`, `shader_type:str`, `params:dict[str, Any] \| None` | `/mat`에 새 머티리얼 네트워크 생성 |
| `list_material_types` | `filter:str \| None` | 사용 가능한 VOP/머티리얼 노드 타입 목록 |

### CHOPs — `tools/chops.py` (4개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `get_chop_data` | `node_path:str`, `channel_name:str \| None`, `start:int \| None`, `end:int \| None` | CHOP 노드 트랙 데이터 조회 |
| `create_chop_node` | `parent_path:str`, `chop_type:str`, `name:str \| None` | 새 CHOP 노드 생성 |
| `list_chop_channels` | `node_path:str` | CHOP 노드의 모든 채널 목록 |
| `export_chop_to_parm` | `chop_path:str`, `channel_name:str`, `target_node_path:str`, `target_parm_name:str` | `chop()` 표현식을 통해 CHOP 채널을 파라미터로 내보내기 |

### Cache — `tools/cache.py` (4개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `list_caches` | `root_path:str` | 루트 경로 하위의 모든 캐시 타입 노드 목록 |
| `get_cache_status` | `node_path:str` | 캐시 노드의 상세 상태 조회 |
| `clear_cache` | `node_path:str`, `frame_range:list[int] \| None` | 캐시 노드의 디스크 캐시 파일 삭제 |
| `write_cache` | `node_path:str`, `frame_range:list[int] \| None` | 캐시 노드를 실행하고 실제로 캐시가 생성되었는지 보고 |

### Takes — `tools/takes.py` (4개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `list_takes` | (없음) | 씬의 모든 take를 계층 구조와 함께 목록화 |
| `get_current_take` | (없음) | 현재 take와 오버라이드된 파라미터 조회 |
| `set_current_take` | `name:str` | 이름으로 현재 take 설정 |
| `create_take` | `name:str`, `parent_name:str \| None` | 새 take 생성(선택적으로 부모 take 지정) |

### Shelf Tools — `tools/shelf.py` (3개)

| 툴 이름 | 파라미터 | 설명 |
|---|---|---|
| `list_shelf_tools` | `filter:str \| None`, `limit:int` | 이름/라벨/키워드로 셸프 툴 검색 |
| `get_shelf_tool_script` | `tool_name:str` | 셸프 툴이 실행하는 스크립트와 도움말/임포트 읽기 |
| `run_shelf_tool` | `tool_name:str`, `kwargs:dict[str, Any] \| None`, `parent_path:str \| None` | 셸프 툴을 실행하고 생성된 노드 보고 |

### 리소스(Resources)와 프롬프트(Prompts) — 참고

이 조사의 본 목적은 툴이지만, 참고로 README와 코드는 **8개 MCP Resources**(`python/fxhoudinimcp/resources/{geo_resources,scene_resources,usd_resources}.py`, 예: `houdini://scene/info` 같은 정적 URI)와 **9개 MCP Prompts**(`python/fxhoudinimcp/prompts/workflows.py`, 예: `simulation_setup`, `procedural_modeling_workflow`, `usd_scene_assembly`, `pdg_pipeline`, `hda_development`, `copernicus_workflow`, `heightfield_terrain`, `debug_scene`, `houdini_workflow`)를 함께 제공한다. 31개의 서면 워크플로우 가이드(마크다운)를 이 프롬프트들이 참조한다.

---

## 2. 아키텍처

**(a) 트랜스포트**: `stdio`가 기본값이며, 환경변수 `MCP_TRANSPORT`로 `streamable-http`로 전환 가능(`python/fxhoudinimcp/__main__.py`: `transport = os.getenv("MCP_TRANSPORT", "stdio")`). MCP SDK(`mcp` 패키지, `FastMCP`)를 그대로 사용.

**(b) Houdini와의 통신 방식**: Houdini에 내장된 `hwebserver`(HTTP 서버)를 그대로 사용한다. 커스텀 소켓 서버도, rpyc도 쓰지 않는다. `python/fxhoudinimcp/bridge.py`의 `HoudiniBridge`가 `httpx.AsyncClient`로 `http://{host}:{port}/api`에 `POST`하며, 바디는 `hwebserver`가 요구하는 RPC 컨벤션인 `json=["함수명", [위치 인자], {키워드 인자}]` 형식이다. 실제로는 모든 툴 호출이 단일 엔드포인트 `mcp.execute(command, params, request_id)`를 거치고, Houdini 쪽 `dispatcher.py`가 `command` 문자열(예: `"scene.get_scene_info"`)로 등록된 핸들러를 찾아 실행한다. 별도의 헬스체크(`mcp.health`, HOM을 건드리지 않아 메인 스레드가 막혀 있어도 응답)와 커맨드 목록 조회(`mcp.list_commands`, 플러그인-서버 버전 불일치 감지용)도 같은 방식으로 노출된다. 기본 포트는 8100이며, 두 번째 Houdini 세션이 뜨면 다음 빈 포트로 자동 이동하므로 MCP 서버 쪽은 8100부터 최대 16개 포트를 프로브해서 살아있는 세션을 찾는다(`find_servers`).

**(c) Houdini 메인 스레드 안전성**: `houdini/scripts/python/fxhoudinimcp_server/dispatcher.py`가 이를 명시적으로 처리한다. `hwebserver`의 핸들러는 워커 스레드에서 실행되므로, `hdefereval.executeInMainThreadWithResult()`로 실제 `hou.*` 호출을 메인 스레드로 마샬링하고 결과를 기다린다. 이 호출 자체를 다시 별도의 워커 스레드에서 감싸 `_COMMAND_TIMEOUT = 120`초의 타임아웃을 강제한다(메인 스레드가 영원히 막히는 경우에도 요청이 걸리지 않도록). `hython`(GUI 없는 단일 스레드 세션)처럼 `hdefereval`을 import할 수 없는 환경에서는 메인 스레드 마샬링 없이 핸들러를 직접 실행하는 폴백 경로를 갖는다(`HAS_HDEFEREVAL` 플래그). 순수 헬스체크(`mcp.health`)는 의도적으로 `hou`를 전혀 건드리지 않아 메인 스레드가 막혀 있어도(예: GUI 세션의 시작 대기 루프) 응답 가능하도록 설계되어 있다 — 코드 주석에 "여기서 HOM을 건드리면 GUI 세션이 데드락된다"고 명시.

**(d) 툴 등록 방식**: MCP 서버 쪽(`python/fxhoudinimcp/tools/`)은 23개 파일에 `@mcp.tool()` 데코레이터로 하드코딩되어 있고, `tools/__init__.py`가 이 23개 모듈을 명시적으로 import함으로써 등록을 트리거한다(플러그인 자동탐색은 아니지만, 카테고리별 파일 분리 + 단일 진입점 import라는 점에서 완전한 단일 파일 하드코딩과는 다르다). Houdini 플러그인 쪽(`houdini/scripts/python/fxhoudinimcp_server/handlers/`)은 한 단계 더 나아가 **레지스트리 패턴**을 쓴다: `dispatcher.py`가 `_handler_registry: dict[str, Callable]`를 유지하고 `register_handler(command, handler)`로 등록하며, `handlers/__init__.py`는 23개 핸들러 모듈 이름의 리스트(`_HANDLER_MODULES`)를 `importlib.import_module`로 동적 로드한다. 개별 모듈 로드가 실패해도 나머지는 계속 로드되고(`_loaded`/`_failed` 분리, 실패 목록을 로그로 남김), 몇 개 모듈이 로드됐고 몇 개 커맨드가 등록됐는지 시작 시 콘솔에 출력한다.

**(e) Houdini 쪽 설치 방식**: 패키지 JSON 기반의 완전 자동화된 설치기가 있다. `pip install fxhoudinimcp` 후 `python -m fxhoudinimcp install`을 실행하면 (1) 발견되는 모든 `Documents/houdiniXX.X/packages/` 디렉터리에 `fxhoudinimcp.json` 패키지 파일을 써서 Houdini 플러그인을 등록하고, (2) 실행에 사용된 Python 인터프리터의 절대 경로로 Claude Code/Claude Desktop 중 발견되는 MCP 클라이언트 설정 파일에 서버 항목을 등록한다. `--dry-run`, `--houdini-dir`, `--client-only`, `--client auto|claude-code|claude-desktop|both|none` 등의 플래그를 제공하며, 셸프 툴을 통한 수동 설치 방식은 아니다. Houdini 플러그인 자체는 pip wheel 안에 함께 포함되어 배포되므로(`tool.hatch.build.targets.wheel.force-include`) `pip install --upgrade`가 두 반쪽(서버/플러그인)을 함께 이동시킨다(단, 플러그인을 git clone에서 직접 로드하도록 설정한 경우는 예외이며, 이 경우 서버가 시작 시 플러그인 버전이 낡았음을 경고한다).

**아키텍처 다이어그램** (README 인용, Mermaid):
```
AI Client(Claude Desktop/Cursor/VS Code/Claude Code)
  --MCP 프로토콜(stdio)-->
FXHoudini MCP 서버(188 tools, 8 Resources, 9 Prompts)
  --HTTP/JSON(port 8100)-->
SideFX Houdini(hwebserver --> Dispatcher --> hou.* Handlers)
```

**호출 비용에 대한 문서화된 실측치** (Houdini 22.0.368, 빈 씬 기준): `health_check`(메인 스레드 경유 없음) 0.5ms, 일반 커맨드(빈 `/obj`의 `list_children` 포함) 약 50ms, 노드 10개를 한 번에 하나씩 생성 시 약 800ms — 이 때문에 문서(`server_instructions.md`)는 `build_network`/`connect_nodes_batch`/`set_parameters` 같은 배치 툴을 개별 호출보다 강하게 권장한다.

---

## 3. 의존성

`pyproject.toml` 기준:
- `mcp>=1.14.0,<3` — 주석에 따르면 1.14 미만은 `from __future__ import annotations`로 인해 문자열화된 타입 힌트를 FastMCP가 해석하지 못해 툴 등록 시 `TypeError`가 나서 실질적으로 동작하지 않았다고 명시. `mcp` 2.0의 `Server` 클래스 이동/`Tool.inputSchema` → `input_schema` 변경 등은 `fxhoudinimcp._sdk`라는 단일 shim 모듈에서 흡수한다.
- `httpx>=0.27.0` (MCP 서버 → Houdini HTTP 브리지)
- `pydantic>=2.0.0`
- `requires-python = ">=3.10"` (MCP 서버 프로세스는 Houdini 내장 Python과는 별개의 Python)
- 개발 의존성(`dev` extra): `pytest>=8.0`, `pytest-asyncio>=0.24`, `pytest-cov>=5.0`, `ruff>=0.8.0`
- 문서화 의존성(`mkdocs` extra): `mkdocs-material` 등 mkdocs 생태계 일체
- 빌드 시스템: `hatchling` + `hatch-vcs`(버전을 git 태그에서 유도)

---

## 4. 지원 Houdini 버전 / 커밋 / 스타

- **지원 Houdini 버전**: README 명시 — **Houdini 20.5+**. "integration suite green on 20.5.278, 20.5.487, 20.5.613, 20.5.654, 21.0.440 and 22.0.368"이라고 구체적 빌드 번호까지 명시. `server_instructions.md`에도 "this server supports"라며 20.5–22.0 범위를 노드 도메인 문서의 버전 어노테이션 기준으로 삼는다고 되어 있다. Red Giant/Maxon Universe의 OpenFX 플러그인이 설치된 경우 Houdini 20.5.487 이상에서 `hou` 초기화가 크래시하는 알려진 충돌이 있어 `HOUDINI_DISABLE_OPENFX_DEFAULT_PATH=1` 환경변수 설정이 필요하다고 문서화되어 있음(이 저장소의 결함은 아니라고 명시).
- **마지막 커밋**: `4462529063ecb88561b3c62596680db62ca51f2b`, 2026-07-29 18:17:21 +00:00
- **스타 수**: 202 (2026-09-09 조사 시점)
- **PyPI 배포**: `pip install fxhoudinimcp`로 설치 가능한 정식 PyPI 패키지로 배포되고 있음(eliiik/houdini-mcp는 PyPI 미배포, git clone 실행 방식).
