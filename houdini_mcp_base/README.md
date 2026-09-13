# houdini_mcp_base

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_base.json` |
| requires | `houdini_mcp` |
| 툴 | 104개 |
| 모듈 (`TOOL_MODULES`) | `info`, `edit`, `parms`, `parmedit`, `transform`, `context`, `explain`, `analyze`, `geometry`, `cache`, `viewport`, `video`, `visualize`, `nodetypes`, `scene`, `deps`, `portability`, `takes`, `diagnose`, `anim`, `execute` |

## 개요

```text
모든 작업의 토대가 되는 툴 팩.

어떤 컨텍스트에서 무엇을 하든 쓰이는 것들을 담는다. 모듈로만 나눈다.

    info       씬·노드·그래프 조회
    edit       네트워크 종류를 가리지 않는 노드 생성·조작·연결
    parms      파라미터 조회
    parmedit   파라미터 자체를 고친다 - 스페어 추가, 링크, 잠금, 되돌리기
    transform  노드 변환과 OBJ 계층 - world/parm/local/pre 를 갈라서 본다
    context    노드 트리와 의존 관계 - 직접 연결뿐 아니라 간접 참조까지
    explain    노드 하나를 종합 설명 - 다섯 번 부르던 것을 한 번으로
    analyze    네트워크 전체를 훑는다 - 요약, 쿡 순서, 비싼 노드, 스냅샷 비교
    geometry   지오메트리 통계·어트리뷰트 - SOP 뿐 아니라 DOP 등에서도 필요하다
    cache      디스크 캐시 - 쓰고, 최신인지 보고, 지운다
    viewport   뷰포트 캡처와 프레이밍 - 만든 결과를 눈으로 확인한다
    video      프레임을 영상으로 굽고 A/B 비교 영상을 만든다 - FFMPEG_BIN_PATH 의 외부 ffmpeg
    visualize  어트리뷰트 비주얼라이저 - 값이 어떻게 퍼져 있는지 색으로 본다
    nodetypes  노드 타입 카탈로그 - 무엇을 만들 수 있는지 먼저 본다
    scene      씬 파일 저장·열기, 프레임 범위
    deps       씬의 파일 참조 - 목록·수집·경로 치환. hou.fileReferences() 로 얻는다
    portability  씬을 다른 기계로 옮길 수 있는지 판정 - 없는 파일, 박힌 경로
    takes      테이크 - 파라미터 변형을 갈라 두고 오간다
    diagnose   에러·경고 조회와 쿡 - 무엇이 잘못됐는지 알아낸다
    anim       파라미터 식과 키프레임
    execute    툴로 안 되는 일을 하는 탈출구. 마지막 수단이다

툴이 없는 모듈은 TOOL_MODULES 에 넣지 않는다.

    parmtemplate  hou.ParmTemplate 을 만드는 공통 헬퍼. parmedit 과
                  houdini_mcp_hda 가 함께 쓴다
    paths         경로 전개·원문 보존·시퀀스·$HFS. 경로를 다루는 팩은 전부
                  이것을 쓰고 자기 헬퍼를 두지 않는다
    ffmpeg        외부 ffmpeg 찾기·실행·인코더 선택·drawtext·ffprobe 검증

특정 컨텍스트에만 의미가 있는 툴은 전용 팩(houdini_mcp_sop 등)으로 분리한다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`houdini_version`](#houdini_version) | `info` | 실행 중인 Houdini 버전 문자열. |  |
| [`scene_info`](#scene_info) | `info` | 현재 씬의 경로, 저장 여부, FPS, 프레임 범위. |  |
| [`list_children`](#list_children) | `info` | 주어진 네트워크 아래 자식 노드들을 나열한다. |  |
| [`node_info`](#node_info) | `info` | 노드 하나의 타입, 부모, 자식 수, 플래그, 연결 상태. |  |
| [`node_flags`](#node_flags) | `info` | 노드의 display/render/bypass/lock 플래그. |  |
| [`find_nodes`](#find_nodes) | `info` | 패턴으로 노드를 찾는다. |  |
| [`network_graph`](#network_graph) | `info` | 네트워크의 노드와 연결을 한 번에 훑는다. |  |
| [`get_parms`](#get_parms) | `info` | 노드 파라미터 값과 그 노드의 코멘트를 읽는다. |  |
| [`create_node`](#create_node) | `edit` | 네트워크 안에 노드를 만든다. 만들면서 파라미터도 함께 걸 수 있다. | ✓ |
| [`set_comment`](#set_comment) | `edit` | 노드 코멘트를 바꾼다. | ✓ |
| [`delete_node`](#delete_node) | `edit` | 노드를 지운다. | ✓ |
| [`rename_node`](#rename_node) | `edit` | 노드 이름을 바꾼다. | ✓ |
| [`set_parms`](#set_parms) | `edit` | 노드 파라미터를 건다. | ✓ |
| [`connect_nodes`](#connect_nodes) | `edit` | source 의 출력을 target 의 입력에 잇는다. | ✓ |
| [`disconnect_input`](#disconnect_input) | `edit` | 노드의 입력 하나를 끊는다. | ✓ |
| [`set_flags`](#set_flags) | `edit` | 노드 플래그를 건다. 준 것만 바뀐다. | ✓ |
| [`layout_children`](#layout_children) | `edit` | 네트워크 안 노드들을 보기 좋게 정렬한다. | ✓ |
| [`copy_node`](#copy_node) | `edit` | 노드를 복제한다. 파라미터와 내부 네트워크까지 함께 복사된다. | ✓ |
| [`reorder_inputs`](#reorder_inputs) | `edit` | 노드의 입력 순서를 바꾼다. | ✓ |
| [`set_node_appearance`](#set_node_appearance) | `edit` | 네트워크 뷰에서의 노드 색·위치·모양을 정한다. | ✓ |
| [`get_selection`](#get_selection) | `edit` | 지금 사용자가 네트워크 뷰에서 고른 노드들. |  |
| [`select_by_pattern`](#select_by_pattern) | `edit` | 패턴이나 타입으로 골라서 한꺼번에 선택한다. | ✓ |
| [`set_selection`](#set_selection) | `edit` | 네트워크 뷰의 선택을 바꾼다. | ✓ |
| [`list_parms`](#list_parms) | `parms` | 노드의 파라미터를 이름·라벨·타입·현재 값과 함께 나열한다. 노드 코멘트도 준다. |  |
| [`parm_info`](#parm_info) | `parms` | 파라미터 하나를 자세히 본다. 기본값, 범위, 메뉴 항목, 도움말. |  |
| [`add_spare_parm`](#add_spare_parm) | `parmedit` | 노드에 스페어 파라미터를 붙인다. | ✓ |
| [`remove_spare_parm`](#remove_spare_parm) | `parmedit` | 스페어 파라미터를 뗀다. | ✓ |
| [`link_parms`](#link_parms) | `parmedit` | target 파라미터가 source 파라미터를 따라가도록 식을 건다. | ✓ |
| [`lock_parm`](#lock_parm) | `parmedit` | 파라미터를 잠그거나 푼다. | ✓ |
| [`revert_parm`](#revert_parm) | `parmedit` | 파라미터를 기본값으로 되돌린다. 되돌리기 전 값을 함께 돌려준다. | ✓ |
| [`spare_parms`](#spare_parms) | `parmedit` | 노드에 붙어 있는 스페어 파라미터를 나열한다. |  |
| [`get_transform`](#get_transform) | `transform` | 노드의 변환을 네 가지 공간으로 모두 본다. |  |
| [`set_transform`](#set_transform) | `transform` | 노드의 변환을 정한다. 준 것만 바뀐다. | ✓ |
| [`set_pivot`](#set_pivot) | `transform` | 회전·스케일의 중심점을 정한다. | ✓ |
| [`parent_node`](#parent_node) | `transform` | OBJ 노드를 다른 OBJ 노드에 붙인다. 부모가 움직이면 자식이 따라간다. | ✓ |
| [`unparent_node`](#unparent_node) | `transform` | OBJ 계층에서 부모를 뗀다. | ✓ |
| [`set_node_lock`](#set_node_lock) | `transform` | 노드의 쿡 결과를 굳힌다. 하드 락과 소프트 락은 다르다. | ✓ |
| [`node_references`](#node_references) | `context` | 이 노드가 무엇에 의존하는지 한 번에 본다. |  |
| [`scene_context`](#scene_context) | `context` | 네트워크를 노드와 의존 관계까지 한 번에 훑어 컨텍스트로 만든다. |  |
| [`find_referencing_nodes`](#find_referencing_nodes) | `context` | 누가 이 노드를 참조하는지 찾는다. |  |
| [`explain_node`](#explain_node) | `explain` | 노드 하나를 종합해서 설명한다. 노드를 이해할 때 이걸 먼저 부른다. |  |
| [`network_overview`](#network_overview) | `analyze` | 네트워크가 어떻게 생겼는지 한눈에 본다. 씬을 처음 볼 때 부른다. |  |
| [`cook_chain`](#cook_chain) | `analyze` | 이 노드가 나오기까지 무엇이 어떤 순서로 쿡되는지 보여 준다. |  |
| [`find_expensive_nodes`](#find_expensive_nodes) | `analyze` | 어느 노드가 시간을 잡아먹는지 **실측값으로** 찾는다. |  |
| [`scene_snapshot`](#scene_snapshot) | `analyze` | 지금 상태를 떠 둔다. 나중에 `diff_scene` 으로 무엇이 바뀌었는지 본다. |  |
| [`diff_scene`](#diff_scene) | `analyze` | 스냅샷과 지금(또는 다른 스냅샷)을 비교한다. 무엇이 바뀌었는지 본다. |  |
| [`geometry_stats`](#geometry_stats) | `geometry` | SOP 의 포인트·프리미티브·버텍스 수와 바운딩 박스. |  |
| [`list_attributes`](#list_attributes) | `geometry` | 지오메트리의 어트리뷰트를 종류별로 나열한다. |  |
| [`list_groups`](#list_groups) | `geometry` | 지오메트리의 그룹을 종류별로 나열한다. |  |
| [`sample_points`](#sample_points) | `geometry` | 포인트 좌표를 몇 개 뽑아 본다. |  |
| [`attribute_values`](#attribute_values) | `geometry` | 어트리뷰트 값을 몇 개 읽어 본다. |  |
| [`write_cache`](#write_cache) | `cache` | 지오메트리를 디스크에 캐시로 굽는다. 굽고 나서 파일이 생겼는지 확인해 준다. | ✓ |
| [`list_caches`](#list_caches) | `cache` | 씬에 있는 캐시 노드를 전부 찾는다. |  |
| [`cache_status`](#cache_status) | `cache` | 캐시가 있는지, 낡았는지 본다. |  |
| [`clear_cache`](#clear_cache) | `cache` | 캐시를 비운다. 메모리와 디스크는 따로 다룬다. |  |
| [`viewport_snapshot`](#viewport_snapshot) | `viewport` | 현재 뷰포트를 캡처해서 그림으로 돌려준다. |  |
| [`viewport_sequence`](#viewport_sequence) | `viewport` | 여러 프레임을 한 장에 모아 캡처한다. 시간에 따라 무엇이 일어나는지 볼 때. |  |
| [`frame_all`](#frame_all) | `viewport` | 뷰포트를 씬 전체가 보이도록 맞춘다. |  |
| [`frame_node`](#frame_node) | `viewport` | 뷰포트를 특정 노드의 지오메트리에 맞춘다. |  |
| [`viewport_info`](#viewport_info) | `viewport` | 현재 뷰포트의 이름, 크기, 카메라 상태. |  |
| [`set_viewport_camera`](#set_viewport_camera) | `viewport` | 뷰포트를 카메라로 본다. 렌더가 실제로 무엇을 담는지 확인할 때 쓴다. |  |
| [`set_viewport_direction`](#set_viewport_direction) | `viewport` | 뷰포트를 정해진 방향에서 보게 한다. |  |
| [`set_viewport_display`](#set_viewport_display) | `viewport` | 뷰포트가 지오메트리를 어떻게 그릴지 정한다. |  |
| [`set_viewport_renderer`](#set_viewport_renderer) | `viewport` | 뷰포트 렌더러를 바꾼다. 이름을 생략하면 고를 수 있는 것을 알려 준다. |  |
| [`list_panes`](#list_panes) | `viewport` | 지금 열려 있는 패널 탭들. 사용자가 무엇을 보고 있는지 알 수 있다. |  |
| [`set_current_network`](#set_current_network) | `viewport` | 네트워크 에디터가 보는 네트워크를 바꾼다. |  |
| [`make_video`](#make_video) | `video` | 뷰포트 캡처나 이미지 시퀀스를 영상 하나로 굽고, 다시 읽어 확인한다. |  |
| [`compare_videos`](#compare_videos) | `video` | 두 소스를 나란히(또는 위아래로) 붙인 A/B 비교 영상을 굽고, 다시 읽어 확인한다. |  |
| [`visualize_attribute`](#visualize_attribute) | `visualize` | 어트리뷰트를 뷰포트에 색으로 표시한다. | ✓ |
| [`list_visualizers`](#list_visualizers) | `visualize` | 붙어 있는 비주얼라이저를 나열한다. |  |
| [`set_visualizer_active`](#set_visualizer_active) | `visualize` | 비주얼라이저를 켜거나 끈다. | ✓ |
| [`remove_visualizer`](#remove_visualizer) | `visualize` | 비주얼라이저를 지운다. | ✓ |
| [`list_node_types`](#list_node_types) | `nodetypes` | 카테고리에서 쓸 수 있는 노드 타입을 찾는다. |  |
| [`node_type_info`](#node_type_info) | `nodetypes` | 노드를 만들기 전에 그 타입의 파라미터와 입출력을 본다. |  |
| [`node_type_help`](#node_type_help) | `nodetypes` | 노드 타입에 딸린 내장 도움말 텍스트. |  |
| [`scene_path`](#scene_path) | `scene` | 현재 씬 파일 경로와 저장 상태. |  |
| [`save_scene`](#save_scene) | `scene` | 씬을 저장한다. |  |
| [`load_scene`](#load_scene) | `scene` | 씬 파일을 연다. |  |
| [`new_scene`](#new_scene) | `scene` | 씬을 비우고 새로 시작한다. |  |
| [`set_frame_range`](#set_frame_range) | `scene` | 플레이바의 프레임 범위를 정한다. |  |
| [`list_dependencies`](#list_dependencies) | `deps` | 씬이 참조하는 외부 파일을 전부 나열하고, 실제로 있는지 확인한다. |  |
| [`collect_dependencies`](#collect_dependencies) | `deps` | 씬이 쓰는 파일을 한 디렉토리로 모은다. 원하면 씬이 그쪽을 보게 고친다. | ✓ |
| [`remap_paths`](#remap_paths) | `deps` | 파일 참조 경로의 일부를 바꾼다. 씬을 다른 기계로 옮길 때 쓴다. | ✓ |
| [`validate_scene`](#validate_scene) | `portability` | 씬을 다른 기계로 옮길 수 있는지 판정한다. 없는 파일과 박힌 경로를 잡는다. |  |
| [`list_takes`](#list_takes) | `takes` | 씬의 테이크를 전부 나열하고 지금 어느 것이 켜져 있는지 알려 준다. |  |
| [`create_take`](#create_take) | `takes` | 테이크를 만든다. | ✓ |
| [`set_current_take`](#set_current_take) | `takes` | 켜져 있는 테이크를 바꾼다. | ✓ |
| [`delete_take`](#delete_take) | `takes` | 테이크를 지운다. 그 테이크에만 있던 파라미터 값은 사라진다. | ✓ |
| [`take_include`](#take_include) | `takes` | 어떤 파라미터를 이 테이크에서 따로 움직이게 할지 정한다. | ✓ |
| [`take_includes`](#take_includes) | `takes` | 이 테이크가 어떤 파라미터를 담고 있는지 본다. |  |
| [`node_errors`](#node_errors) | `diagnose` | 노드 하나의 에러와 경고를 읽는다. |  |
| [`find_error_nodes`](#find_error_nodes) | `diagnose` | 범위 안에서 에러나 경고가 붙은 노드를 찾는다. |  |
| [`cook_node`](#cook_node) | `diagnose` | 노드를 쿡해서 실제로 계산되는지 확인한다. |  |
| [`cook_status`](#cook_status) | `diagnose` | 노드가 쿡됐는지, 얼마나 걸렸는지, 시간에 의존하는지. |  |
| [`delete_unused`](#delete_unused) | `diagnose` | 출력으로 이어지지 않는 노드를 지운다. | ✓ |
| [`get_expression`](#get_expression) | `anim` | 파라미터에 걸린 식을 읽는다. |  |
| [`set_expression`](#set_expression) | `anim` | 파라미터에 식을 건다. | ✓ |
| [`clear_expression`](#clear_expression) | `anim` | 파라미터의 식을 떼고 보통 값으로 되돌린다. | ✓ |
| [`set_keyframe`](#set_keyframe) | `anim` | 파라미터에 키프레임을 찍는다. | ✓ |
| [`get_keyframes`](#get_keyframes) | `anim` | 파라미터의 키프레임 목록. |  |
| [`delete_keyframes`](#delete_keyframes) | `anim` | 키프레임을 지운다. 범위를 주면 그 구간만. | ✓ |
| [`list_animated_parms`](#list_animated_parms) | `anim` | 노드에서 키프레임이나 식이 걸린 파라미터를 찾는다. |  |
| [`run_python`](#run_python) | `execute` | Houdini 안에서 Python 을 실행한다. 전용 툴로 안 될 때만 쓴다. | ✓ |
| [`run_hscript`](#run_hscript) | `execute` | HScript 명령을 실행한다. |  |

## 모듈별 상세

### `info`

씬과 노드 그래프의 정보를 읽는 툴들.

#### houdini_version

```python
houdini_version()
```

실행 중인 Houdini 버전 문자열.

#### scene_info

```python
scene_info()
```

현재 씬의 경로, 저장 여부, FPS, 프레임 범위.

#### list_children

```python
list_children(path: str = '/obj')
```

주어진 네트워크 아래 자식 노드들을 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | `'/obj'` | 부모 노드 경로. 기본값은 /obj. |

#### node_info

```python
node_info(path: str, include_parameters: bool = False)
```

노드 하나의 타입, 부모, 자식 수, 플래그, 연결 상태.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. 예: /obj/geo1 |
| `include_parameters` | `bool` | `False` | True 면 파라미터 이름 목록도 함께 준다. 노드에 따라 수백 개가 되므로 기본값은 False 다. |

#### node_flags

```python
node_flags(path: str)
```

노드의 display/render/bypass/lock 플래그.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |

#### find_nodes

```python
find_nodes(pattern: str, root: str = '/obj')
```

패턴으로 노드를 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `pattern` | `str` | 필수 | 예) "*geo*", "**/*box*" |
| `root` | `str` | `'/obj'` | 검색을 시작할 네트워크 경로. |

#### network_graph

```python
network_graph(path: str = '/obj', depth: int = 1)
```

네트워크의 노드와 연결을 한 번에 훑는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | `'/obj'` | 네트워크 경로. |
| `depth` | `int` | `1` | 하위 네트워크를 몇 단계까지 따라 들어갈지. 1 이면 바로 아래만. |

#### get_parms

```python
get_parms(path: str, names: list[str] | None = None)
```

노드 파라미터 값과 그 노드의 코멘트를 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `names` | `list[str] \| None` | `None` | 읽을 파라미터 이름들. 생략하면 기본값과 다른 것만 돌려준다 (노드마다 파라미터가 수백 개라 전부 주면 쓸모가 없다). |

### `edit`

네트워크 종류와 무관하게 쓰는 노드 생성·조작·연결 툴.

#### create_node

```python
create_node(parent: str, node_type: str, comment: str, name: str | None = None, parms: dict[str, ParmValue] | None = None)
```

네트워크 안에 노드를 만든다. 만들면서 파라미터도 함께 걸 수 있다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 부모 네트워크 경로. 예: /obj, /obj/geo1 |
| `node_type` | `str` | 필수 | 노드 타입 이름. 예: geo, box, merge, copytopoints |
| `comment` | `str` | 필수 | 이 노드가 무엇을 위한 것인지. 필수. 씬 파일에 저장되고 다른 도구에서도 읽히므로 영어로 쓴다. 예: "Wall body, 20 x 4 x 1.2" |
| `name` | `str \| None` | `None` | 노드 이름. 역할이 드러나게 짓는다. 생략하면 Houdini 가 정한다. |
| `parms` | `dict[str, ParmValue] \| None` | `None` | 만들자마자 걸 파라미터. 예: {"sizex": 2.0, "ty": 1.5} |

#### set_comment

```python
set_comment(path: str, comment: str)
```

노드 코멘트를 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `comment` | `str` | 필수 | 새 코멘트. 씬에 저장되므로 영어로 쓴다. |

#### delete_node

```python
delete_node(path: str)
```

노드를 지운다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 지울 노드 경로. |

#### rename_node

```python
rename_node(path: str, name: str)
```

노드 이름을 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 새 이름. 역할이 드러나게, 영어로. |

#### set_parms

```python
set_parms(path: str, parms: dict[str, ParmValue])
```

노드 파라미터를 건다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `parms` | `dict[str, ParmValue]` | 필수 | 이름과 값. 예: {"sizex": 2.0, "ty": 1.5, "group": "0-3"} |

#### connect_nodes

```python
connect_nodes(source: str, target: str, input_index: int = 0, output_index: int = 0)
```

source 의 출력을 target 의 입력에 잇는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `source` | `str` | 필수 | 출력 쪽 노드 경로. |
| `target` | `str` | 필수 | 입력 쪽 노드 경로. |
| `input_index` | `int` | `0` | target 의 몇 번째 입력에 꽂을지. |
| `output_index` | `int` | `0` | source 의 몇 번째 출력에서 뽑을지. |

#### disconnect_input

```python
disconnect_input(path: str, input_index: int = 0)
```

노드의 입력 하나를 끊는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `input_index` | `int` | `0` | 끊을 입력 번호. |

#### set_flags

```python
set_flags(path: str, display: bool | None = None, render: bool | None = None, bypass: bool | None = None)
```

노드 플래그를 건다. 준 것만 바뀐다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `display` | `bool \| None` | `None` | 뷰포트 표시 플래그. |
| `render` | `bool \| None` | `None` | 렌더 플래그. |
| `bypass` | `bool \| None` | `None` | 바이패스 플래그. |

#### layout_children

```python
layout_children(path: str)
```

네트워크 안 노드들을 보기 좋게 정렬한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 네트워크 경로. |

#### copy_node

```python
copy_node(path: str, parent: str | None = None, name: str | None = None)
```

노드를 복제한다. 파라미터와 내부 네트워크까지 함께 복사된다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 복사할 노드 경로. |
| `parent` | `str \| None` | `None` | 붙여 넣을 네트워크. 생략하면 원본과 같은 부모. |
| `name` | `str \| None` | `None` | 새 이름. 생략하면 Houdini 가 정한다. |

#### reorder_inputs

```python
reorder_inputs(path: str, order: list[int])
```

노드의 입력 순서를 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `order` | `list[int]` | 필수 | 새 순서. 현재 입력 번호를 원하는 순서대로. |

#### set_node_appearance

```python
set_node_appearance(path: str, color: list[float] | None = None, position: list[float] | None = None, shape: str | None = None)
```

네트워크 뷰에서의 노드 색·위치·모양을 정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `color` | `list[float] \| None` | `None` | RGB 0~1 세 값. 예: [0.9, 0.3, 0.3] |
| `position` | `list[float] \| None` | `None` | 네트워크 뷰 좌표 두 값. 예: [3.0, -2.0] |
| `shape` | `str \| None` | `None` | 노드 모양 이름. 예: circle, oval, box |

#### get_selection

```python
get_selection()
```

지금 사용자가 네트워크 뷰에서 고른 노드들.

#### select_by_pattern

```python
select_by_pattern(pattern: str = '*', root: str = '/obj', node_type: str | None = None, clear_existing: bool = True)
```

패턴이나 타입으로 골라서 한꺼번에 선택한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `pattern` | `str` | `'*'` | 노드 이름 패턴. `*` 는 한 단계, `**` 는 재귀. 예: "*wall*", "**/*merlon*" |
| `root` | `str` | `'/obj'` | 검색을 시작할 네트워크 경로. |
| `node_type` | `str \| None` | `None` | 타입으로 한 번 더 거른다. 예: box, copytopoints |
| `clear_existing` | `bool` | `True` | 기존 선택을 지우고 새로 고른다. |

#### set_selection

```python
set_selection(paths: list[str], clear_existing: bool = True)
```

네트워크 뷰의 선택을 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `paths` | `list[str]` | 필수 | 고를 노드 경로들. |
| `clear_existing` | `bool` | `True` | 기존 선택을 지우고 새로 고른다. |

### `parms`

파라미터를 들여다보는 툴들.

#### list_parms

```python
list_parms(path: str, pattern: str = '*', changed_only: bool = False)
```

노드의 파라미터를 이름·라벨·타입·현재 값과 함께 나열한다. 노드 코멘트도 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `pattern` | `str` | `'*'` | 이름 패턴. 예: "size*", "t?", "*color*" |
| `changed_only` | `bool` | `False` | True 면 기본값과 다른 것만. |

#### parm_info

```python
parm_info(path: str, name: str)
```

파라미터 하나를 자세히 본다. 기본값, 범위, 메뉴 항목, 도움말.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. 예: sizex, type |

### `parmedit`

파라미터를 고치는 툴들. 값이 아니라 파라미터 자체를 다룬다.

#### add_spare_parm

```python
add_spare_parm(path: str, kind: str, name: str, label: str, size: int = 1, default: Any = None, min_value: float | None = None, max_value: float | None = None, menu_items: list[str] | None = None, menu_labels: list[str] | None = None, string_type: str = 'regular', help_text: str | None = None, folder: list[str] | None = None)
```

노드에 스페어 파라미터를 붙인다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `kind` | `str` | 필수 | float / int / string / toggle / menu / button / ramp_float / ramp_color / separator. |
| `name` | `str` | 필수 | 내부 이름. 예: wall_height |
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

#### remove_spare_parm

```python
remove_spare_parm(path: str, name: str)
```

스페어 파라미터를 뗀다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 뗄 파라미터 이름. 벡터면 튜플 이름을 준다. |

#### link_parms

```python
link_parms(source: str, source_parm: str, target: str, target_parm: str, relative: bool = True)
```

target 파라미터가 source 파라미터를 따라가도록 식을 건다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `source` | `str` | 필수 | 값을 내주는 노드 경로. |
| `source_parm` | `str` | 필수 | 그 노드의 파라미터 이름. |
| `target` | `str` | 필수 | 값을 받는 노드 경로. |
| `target_parm` | `str` | 필수 | 그 노드의 파라미터 이름. |
| `relative` | `bool` | `True` | True 면 상대 경로로 건다. |

#### lock_parm

```python
lock_parm(path: str, names: list[str], locked: bool = True)
```

파라미터를 잠그거나 푼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `names` | `list[str]` | 필수 | 파라미터 이름들. 벡터는 성분 이름으로. 예: ["tx", "ty"] |
| `locked` | `bool` | `True` | True 면 잠그고 False 면 푼다. |

#### revert_parm

```python
revert_parm(path: str, names: list[str] | None = None)
```

파라미터를 기본값으로 되돌린다. 되돌리기 전 값을 함께 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `names` | `list[str] \| None` | `None` | 되돌릴 파라미터 이름들. 생략하면 기본값이 아닌 것 전부. |

#### spare_parms

```python
spare_parms(path: str)
```

노드에 붙어 있는 스페어 파라미터를 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |

### `transform`

노드의 변환과 계층을 다루는 툴들.

#### get_transform

```python
get_transform(path: str)
```

노드의 변환을 네 가지 공간으로 모두 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | OBJ 노드 경로. 예: /obj/castle |

#### set_transform

```python
set_transform(path: str, translate: list[float] | None = None, rotate: list[float] | None = None, scale: list[float] | None = None, space: str = 'parm')
```

노드의 변환을 정한다. 준 것만 바뀐다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | OBJ 노드 경로. |
| `translate` | `list[float] \| None` | `None` | 위치 세 값. 예: [0, 2, 0] |
| `rotate` | `list[float] \| None` | `None` | 회전 세 값(도). 예: [0, 45, 0] |
| `scale` | `list[float] \| None` | `None` | 스케일 세 값. 예: [1, 2, 1] |
| `space` | `str` | `'parm'` | parm 또는 world. |

#### set_pivot

```python
set_pivot(path: str, pivot: list[float] | None = None, pivot_rotate: list[float] | None = None)
```

회전·스케일의 중심점을 정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | OBJ 노드 경로. |
| `pivot` | `list[float] \| None` | `None` | 중심점 세 값. 예: [0, 0, -1] |
| `pivot_rotate` | `list[float] \| None` | `None` | 중심점의 기준 회전 세 값(도). |

#### parent_node

```python
parent_node(path: str, parent: str, keep_position: bool = True)
```

OBJ 노드를 다른 OBJ 노드에 붙인다. 부모가 움직이면 자식이 따라간다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 자식이 될 노드 경로. |
| `parent` | `str` | 필수 | 부모가 될 노드 경로. |
| `keep_position` | `bool` | `True` | 붙인 뒤에도 보이는 위치를 유지한다. |

#### unparent_node

```python
unparent_node(path: str, keep_position: bool = True)
```

OBJ 계층에서 부모를 뗀다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 떼어 낼 노드 경로. |
| `keep_position` | `bool` | `True` | 뗀 뒤에도 보이는 위치를 유지한다. |

#### set_node_lock

```python
set_node_lock(path: str, hard: bool | None = None, soft: bool | None = None)
```

노드의 쿡 결과를 굳힌다. 하드 락과 소프트 락은 다르다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. 락을 지원하는 것은 대개 SOP 이다. |
| `hard` | `bool \| None` | `None` | 하드 락을 걸거나 푼다. |
| `soft` | `bool \| None` | `None` | 소프트 락을 걸거나 푼다. |

### `context`

노드 트리와 의존 관계를 한 번에 읽어 컨텍스트로 만드는 툴들.

#### node_references

```python
node_references(path: str)
```

이 노드가 무엇에 의존하는지 한 번에 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |

#### scene_context

```python
scene_context(path: str = '/obj', depth: int = 2)
```

네트워크를 노드와 의존 관계까지 한 번에 훑어 컨텍스트로 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | `'/obj'` | 시작 네트워크 경로. |
| `depth` | `int` | `2` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |

#### find_referencing_nodes

```python
find_referencing_nodes(path: str, root: str = '/obj', depth: int = 3)
```

누가 이 노드를 참조하는지 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 참조당하는 노드 경로. |
| `root` | `str` | `'/obj'` | 훑을 범위. |
| `depth` | `int` | `3` | 몇 단계까지 들어갈지. |

### `explain`

노드 하나를 한 번에 설명하는 툴.

#### explain_node

```python
explain_node(path: str, max_help_chars: int = MAX_HELP)
```

노드 하나를 종합해서 설명한다. 노드를 이해할 때 이걸 먼저 부른다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. 예: /obj/castle/wall_body |
| `max_help_chars` | `int` | `MAX_HELP` | 타입 도움말을 몇 자까지 실을지. |

### `analyze`

네트워크 전체를 훑어 무슨 일이 벌어지고 있는지 알아내는 툴들.

#### network_overview

```python
network_overview(path: str = '/obj', depth: int = 1)
```

네트워크가 어떻게 생겼는지 한눈에 본다. 씬을 처음 볼 때 부른다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | `'/obj'` | 네트워크 경로. 예: /obj, /obj/castle |
| `depth` | `int` | `1` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |

#### cook_chain

```python
cook_chain(path: str)
```

이 노드가 나오기까지 무엇이 어떤 순서로 쿡되는지 보여 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 결과가 될 노드 경로. 예: /obj/castle/OUT |

#### find_expensive_nodes

```python
find_expensive_nodes(root: str = '/obj', depth: int = 3, top: int = 15)
```

어느 노드가 시간을 잡아먹는지 **실측값으로** 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `root` | `str` | `'/obj'` | 훑기 시작할 경로. |
| `depth` | `int` | `3` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |
| `top` | `int` | `15` | 느린 순으로 몇 개까지 보여줄지. |

#### scene_snapshot

```python
scene_snapshot(label: str, root: str = '/obj', depth: int = 3)
```

지금 상태를 떠 둔다. 나중에 `diff_scene` 으로 무엇이 바뀌었는지 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `label` | `str` | 필수 | 이 스냅샷을 부를 이름. 예: "before_bevel" |
| `root` | `str` | `'/obj'` | 뜰 범위. |
| `depth` | `int` | `3` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |

#### diff_scene

```python
diff_scene(label: str, other: str | None = None)
```

스냅샷과 지금(또는 다른 스냅샷)을 비교한다. 무엇이 바뀌었는지 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `label` | `str` | 필수 | 기준이 될 스냅샷 이름. |
| `other` | `str \| None` | `None` | 비교 대상 스냅샷 이름. 생략하면 지금 씬과 비교한다. |

### `geometry`

지오메트리를 들여다보는 툴들.

#### geometry_stats

```python
geometry_stats(path: str, output: int = 0)
```

SOP 의 포인트·프리미티브·버텍스 수와 바운딩 박스.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. 예: /obj/castle/castle_wall |
| `output` | `int` | `0` | 읽을 출력 포트 번호. 기본 0. 출력이 여럿인 노드(RBD 솔버의 제약은 1)에서 쓴다. |

#### list_attributes

```python
list_attributes(path: str, output: int = 0)
```

지오메트리의 어트리뷰트를 종류별로 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `output` | `int` | `0` | 읽을 출력 포트 번호. 기본 0. 출력이 여럿인 노드(RBD 솔버의 제약은 1)에서 쓴다. |

#### list_groups

```python
list_groups(path: str, output: int = 0)
```

지오메트리의 그룹을 종류별로 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `output` | `int` | `0` | 읽을 출력 포트 번호. 기본 0. 출력이 여럿인 노드(RBD 솔버의 제약은 1)에서 쓴다. |

#### sample_points

```python
sample_points(path: str, count: int = 10, start: int = 0, output: int = 0)
```

포인트 좌표를 몇 개 뽑아 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `count` | `int` | `10` | 뽑을 개수. 최대 200. |
| `start` | `int` | `0` | 몇 번째 포인트부터 뽑을지. |
| `output` | `int` | `0` | 읽을 출력 포트 번호. 기본 0. 출력이 여럿인 노드(RBD 솔버의 제약은 1)에서 쓴다. |

#### attribute_values

```python
attribute_values(path: str, name: str, owner: str = 'point', count: int = 10, start: int = 0, output: int = 0)
```

어트리뷰트 값을 몇 개 읽어 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | SOP 노드 경로. |
| `name` | `str` | 필수 | 어트리뷰트 이름. 예: P, Cd, name |
| `owner` | `str` | `'point'` | point / prim / vertex / detail 중 하나. UV 는 보통 vertex 다. |
| `count` | `int` | `10` | 읽을 개수. 최대 200. detail 은 하나뿐이라 무시된다. |
| `start` | `int` | `0` | 몇 번째부터 읽을지. |
| `output` | `int` | `0` | 읽을 출력 포트 번호. 기본 0. 출력이 여럿인 노드(RBD 솔버의 제약은 1)에서 쓴다. |

### `cache`

디스크 캐시를 쓰고 상태를 보고 지우는 툴들.

#### write_cache

```python
write_cache(source: str, comment: str, file_path: str | None = None, frame_start: float | None = None, frame_end: float | None = None, name: str | None = None)
```

지오메트리를 디스크에 캐시로 굽는다. 굽고 나서 파일이 생겼는지 확인해 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `source` | `str` | 필수 | 구울 SOP 경로, 또는 이미 있는 캐시 노드 경로. |
| `comment` | `str` | 필수 | 이 캐시가 무엇인지. 필수. 씬에 저장되므로 영어로. 예: "Baked wall geometry, 1.2M points" |
| `file_path` | `str \| None` | `None` | 쓸 파일 경로. 생략하면 Houdini 가 $HIP/geo 아래에 정한다. |
| `frame_start` | `float \| None` | `None` | 시작 프레임. 생략하면 현재 프레임 하나만. |
| `frame_end` | `float \| None` | `None` | 끝 프레임. |
| `name` | `str \| None` | `None` | 새로 만들 때 쓸 노드 이름. 역할이 드러나게, 영어로. |

#### list_caches

```python
list_caches(root: str = '/obj', depth: int = 4)
```

씬에 있는 캐시 노드를 전부 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `root` | `str` | `'/obj'` | 훑기 시작할 경로. |
| `depth` | `int` | `4` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |

#### cache_status

```python
cache_status(path: str)
```

캐시가 있는지, 낡았는지 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 캐시 노드 경로. |

#### clear_cache

```python
clear_cache(path: str | None = None, memory: bool = True, delete_files: bool = False)
```

캐시를 비운다. 메모리와 디스크는 따로 다룬다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str \| None` | `None` | 디스크 파일을 지울 캐시 노드 경로. delete_files 와 함께 쓴다. |
| `memory` | `bool` | `True` | Houdini 의 메모리 캐시를 비운다. |
| `delete_files` | `bool` | `False` | path 가 가리키는 캐시의 디스크 파일을 **영구히 지운다**. |

### `viewport`

뷰포트를 보고 다루는 툴들.

#### viewport_snapshot

```python
viewport_snapshot(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, frame: float | None = None, crop_to_camera: bool = False)
```

현재 뷰포트를 캡처해서 그림으로 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `width` | `int` | `DEFAULT_WIDTH` | 가로 픽셀. |
| `height` | `int` | `DEFAULT_HEIGHT` | 세로 픽셀. |
| `frame` | `float \| None` | `None` | 캡처할 프레임. 생략하면 현재 프레임. |
| `crop_to_camera` | `bool` | `False` | 카메라 마스크 바깥을 잘라낸다. 카메라를 보고 있을 때만 의미가 있다. |

#### viewport_sequence

```python
viewport_sequence(frames: list[float], columns: int = 4, tile_width: int = 480, tile_height: int = 270)
```

여러 프레임을 한 장에 모아 캡처한다. 시간에 따라 무엇이 일어나는지 볼 때.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `frames` | `list[float]` | 필수 | 캡처할 프레임들. 최대 16개. 예: [1, 12, 20, 24, 36, 48] |
| `columns` | `int` | `4` | 한 줄에 놓을 칸 수. |
| `tile_width` | `int` | `480` | 칸 하나의 가로 픽셀. |
| `tile_height` | `int` | `270` | 칸 하나의 세로 픽셀. |

#### frame_all

```python
frame_all()
```

뷰포트를 씬 전체가 보이도록 맞춘다.

#### frame_node

```python
frame_node(path: str)
```

뷰포트를 특정 노드의 지오메트리에 맞춘다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. 예: /obj/castle/castle_wall |

#### viewport_info

```python
viewport_info()
```

현재 뷰포트의 이름, 크기, 카메라 상태.

#### set_viewport_camera

```python
set_viewport_camera(path: str | None = None, lock: bool = False)
```

뷰포트를 카메라로 본다. 렌더가 실제로 무엇을 담는지 확인할 때 쓴다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str \| None` | `None` | 카메라 노드 경로. 예: /obj/shot_cam |
| `lock` | `bool` | `False` | True 면 뷰를 카메라에 잠가 실수로 시점이 움직이지 않게 한다. |

#### set_viewport_direction

```python
set_viewport_direction(direction: str = 'persp')
```

뷰포트를 정해진 방향에서 보게 한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `direction` | `str` | `'persp'` | top / bottom / front / back / left / right / persp / uv |

#### set_viewport_display

```python
set_viewport_display(shading: str = 'smooth_wire', ghost_others: bool = False)
```

뷰포트가 지오메트리를 어떻게 그릴지 정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `shading` | `str` | `'smooth_wire'` | wire / wire_ghost / hidden_line / hidden_line_ghost / flat / flat_wire / smooth / smooth_wire / bbox |
| `ghost_others` | `bool` | `False` | 작업 중이 아닌 오브젝트를 반투명으로. |

#### set_viewport_renderer

```python
set_viewport_renderer(name: str | None = None)
```

뷰포트 렌더러를 바꾼다. 이름을 생략하면 고를 수 있는 것을 알려 준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str \| None` | `None` | 렌더러 이름. 생략하면 지금 것과 고를 수 있는 것만 돌려준다. |

#### list_panes

```python
list_panes()
```

지금 열려 있는 패널 탭들. 사용자가 무엇을 보고 있는지 알 수 있다.

#### set_current_network

```python
set_current_network(path: str)
```

네트워크 에디터가 보는 네트워크를 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 열 네트워크 경로. 예: /obj/castle |

### `video`

영상 툴 - 프레임을 영상 하나로 굽고, 두 소스를 나란히 붙여 비교한다.

#### make_video

```python
make_video(output: str, source: str | None = None, start: float | None = None, end: float | None = None, fps: float = 24.0, width: int = 1280, height: int = 720, label: str | None = None, font_file: str | None = None, exposure: float = 0.0, crf: int = 18, overwrite: bool = False)
```

뷰포트 캡처나 이미지 시퀀스를 영상 하나로 굽고, 다시 읽어 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `output` | `str` | 필수 | 쓸 영상 경로. .mp4 / .mov / .mkv / .webm. $HIP 같은 변수를 써도 된다. |
| `source` | `str \| None` | `None` | 생략하면 뷰포트 캡처. 이미지 시퀀스는 `$HIP/render/beauty.$F4.exr` 나 `.../frame.%04d.png` 처럼 프레임 토큰이 든 경로. 영상 파일(.mp4 등)을 주면 라벨만 입혀 다시 굽는다. |
| `start` | `float \| None` | `None` | 시작 프레임. 뷰포트 캡처에서 생략하면 플레이바 시작. 시퀀스에서 start/end 를 둘 다 생략하면 있는 파일을 전부 쓴다. |
| `end` | `float \| None` | `None` | 끝 프레임(포함). |
| `fps` | `float` | `24.0` | 초당 프레임. |
| `width` | `int` | `1280` | 뷰포트 캡처의 가로 픽셀. 시퀀스는 원본 크기를 쓴다. |
| `height` | `int` | `720` | 뷰포트 캡처의 세로 픽셀. |
| `label` | `str \| None` | `None` | 왼쪽 위에 넣을 글자. 예: "flag loop - after relax" |
| `font_file` | `str \| None` | `None` | 라벨 폰트(.ttf/.ttc/.otf). 생략하면 영문은 ffmpeg 기본 글꼴, 한글이 있으면 OS 의 한글 글꼴을 찾는다. |
| `exposure` | `float` | `0.0` | EXR·HDR 같은 선형 이미지에 더할 노출(스톱). 다른 이미지에는 쓰지 않는다. |
| `crf` | `int` | `18` | 화질. 낮을수록 좋고 파일이 커진다. 18 이면 눈으로 구분하기 어렵다. |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |

#### compare_videos

```python
compare_videos(a: str, b: str, output: str, label_a: str | None = 'A', label_b: str | None = 'B', layout: str = 'horizontal', start: float | None = None, end: float | None = None, fps: float = 24.0, size: int | None = None, font_file: str | None = None, exposure: float = 0.0, crf: int = 18, overwrite: bool = False)
```

두 소스를 나란히(또는 위아래로) 붙인 A/B 비교 영상을 굽고, 다시 읽어 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `a` | `str` | 필수 | 왼쪽(위) 소스. 영상 파일 또는 `$F4`·`%04d` 프레임 토큰이 든 이미지 시퀀스 경로. |
| `b` | `str` | 필수 | 오른쪽(아래) 소스. 형식은 a 와 같다. |
| `output` | `str` | 필수 | 쓸 영상 경로. .mp4 / .mov / .mkv / .webm. |
| `label_a` | `str \| None` | `'A'` | a 에 넣을 글자. 빈 문자열이나 None 이면 넣지 않는다. 예: "before" |
| `label_b` | `str \| None` | `'B'` | b 에 넣을 글자. 예: "after relax x80" |
| `layout` | `str` | `'horizontal'` | "horizontal"(나란히) 또는 "vertical"(위아래). |
| `start` | `float \| None` | `None` | 이미지 시퀀스 소스의 시작 프레임. 영상 파일 소스에는 쓰지 않는다. 생략하면 있는 파일 전부. |
| `end` | `float \| None` | `None` | 이미지 시퀀스 소스의 끝 프레임(포함). |
| `fps` | `float` | `24.0` | 초당 프레임. 이미지 시퀀스를 이 속도로 읽고, 결과도 이 속도로 쓴다. |
| `size` | `int \| None` | `None` | horizontal 이면 공통 높이, vertical 이면 공통 너비(픽셀). 생략하면 두 소스 중 작은 쪽. |
| `font_file` | `str \| None` | `None` | 라벨 폰트(.ttf/.ttc/.otf). 생략하면 영문은 ffmpeg 기본 글꼴, 한글이 있으면 OS 의 한글 글꼴을 찾는다. |
| `exposure` | `float` | `0.0` | EXR·HDR 같은 선형 이미지 소스에 더할 노출(스톱). |
| `crf` | `int` | `18` | 화질. 낮을수록 좋고 파일이 커진다. |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |

### `visualize`

어트리뷰트 비주얼라이저를 다루는 툴들.

#### visualize_attribute

```python
visualize_attribute(node: str, attribute: str, label: str, name: str | None = None, geometry_class: str = 'point', color_mode: str = 'attribramped', range_mode: str = 'auto', min_value: float | None = None, max_value: float | None = None)
```

어트리뷰트를 뷰포트에 색으로 표시한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `node` | `str` | 필수 | 비주얼라이저를 붙일 노드 경로. 보통 geo 오브젝트를 준다. |
| `attribute` | `str` | 필수 | 표시할 어트리뷰트 이름. 예: Cd, density, P |
| `label` | `str` | 필수 | 뷰포트 툴바에 뜨는 이름. 영어로 쓴다. |
| `name` | `str \| None` | `None` | 내부 이름. 생략하면 어트리뷰트 이름을 쓴다. |
| `geometry_class` | `str` | `'point'` | vertex / point / primitive / detail / auto |
| `color_mode` | `str` | `'attribramped'` | attribasis(벡터를 그대로 색으로) / attribramped(램프) / constant / random / attribrandom |
| `range_mode` | `str` | `'auto'` | auto / min-max / center-width |
| `min_value` | `float \| None` | `None` | range_mode 가 min-max 일 때 하한. |
| `max_value` | `float \| None` | `None` | range_mode 가 min-max 일 때 상한. |

#### list_visualizers

```python
list_visualizers(node: str | None = None)
```

붙어 있는 비주얼라이저를 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `node` | `str \| None` | `None` | 노드 경로. 주면 그 노드에 붙은 것만, 생략하면 씬 전역의 것. |

#### set_visualizer_active

```python
set_visualizer_active(node: str, name: str, active: bool = True)
```

비주얼라이저를 켜거나 끈다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `node` | `str` | 필수 | 비주얼라이저가 붙은 노드 경로. |
| `name` | `str` | 필수 | 비주얼라이저 이름. |
| `active` | `bool` | `True` | 켤지 끌지. |

#### remove_visualizer

```python
remove_visualizer(node: str, name: str)
```

비주얼라이저를 지운다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `node` | `str` | 필수 | 비주얼라이저가 붙은 노드 경로. |
| `name` | `str` | 필수 | 비주얼라이저 이름. |

### `nodetypes`

노드 타입을 만들기 전에 알아보는 툴들.

#### list_node_types

```python
list_node_types(category: str = 'Sop', pattern: str = '*', include_hidden: bool = False)
```

카테고리에서 쓸 수 있는 노드 타입을 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `category` | `str` | `'Sop'` | Sop / Object / Dop / Cop / Top / Chop / Driver / Lop / Vop 등. |
| `pattern` | `str` | `'*'` | 이름이나 라벨에 대한 와일드카드. 예: "copy*", "*scatter*" |
| `include_hidden` | `bool` | `False` | 숨김·폐기 노드까지 포함한다. |

#### node_type_info

```python
node_type_info(category: str, type_name: str, parm_pattern: str = '*', detailed: bool = False)
```

노드를 만들기 전에 그 타입의 파라미터와 입출력을 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `category` | `str` | 필수 | Sop / Object / Dop 등. |
| `type_name` | `str` | 필수 | 노드 타입 이름. 예: tube, copytopoints::2.0 |
| `parm_pattern` | `str` | `'*'` | 파라미터 이름 와일드카드. 공백으로 여러 개를 줄 수 있다. 예: "rad* height cols". 기본은 전부. |
| `detailed` | `bool` | `False` | True 면 메뉴 항목과 조건부 활성식(DisableWhen)까지 준다. |

#### node_type_help

```python
node_type_help(category: str, type_name: str, max_chars: int = 4000)
```

노드 타입에 딸린 내장 도움말 텍스트.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `category` | `str` | 필수 | Sop / Object / Dop 등. |
| `type_name` | `str` | 필수 | 노드 타입 이름. |
| `max_chars` | `int` | `4000` | 잘라낼 길이. |

### `scene`

씬 파일을 저장하고 여는 툴들.

#### scene_path

```python
scene_path()
```

현재 씬 파일 경로와 저장 상태.

#### save_scene

```python
save_scene(path: str | None = None, overwrite: bool = False)
```

씬을 저장한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str \| None` | `None` | 저장할 경로. 생략하면 현재 씬 경로. |
| `overwrite` | `bool` | `False` | 이미 있는 파일을 덮어쓸 때 True. |

#### load_scene

```python
load_scene(path: str, discard_changes: bool = False)
```

씬 파일을 연다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 열 .hip / .hipnc / .hiplc 경로. |
| `discard_changes` | `bool` | `False` | 저장하지 않은 변경을 버리고 연다. |

#### new_scene

```python
new_scene(discard_changes: bool = False)
```

씬을 비우고 새로 시작한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `discard_changes` | `bool` | `False` | 저장하지 않은 변경을 버린다. |

#### set_frame_range

```python
set_frame_range(start: float, end: float, current: float | None = None)
```

플레이바의 프레임 범위를 정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `start` | `float` | 필수 | 시작 프레임. |
| `end` | `float` | 필수 | 끝 프레임. |
| `current` | `float \| None` | `None` | 현재 프레임. 생략하면 그대로 둔다. |

### `deps`

씬이 무엇에 의존하는지 — 목록·수집·경로 치환.

#### list_dependencies

```python
list_dependencies(kinds: Sequence[str] | None = None, missing_only: bool = False, include_outputs: bool = False, limit: int = MAX_LISTED)
```

씬이 참조하는 외부 파일을 전부 나열하고, 실제로 있는지 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `kinds` | `Sequence[str] \| None` | `None` | hou.fileType 이름으로 거른다. Geometry / Image / Otl / Usd / Alembic / Fbx / Hip / Directory / Any 등. 생략하면 전부. 텍스처만 보려면 ["Image"]. |
| `missing_only` | `bool` | `False` | True 면 없는 파일만. |
| `include_outputs` | `bool` | `False` | True 면 출력 경로 파라미터도 함께 낸다. |
| `limit` | `int` | `MAX_LISTED` | 목록에 담을 최대 개수. 집계는 전체를 대상으로 한다. |

#### collect_dependencies

```python
collect_dependencies(target_dir: str, kinds: Sequence[str] | None = None, overwrite: bool = False, relink: bool = False, dry_run: bool = True)
```

씬이 쓰는 파일을 한 디렉토리로 모은다. 원하면 씬이 그쪽을 보게 고친다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target_dir` | `str` | 필수 | 모을 디렉토리. 없으면 만든다. |
| `kinds` | `Sequence[str] \| None` | `None` | hou.fileType 이름으로 거른다. 생략하면 이미지·지오메트리·HDA 등 입력 참조 전부. |
| `overwrite` | `bool` | `False` | 대상 디렉토리에 같은 이름이 이미 있을 때 덮어쓴다. |
| `relink` | `bool` | `False` | True 면 복사한 뒤 씬의 파라미터를 새 경로로 고친다. 시퀀스 토큰 ($F4, <UDIM>)은 그대로 보존한다. |
| `dry_run` | `bool` | `True` | True(기본)면 복사하지 않고 계획만 돌려준다. |

#### remap_paths

```python
remap_paths(find: str, replace: str, kinds: Sequence[str] | None = None, dry_run: bool = True)
```

파일 참조 경로의 일부를 바꾼다. 씬을 다른 기계로 옮길 때 쓴다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `find` | `str` | 필수 | 찾을 문자열. 경로의 일부면 된다. |
| `replace` | `str` | 필수 | 바꿔 넣을 문자열. $HIP 같은 Houdini 변수를 그대로 써도 된다. |
| `kinds` | `Sequence[str] \| None` | `None` | hou.fileType 이름으로 거른다. 생략하면 전부. |
| `dry_run` | `bool` | `True` | True(기본)면 바꾸지 않고 계획만 돌려준다. |

### `portability`

씬을 넘기기 전에 보는 것 — 이식성 점검.

#### validate_scene

```python
validate_scene(include_outputs: bool = False, limit: int = MAX_LISTED)
```

씬을 다른 기계로 옮길 수 있는지 판정한다. 없는 파일과 박힌 경로를 잡는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `include_outputs` | `bool` | `False` | True 면 출력 경로 파라미터도 판정 대상에 넣는다. |
| `limit` | `int` | `MAX_LISTED` | 문제 목록에 담을 최대 개수. |

### `takes`

테이크를 다루는 툴들.

#### list_takes

```python
list_takes()
```

씬의 테이크를 전부 나열하고 지금 어느 것이 켜져 있는지 알려 준다.

#### create_take

```python
create_take(name: str, parent: str | None = None, set_current: bool = True)
```

테이크를 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 새 테이크 이름. 영어로. 예: "night_lighting" |
| `parent` | `str \| None` | `None` | 부모 테이크 이름. 생략하면 지금 테이크. |
| `set_current` | `bool` | `True` | 만들고 나서 이 테이크로 전환한다. |

#### set_current_take

```python
set_current_take(name: str)
```

켜져 있는 테이크를 바꾼다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 전환할 테이크 이름. |

#### delete_take

```python
delete_take(name: str, recurse: bool = False)
```

테이크를 지운다. 그 테이크에만 있던 파라미터 값은 사라진다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 지울 테이크 이름. |
| `recurse` | `bool` | `False` | 자식 테이크까지 함께 지운다. |

#### take_include

```python
take_include(name: str, path: str, parms: list[str] | None = None, include: bool = True)
```

어떤 파라미터를 이 테이크에서 따로 움직이게 할지 정한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 테이크 이름. |
| `path` | `str` | 필수 | 노드 경로. |
| `parms` | `list[str] \| None` | `None` | 담을 파라미터 이름들. 생략하면 기본값이 아닌 것 전부. |
| `include` | `bool` | `True` | False 면 담긴 것을 도로 뺀다. |

#### take_includes

```python
take_includes(name: str)
```

이 테이크가 어떤 파라미터를 담고 있는지 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 테이크 이름. |

### `diagnose`

무엇이 잘못됐는지 알아내는 툴들.

#### node_errors

```python
node_errors(path: str)
```

노드 하나의 에러와 경고를 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |

#### find_error_nodes

```python
find_error_nodes(root: str = '/obj', depth: int = 3)
```

범위 안에서 에러나 경고가 붙은 노드를 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `root` | `str` | `'/obj'` | 훑기 시작할 경로. |
| `depth` | `int` | `3` | 하위 네트워크를 몇 단계까지 따라 들어갈지. |

#### cook_node

```python
cook_node(path: str, force: bool = False)
```

노드를 쿡해서 실제로 계산되는지 확인한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `force` | `bool` | `False` | 이미 쿡된 노드도 다시 쿡한다. |

#### cook_status

```python
cook_status(path: str)
```

노드가 쿡됐는지, 얼마나 걸렸는지, 시간에 의존하는지.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |

#### delete_unused

```python
delete_unused(parent: str, keep: list[str] | None = None)
```

출력으로 이어지지 않는 노드를 지운다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 정리할 네트워크 경로. |
| `keep` | `list[str] \| None` | `None` | 무조건 남길 노드 이름들. |

### `anim`

파라미터에 식과 키프레임을 거는 툴들.

#### get_expression

```python
get_expression(path: str, name: str)
```

파라미터에 걸린 식을 읽는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. |

#### set_expression

```python
set_expression(path: str, name: str, expression: str, language: str = 'hscript')
```

파라미터에 식을 건다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. |
| `expression` | `str` | 필수 | 식 문자열. |
| `language` | `str` | `'hscript'` | hscript 또는 python. |

#### clear_expression

```python
clear_expression(path: str, name: str, keep_value: bool = True)
```

파라미터의 식을 떼고 보통 값으로 되돌린다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. |
| `keep_value` | `bool` | `True` | 식이 마지막으로 낸 값을 그대로 남긴다. |

#### set_keyframe

```python
set_keyframe(path: str, name: str, frame: float, value: float | None = None, expression: str | None = None, interpolation: str = 'cubic')
```

파라미터에 키프레임을 찍는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. |
| `frame` | `float` | 필수 | 프레임 번호. |
| `value` | `float \| None` | `None` | 키의 값. |
| `expression` | `str \| None` | `None` | 값 대신 걸 식. |
| `interpolation` | `str` | `'cubic'` | constant / linear / cubic / bezier / ease 등. |

#### get_keyframes

```python
get_keyframes(path: str, name: str)
```

파라미터의 키프레임 목록.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. |

#### delete_keyframes

```python
delete_keyframes(path: str, name: str, start: float | None = None, end: float | None = None)
```

키프레임을 지운다. 범위를 주면 그 구간만.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |
| `name` | `str` | 필수 | 파라미터 이름. |
| `start` | `float \| None` | `None` | 지울 구간 시작 프레임. 생략하면 전부. |
| `end` | `float \| None` | `None` | 지울 구간 끝 프레임. |

#### list_animated_parms

```python
list_animated_parms(path: str)
```

노드에서 키프레임이나 식이 걸린 파라미터를 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 노드 경로. |

### `execute`

툴로 안 되는 일을 하는 탈출구.

#### run_python

```python
run_python(code: str, comment: str)
```

Houdini 안에서 Python 을 실행한다. 전용 툴로 안 될 때만 쓴다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `code` | `str` | 필수 | 실행할 Python 코드. |
| `comment` | `str` | 필수 | 무엇을 왜 하는지. 로그에 코드와 함께 남는다. 필수. |

#### run_hscript

```python
run_hscript(command: str)
```

HScript 명령을 실행한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `command` | `str` | 필수 | HScript 명령 한 줄 또는 여러 줄. |
