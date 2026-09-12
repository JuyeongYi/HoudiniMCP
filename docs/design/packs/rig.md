# houdini_mcp_rig — 리깅 · KineFX · APEX

> 먼저 [README.md](README.md) 를 읽는다. 이 팩은 **조사 비중이 가장 크다.**

## 무엇을 담나

스켈레톤, 스키닝, 리그 그래프, 컨스트레인트, 모캡 리타깃.

기존 구현이 가진 것: dcc kinefx 8 (`create_rig`, `capture_joints`,
`apply_mocap`, `set_rig_pose`, `build_retarget_motion_mixer`,
`create_insect_rig`, `validate_ground_contacts`, `deform_gsplat_with_rig`),
dcc constraints 6 (`create_parent_constraint`, `create_position_constraint`,
`create_orient_constraint`, `create_blend_constraint`, `list_constraints`,
`delete_constraint`).

`deform_gsplat_with_rig` 는 범위 밖이다(README 참고).

## 기존 구현이 한 방식과 그 한계

- **KineFX SOP 노드를 놓는 수준에 머문다.** `create_rig` 가 rigdoctor + skeleton
  노드를 만들고 끝난다.
- **APEX 를 전혀 쓰지 않는다.** Houdini 20+ 의 리깅은 APEX 그래프가 중심인데
  다섯 구현 중 어느 것도 건드리지 않는다.
- **리그가 맞는지 검증하지 않는다.** 조인트 방향, 웨이트 합, 바인드 포즈가
  말이 되는지 확인하지 않는다.

## 우리가 쓸 경로

### 1. `apex` 모듈이 번들돼 있다 (실측 확인)

최상위에 있는 것:

```
Graph, GraphExecutor, GraphDebugger, Scene, SceneCharacter, SceneGraph, SceneTool
Control, ControlManager, ControlMap, ControlGroup, TransformControl, MultiControl
Constraint, ConstraintManager, ConstraintType
AnimLayer, AnimationCatalog, ChannelPrimBindings, ChannelPrimMapping
Registry, Signature, Parm, ParmDict, Tags, CompatibilityMap
callbackRegistry, controlRegistry, constraintRegistry, componentRegistry
graphops, findSkeletonJoints, findFirstSkeletonJoint, getOutputShapeNamesFromRig
tagRigControls, matchControlsFromTemplate, mergeAnimation, trimClip, packToFolders
```

`apex.callbackRegistry()` 에만 콜백이 2,286개다. 이것이 Houdini 22 리깅의
실제 API다.

`apex.graphops` 는 그래프 조작 헬퍼다. **가장 먼저 볼 것.**

`kinefx` 모듈은 import 는 되지만 **비어 있다**(실측 확인). KineFX 기능은
SOP 노드와 `apex` 에 있다.

### 2. 컨스트레인트는 `apex.ConstraintManager` 로

기존 구현처럼 OBJ 레벨 컨스트레인트 CHOP 네트워크를 짜는 것은 옛 방식이다.
22.0 에서 무엇이 표준인지 먼저 확인하고, **옛 경로와 APEX 경로 둘 다 필요하면
툴 이름으로 구분한다** (`create_obj_constraint` vs `create_apex_constraint`).

### 3. 리그를 검증한다

기존 구현에 없는 것이고, 리깅에서 가장 값어치 있는 것이다.

- 조인트 계층이 끊겼는지, 루트가 여럿인지
- 조인트 방향(`transform` 어트리뷰트)이 일관된지
- **스킨 웨이트 합이 1인지** — `boneCapture` 어트리뷰트를 numpy 로 합산
- 웨이트가 0인 점(어디에도 안 붙은 점)
- 영향 조인트 수가 과한 점
- 바인드 포즈와 현재 포즈의 차이

numpy 벌크 경로로 읽는다 (README 제3원칙). 점 10만 개짜리 캐릭터에서
파이썬 루프를 돌면 못 쓴다.

### 4. 스켈레톤은 지오메트리다

KineFX 스켈레톤은 점과 폴리라인이다. 계층은 어트리뷰트로 들어 있다
(`name`, `transform`, 부모 연결). 특수 API를 찾기 전에 **지오메트리로 읽는
경로**를 먼저 확인한다 — `houdini_mcp_sop` 의 벌크 접근자를 그대로 쓸 수 있다.

## 툴 초안

전부 **조사 후에 확정한다.** 이건 초안이다.

| 모듈 | 툴 |
|---|---|
| `skeleton` | `create_skeleton`, `list_joints` (계층 포함), `joint_info`, `set_joint_transform`, `skeleton_stats` |
| `skin` | `capture_skin`, `weight_stats` (합/최소/최대/영향 수), `find_unweighted_points`, `transfer_weights` |
| `apex` | `list_rigs`, `rig_graph` (APEX 그래프 구조), `list_rig_controls`, `set_control`, `rig_info` |
| `pose` | `get_pose`, `set_pose`, `reset_to_bind` |
| `mocap` | `import_mocap`, `retarget` — 소스/타깃 스켈레톤 매핑 결과를 반환 |
| `constraint` | `create_constraint`, `list_constraints`, `delete_constraint` |
| `check` | `validate_rig` — 위 검증 항목 전부 |

## 먼저 확인할 것 (이 팩은 특히 많다)

1. `apex.graphops` 함수 전체
2. `apex.Graph` 를 파일/노드에서 얻는 방법 — SOP 노드에서 APEX 그래프를
   꺼내는 경로
3. `apex.callbackRegistry()` 반환 구조 — 2,286개를 어떻게 질의할지
4. `apex.Scene` / `SceneCharacter` 의 역할
5. 22.0 의 표준 리깅 워크플로 — 공식 문서를 읽는다:
   <https://www.sidefx.com/docs/houdini/character/index.html>
6. 스켈레톤 지오메트리의 어트리뷰트 스키마 (`name`, `transform`, `path`)
7. `boneCapture` 어트리뷰트의 정확한 레이아웃

**조사 결과가 이 문서와 다르면 문서를 고친다.** 실측이 우선이다.

## 검증

```
테스트 캐릭터(또는 간단한 튜브 + 조인트 3개)
→ create_skeleton → list_joints 로 계층 확인
→ capture_skin → weight_stats 로 합이 1인지 확인
→ 조인트 회전 → 지오메트리가 따라 움직이는가 (점 위치 변화로 확인)
→ validate_rig → 문제 없음
→ 일부러 조인트 끊기 → validate_rig 가 잡는가
```
