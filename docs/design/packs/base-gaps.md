# houdini_mcp_base 남은 결핍

> 먼저 [README.md](README.md) 를 읽는다. 이건 새 팩이 아니라 **base 확장**이다.

기존 구현 다섯의 툴 463개 중, **컨텍스트를 가리지 않아서 base 에 있어야 하는데
아직 없는 것**을 모았다. 팩 문서들과 달리 여기는 모듈 단위 작업이다.

현재 base 는 62개 툴, 12개 모듈이다:
`info` `edit` `parms` `context` `geometry` `viewport` `visualize`
`nodetypes` `scene` `diagnose` `anim` `execute`

## 원칙 — 중복을 만들지 않는다

**착수 전에 현재 62개 목록을 실제로 확인한다.** 이 문서는 2026-09-13 기준이다.

```bash
hython -c "from houdini_mcp import get_registry; print(get_registry().names())"
```

이름만 다르고 같은 일을 하는 툴을 추가하지 않는다. 기존 툴에 인자를 더해
해결되면 그쪽이 낫다 — 툴 수가 늘수록 모델이 고르기 어려워진다.

## 1. 노드 변환·계층 (`edit` 또는 새 `transform` 모듈)

| 툴 | 하는 일 |
|---|---|
| `get_transform` / `set_transform` | OBJ 레벨 t/r/s/pivot. 월드/로컬 둘 다 |
| `set_pivot` | |
| `parent_node` / `unparent_node` | OBJ 계층 |
| `set_node_lock` | 하드/소프트 락. 차이를 docstring 에 설명 |
| `move_node` | 네트워크 뷰 위치. `set_node_appearance` 와 중복 점검 |

`hou.ObjNode.worldTransform()` / `setWorldTransform()` / `parmTransform()` 의
차이를 정확히 이해하고 쓴다. `hou.Matrix4` 를 그대로 돌려주지 말고
t/r/s 로 분해해서(`hou.Matrix4.explode()`) 준다.

## 2. 파라미터 심화 (`parms`)

| 툴 | 하는 일 |
|---|---|
| `add_spare_parm` / `remove_spare_parm` | `hou.ParmTemplate` 으로. 문자열 조립 금지 |
| `link_parms` | 두 파라미터를 `ch()` 로 연결. 상대 경로로 건다 |
| `lock_parm` / `unlock_parm` | |
| `revert_parm` | 기본값으로. 되돌리기 전 값을 반환 |
| `parm_schema` | 노드를 만들지 않고 타입에서 스키마만. `nodetypes` 의 것과 중복 점검 |

`hou.ParmTemplate` 서브클래스별 생성자는 `houdini_mcp_hda` 와 겹친다.
**공통 헬퍼를 base 에 두고 hda 팩이 쓰게** 한다.

## 3. 그래프 인텔리전스 (`context` 또는 새 `analyze` 모듈)

기존 fx 구현의 아이디어 중 값어치 있는 것들이다. 다만 구현은 새로 한다.

| 툴 | 하는 일 |
|---|---|
| `explain_node` | 노드 하나를 종합 설명 — 타입 도움말 + 코멘트 + 기본값에서 벗어난 파라미터 + 입출력 + 에러 + 지오 통계. **모델이 노드 하나 이해하려고 5번 부르던 것을 1번으로** |
| `network_overview` | 네트워크 요약 — 노드 수, 타입 분포, 출력 체인, 고아 노드, 에러 |
| `cook_chain` | 어떤 노드가 어떤 순서로 쿡되는가. `inputAncestors()` 기반 |
| `find_expensive_nodes` | `cookTime()` / `cookCount()` 실측. **추측하지 않는다** |
| `diff_scene` | 스냅샷 두 개 비교. 내가 뭘 바꿨는지 확인용 |

`explain_node` 가 이 중 가장 값어치 있다. 먼저 만든다.

## 4. 캐시 (`cache` 모듈)

| 툴 | 하는 일 |
|---|---|
| `write_cache` | File Cache SOP. 쓰고 나서 파일 크기·프레임 수 확인 |
| `cache_status` | 어떤 캐시가 있고 최신인지. 파일 mtime 과 노드 수정 시각 비교 |
| `list_caches` | 씬의 캐시 노드 전부 |
| `clear_cache` | 메모리 캐시(`hou.hscript("cache -c")`)와 디스크 캐시를 구분. **디스크 파일 삭제는 명시적 인자로만** |

되돌릴 수 없는 삭제가 섞여 있다. `scene.load_scene` 이 `discard_changes` 를
요구하는 것과 같은 방식으로 막는다.

## 5. 테이크 (`takes` 모듈)

`create_take`, `list_takes`, `set_current_take`, `delete_take`,
`take_includes` (이 테이크가 어떤 파라미터를 담는가).

`hou.takes` 모듈을 쓴다. 테이크 전환은 씬 상태를 크게 바꾸므로 `@undoable`.

## 6. 뷰포트 심화 (`viewport`)

**주의: 전부 UI 전용이다.** hython 에는 `hou.ui` 가 없다(실측 확인).
`houdini_mcp_base` 의 기존 `viewport` 모듈이 어떻게 보호하는지 보고 같은
방식을 따른다.

| 툴 | 하는 일 |
|---|---|
| `set_viewport_camera` | 카메라로 보기 |
| `set_viewport_direction` | top/front/side/persp |
| `set_viewport_display` | 와이어/셰이드/고스트 |
| `set_viewport_renderer` | Houdini GL / Karma XPU |
| `capture_network_editor` | 네트워크 뷰 캡처. 그래프 구조를 눈으로 보는 데 유용 |
| `list_panes` / `set_current_network` | |

## 7. 선택·플래그 보강 (`edit`)

`get_selection` / `set_selection` 은 이미 있다. 추가로:

- `select_by_pattern` — 패턴/타입으로 골라 선택
- 지오메트리 컴포넌트 선택(점/프림)은 UI 전용이다. 필요한지 먼저 판단

## 작업 순서

1. `explain_node` (3번) — 가장 값어치가 크다
2. 파라미터 심화 (2번) — hda 팩이 이걸 기다린다
3. 노드 변환 (1번)
4. 캐시 (4번)
5. 그래프 인텔리전스 나머지 (3번)
6. 뷰포트 심화 (6번), 테이크 (5번)

## 파일 크기

`edit.py` 는 이미 크다. 여기에 변환·선택을 더 넣기 전에 **먼저 쪼갠다**
(전역 `CLAUDE.md`: 800줄 경계). 모듈을 나눌 때 `TOOL_MODULES` 갱신을
잊지 않는다.

## 검증

```bash
hython -c "from houdini_mcp import get_registry; print(len(get_registry()))"
python -m pytest tests/package_order -q
```

새 툴마다 빈 씬에서 실제로 한 번씩 호출해 본다.
