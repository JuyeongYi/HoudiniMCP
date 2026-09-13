# houdini_mcp_rig

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_rig.json` |
| requires | `houdini_mcp`, `houdini_mcp_base` |
| 툴 | 19개 |
| 모듈 (`TOOL_MODULES`) | `skeleton`, `skin`, `apexgraph`, `check` |

## 개요

```text
리깅 툴 팩 — 스켈레톤 · 스킨 웨이트 · APEX 리그 그래프 · 리그 검증.

    skeleton   조인트를 만들고 계층을 읽고 포즈를 건다
    skin       스킨 웨이트를 만들고 numpy 로 분석하고 디폼한다
    apexgraph  APEX 리그 그래프를 읽고 코드로 되돌린다. 콜백 2,286개를 질의한다
    check      validate_rig — 리그가 맞는지 검사한다

이 팩이 기존 구현과 갈라지는 지점은 둘이다.

1. **검증한다.** 조사한 기존 MCP 구현 다섯 중 리그가 맞는지 보는 것이 하나도
   없다. `validate_rig` 가 계층·이름·조인트 방향·웨이트 합·바인드 포즈를
   numpy 로 한 번에 검사하고, 지적마다 다음에 무엇을 할지 알려 준다.
2. **APEX 를 쓴다.** 기존 다섯은 전부 KineFX SOP 노드를 놓는 수준에 머문다.
   `apex_rig_script` 는 리그 그래프를 APEX 스크립트 코드로 디컴파일해서 돌려준다.

**경계** — 모션 데이터는 이 팩이 아니다. MotionClip·CHOP 채널·키프레임은
`houdini_mcp_chop` 이 맡는다. 여기는 **포즈 하나**(스켈레톤의 한 상태)까지만
다룬다. 시간축을 따라 흐르는 값이 나오면 chop 팩으로 넘어간다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`create_skeleton`](#create_skeleton) | `skeleton` | 조인트 목록으로 KineFX 스켈레톤을 만든다. | ✓ |
| [`skeleton_info`](#skeleton_info) | `skeleton` | 스켈레톤 전체를 한눈에 — 조인트 수, 루트, 깊이, 본 길이, 어트리뷰트. |  |
| [`list_joints`](#list_joints) | `skeleton` | 조인트를 계층 정보와 함께 나열한다. |  |
| [`joint_info`](#joint_info) | `skeleton` | 조인트 하나를 자세히 — 계층 경로, 월드 위치, 회전행렬, 자식, 본 길이. |  |
| [`pose_joints`](#pose_joints) | `skeleton` | 조인트를 돌리거나 옮긴다. 자손이 함께 따라온다. | ✓ |
| [`compare_poses`](#compare_poses) | `skeleton` | 두 스켈레톤의 같은 이름 조인트가 얼마나 벌어졌는지 비교한다. |  |
| [`joint_attributes`](#joint_attributes) | `skeleton` | 스켈레톤이 실제로 들고 있는 조인트 어트리뷰트를 값 예시와 함께 보여준다. |  |
| [`capture_skin`](#capture_skin) | `skin` | 메시를 스켈레톤에 붙이고, 붙은 결과를 통계로 돌려준다. | ✓ |
| [`weight_stats`](#weight_stats) | `skin` | 스킨 웨이트 전체의 분포를 통계로 돌려준다. |  |
| [`find_unweighted_points`](#find_unweighted_points) | `skin` | 어디에도 붙지 않은 점을 찾는다. 디폼할 때 제자리에 남는 점들이다. |  |
| [`joint_influence`](#joint_influence) | `skin` | 조인트 하나가 어느 점을 얼마나 끌고 있는지 본다. |  |
| [`deform_skin`](#deform_skin) | `skin` | 스킨을 포즈에 맞춰 디폼하고, 실제로 움직였는지 측정해서 돌려준다. | ✓ |
| [`apex_graph_info`](#apex_graph_info) | `apexgraph` | APEX 리그 그래프의 구조를 요약한다 — 노드·와이어·포트 수, 콜백 분포, 에러. |  |
| [`apex_graph_nodes`](#apex_graph_nodes) | `apexgraph` | APEX 그래프의 노드를 콜백·태그·파라미터와 함께 나열한다. |  |
| [`apex_rig_script`](#apex_rig_script) | `apexgraph` | APEX 그래프를 APEX 스크립트 코드로 디컴파일해서 돌려준다. |  |
| [`apex_callbacks`](#apex_callbacks) | `apexgraph` | APEX 콜백 레지스트리를 검색한다. 리그 그래프에서 쓸 수 있는 연산 목록이다. |  |
| [`apex_callback_info`](#apex_callback_info) | `apexgraph` | APEX 콜백 하나의 시그니처 — 입력·출력 이름과 타입, 파라미터 기본값. |  |
| [`build_fk_rig`](#build_fk_rig) | `apexgraph` | 스켈레톤에서 APEX FK 리그 그래프를 만든다. | ✓ |
| [`validate_rig`](#validate_rig) | `check` | 리그가 맞는지 검사한다. 이 팩의 간판이다. |  |

## 모듈별 상세

### `skeleton`

스켈레톤을 만들고 읽고 포즈를 건다.

#### create_skeleton

```python
create_skeleton(parent: str, joints: Sequence[dict[str, Any]], comment: str, name: str | None = None)
```

조인트 목록으로 KineFX 스켈레톤을 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `parent` | `str` | 필수 | 스켈레톤을 만들 부모 네트워크. 보통 /obj 아래 geo 노드. |
| `joints` | `Sequence[dict[str, Any]]` | 필수 | 조인트 목록. 각각 다음 키를 갖는다. name     - 조인트 이름 (영어). 반드시 유일해야 한다. position - 월드 위치 [x, y, z]. parent   - 부모 조인트 이름. 루트는 생략하거나 null. |
| `comment` | `str` | 필수 | 이 스켈레톤이 무엇인지 영어로. 예: Three joint test skeleton |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |

#### skeleton_info

```python
skeleton_info(path: str)
```

스켈레톤 전체를 한눈에 — 조인트 수, 루트, 깊이, 본 길이, 어트리뷰트.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 스켈레톤을 내보내는 SOP 노드 경로. |

#### list_joints

```python
list_joints(path: str, pattern: str = '*', limit: int = 200)
```

조인트를 계층 정보와 함께 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 스켈레톤을 내보내는 SOP 노드 경로. |
| `pattern` | `str` | `'*'` | 이름 패턴. Houdini 글로브를 쓴다. 예: arm_*, *_L |
| `limit` | `int` | `200` | 돌려줄 조인트 수 상한. 최대 400. |

#### joint_info

```python
joint_info(path: str, joint: str)
```

조인트 하나를 자세히 — 계층 경로, 월드 위치, 회전행렬, 자식, 본 길이.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 스켈레톤을 내보내는 SOP 노드 경로. |
| `joint` | `str` | 필수 | 조인트 이름. list_joints 로 확인한다. |

#### pose_joints

```python
pose_joints(path: str, poses: Sequence[dict[str, Any]], comment: str, name: str | None = None)
```

조인트를 돌리거나 옮긴다. 자손이 함께 따라온다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 스켈레톤을 내보내는 SOP 노드 경로. |
| `poses` | `Sequence[dict[str, Any]]` | 필수 | 포즈 목록. 각각 다음 키를 갖는다. joint     - 조인트 이름. rotate    - [rx, ry, rz] 도 단위. 생략하면 0. translate - [tx, ty, tz]. 생략하면 0. |
| `comment` | `str` | 필수 | 이 포즈가 무엇인지 영어로. 예: Bend elbow 45 degrees |
| `name` | `str \| None` | `None` | 노드 이름 앞머리. 생략하면 Houdini 가 정한다. |

#### compare_poses

```python
compare_poses(path: str, reference: str, limit: int = 20)
```

두 스켈레톤의 같은 이름 조인트가 얼마나 벌어졌는지 비교한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 비교할 스켈레톤 SOP 경로. |
| `reference` | `str` | 필수 | 기준이 되는 스켈레톤 SOP 경로. 보통 바인드 포즈. |
| `limit` | `int` | `20` | 많이 움직인 조인트를 몇 개까지 보여줄지. 최대 100. |

#### joint_attributes

```python
joint_attributes(path: str, limit: int = 12)
```

스켈레톤이 실제로 들고 있는 조인트 어트리뷰트를 값 예시와 함께 보여준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 스켈레톤을 내보내는 SOP 노드 경로. |
| `limit` | `int` | `12` | 어트리뷰트마다 보여줄 조인트 수. 최대 40. |

### `skin`

스킨 웨이트를 만들고 읽고 적용한다.

#### capture_skin

```python
capture_skin(mesh: str, skeleton: str, comment: str, name: str | None = None, method: str = 'proximity', max_influences: int = 4, dropoff: float | None = None, normalize: bool = True)
```

메시를 스켈레톤에 붙이고, 붙은 결과를 통계로 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `mesh` | `str` | 필수 | 스킨이 될 메시 SOP 경로. |
| `skeleton` | `str` | 필수 | 스켈레톤 SOP 경로. 바인드 포즈여야 한다. |
| `comment` | `str` | 필수 | 무엇을 캡처하는지 영어로. 예: Capture body mesh to spine joints |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |
| `method` | `str` | `'proximity'` | proximity 또는 biharmonic. |
| `max_influences` | `int` | `4` | 점 하나에 붙일 조인트 수 상한. |
| `dropoff` | `float \| None` | `None` | 거리 감쇠. 생략하면 노드 기본값. |
| `normalize` | `bool` | `True` | 웨이트 합을 1로 맞출지. |

#### weight_stats

```python
weight_stats(path: str, top: int = 12)
```

스킨 웨이트 전체의 분포를 통계로 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | boneCapture 를 가진 SOP 노드 경로. |
| `top` | `int` | `12` | 영향이 큰 조인트를 몇 개까지 보여줄지. 최대 100. |

#### find_unweighted_points

```python
find_unweighted_points(path: str, limit: int = 20)
```

어디에도 붙지 않은 점을 찾는다. 디폼할 때 제자리에 남는 점들이다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | boneCapture 를 가진 SOP 노드 경로. |
| `limit` | `int` | `20` | 점을 몇 개까지 보여줄지. 최대 100. |

#### joint_influence

```python
joint_influence(path: str, joint: str, limit: int = 20)
```

조인트 하나가 어느 점을 얼마나 끌고 있는지 본다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | boneCapture 를 가진 SOP 노드 경로. |
| `joint` | `str` | 필수 | 조인트 이름. weight_stats 의 top_joints 에서 확인한다. |
| `limit` | `int` | `20` | 웨이트가 큰 점을 몇 개까지 보여줄지. 최대 100. |

#### deform_skin

```python
deform_skin(rest: str, capture_pose: str, animated_pose: str, comment: str, name: str | None = None)
```

스킨을 포즈에 맞춰 디폼하고, 실제로 움직였는지 측정해서 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `rest` | `str` | 필수 | 캡처된 메시 SOP 경로 (boneCapture 를 가진 것). |
| `capture_pose` | `str` | 필수 | 바인드 포즈 스켈레톤 SOP 경로. |
| `animated_pose` | `str` | 필수 | 목표 포즈 스켈레톤 SOP 경로. |
| `comment` | `str` | 필수 | 무엇을 디폼하는지 영어로. 예: Deform body to bent elbow pose |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |

### `apexgraph`

APEX 리그 그래프를 읽는다.

#### apex_graph_info

```python
apex_graph_info(path: str)
```

APEX 리그 그래프의 구조를 요약한다 — 노드·와이어·포트 수, 콜백 분포, 에러.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | APEX 그래프를 내보내는 SOP 노드 경로. |

#### apex_graph_nodes

```python
apex_graph_nodes(path: str, pattern: str = '*', limit: int = 50, parms: bool = True)
```

APEX 그래프의 노드를 콜백·태그·파라미터와 함께 나열한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | APEX 그래프를 내보내는 SOP 노드 경로. |
| `pattern` | `str` | `'*'` | 노드 이름 패턴. APEX 매칭 문법을 그대로 쓴다. 예: arm_*, *ik* |
| `limit` | `int` | `50` | 돌려줄 노드 수 상한. 최대 200. |
| `parms` | `bool` | `True` | 파라미터와 포트 이름까지 함께 줄지. |

#### apex_rig_script

```python
apex_rig_script(path: str)
```

APEX 그래프를 APEX 스크립트 코드로 디컴파일해서 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | APEX 그래프를 내보내는 SOP 노드 경로. |

#### apex_callbacks

```python
apex_callbacks(pattern: str = '*', limit: int = 50, include_hidden: bool = False)
```

APEX 콜백 레지스트리를 검색한다. 리그 그래프에서 쓸 수 있는 연산 목록이다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `pattern` | `str` | `'*'` | 이름 패턴. 예: *ik*, fbik::*, Transform* |
| `limit` | `int` | `50` | 돌려줄 개수 상한. 최대 200. |
| `include_hidden` | `bool` | `False` | 내부용으로 숨겨진 콜백까지 포함할지. |

#### apex_callback_info

```python
apex_callback_info(name: str)
```

APEX 콜백 하나의 시그니처 — 입력·출력 이름과 타입, 파라미터 기본값.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `name` | `str` | 필수 | 콜백 이름. apex_callbacks 로 찾은 이름을 그대로 준다. |

#### build_fk_rig

```python
build_fk_rig(skeleton: str, comment: str, name: str | None = None)
```

스켈레톤에서 APEX FK 리그 그래프를 만든다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `skeleton` | `str` | 필수 | 스켈레톤 SOP 경로. transform 어트리뷰트가 있어야 한다 (create_skeleton 이나 kinefx::rigdoctor 를 거친 것). |
| `comment` | `str` | 필수 | 이 리그가 무엇인지 영어로. 예: FK rig for test tube character |
| `name` | `str \| None` | `None` | 노드 이름. 생략하면 Houdini 가 정한다. |

### `check`

리그가 맞는지 검증한다.

#### validate_rig

```python
validate_rig(skeleton: str, skin: str | None = None, max_influences: int = 4)
```

리그가 맞는지 검사한다. 이 팩의 간판이다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `skeleton` | `str` | 필수 | 스켈레톤 SOP 경로. |
| `skin` | `str \| None` | `None` | boneCapture 를 가진 스킨 메시 SOP 경로. 생략하면 스켈레톤만 본다. |
| `max_influences` | `int` | `4` | 점 하나에 허용할 영향 조인트 수. 게임 엔진은 보통 4다. |
