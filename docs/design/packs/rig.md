# houdini_mcp_rig — 리깅 · KineFX · APEX

> 먼저 [README.md](README.md) 를 읽는다.
>
> **이 문서는 구현 전 초안이 아니라 실측 기록이다.** 2026-09-13, Houdini 22.0.368
> 에서 hython 으로 확인한 것만 적었다. 초안과 다른 것은 전부 실측 쪽으로 고쳤다.

## 무엇을 담나

| 모듈 | 툴 |
|---|---|
| `skeleton` | `create_skeleton`, `skeleton_info`, `list_joints`, `joint_info`, `joint_attributes`, `pose_joints`, `compare_poses` |
| `skin` | `capture_skin`, `weight_stats`, `find_unweighted_points`, `joint_influence`, `deform_skin` |
| `apexgraph` | `apex_graph_info`, `apex_graph_nodes`, `apex_rig_script`, `apex_callbacks`, `apex_callback_info`, `build_fk_rig` |
| `check` | `validate_rig` |

19개다.

## 경계 — 어디까지가 이 팩인가

**포즈 하나까지가 이 팩이고, 시간축은 `houdini_mcp_chop` 이다.**

스켈레톤의 한 상태(조인트 트랜스폼 한 벌)는 여기가 다룬다. 그 상태가 프레임을
따라 흐르기 시작하면 — MotionClip, CHOP 채널, 키프레임, 모션 믹서 — chop 팩으로
넘어간다. 그래서 초안에 있던 `create_motionclip` / `import_mocap` / `retarget` 은
여기에 만들지 않았다. MotionClip 은 "스켈레톤이 시간을 따라 늘어선 것"이라
데이터 모델이 chop 쪽에 가깝고, 두 팩이 같은 것을 각자 감싸면 모델이 어느 쪽을
불러야 하는지 알 수 없게 된다.

`deform_gsplat_with_rig` 는 범위 밖이다(README 참고).

## 기존 구현이 한 방식과 그 한계

- **KineFX SOP 노드를 놓는 수준에 머문다.** `create_rig` 가 rigdoctor + skeleton
  노드를 만들고 끝난다.
- **APEX 를 전혀 쓰지 않는다.** Houdini 20+ 리깅의 중심인데 다섯 구현 중 어느
  것도 건드리지 않는다.
- **리그가 맞는지 검증하지 않는다.** 조인트 방향, 웨이트 합, 바인드 포즈가 말이
  되는지 확인하는 툴이 **하나도 없다.**

---

# 실측: APEX

## APEX 그래프는 지오메트리다

이것이 이 팩 전체의 전제다. APEX 리그 그래프는 특수 파일이나 불투명 객체가
아니라 **점 지오메트리**다. 점 하나가 그래프 노드 하나고, 내용은 점
어트리뷰트에 들어 있다.

```
callback     이 노드가 부르는 APEX 콜백 이름 (string)
name         노드 이름 (string)
parms        노드 파라미터 (dict)
tags         태그 (string array)
properties   속성 (dict)
comment, Cd, P   주석 · 색 · 네트워크 뷰 위치
```

그래서 SOP 출력을 그대로 읽으면 된다.

```python
graph = apex.Graph()
graph.loadFromGeometry(node.geometry())   # True/False
```

`callback`, `name`, `parms` 세 어트리뷰트가 다 있으면 APEX 그래프다. 이 팩은
그것으로 판별한다(`apexgraph.GRAPH_ATTRIBS`).

## 그래프를 코드로 되돌릴 수 있다 — 이 팩에서 가장 값어치 있는 것

`apex.graphscript.GraphDecompiler` 가 그래프를 APEX 스크립트 텍스트로
디컴파일한다. **생성자는 그래프가 아니라 지오메트리를 받는다** (`geo=` 키워드
인자다. `apex.Graph` 를 넘기면 `findPointAttrib` 을 찾다가 죽는다).

```python
decompiler = apex.graphscript.GraphDecompiler(geo=node.geometry())
code = decompiler.generateCode()
```

3조인트 FK 리그의 실제 출력:

```
hips_xform, hips_localxform = TransformObject(restlocal=Matrix4(1.0, 0.0, ...),
    scaleinheritance=0,
    __name='hips',
    __pos=(0.0, 0.0, 0.0))
spine_xform, spine_localxform = TransformObject(parent=hips_xform,
    parentlocal=hips_localxform,
    restlocal=Matrix4(...),
    __name='spine')
```

노드 목록으로 받으면 무슨 리그인지 알 수 없지만 코드로 받으면 바로 읽힌다.
`apex_rig_script` 가 이것이다.

## 콜백 레지스트리는 질의할 수 있다

`apex.callbackRegistry()` 는 `_apex.Registry` 이고, 이렇게 묻는다.

| 메서드 | 돌려주는 것 |
|---|---|
| `callbackDefinitions()` | 등록된 콜백 전체. **2,283개** |
| `findMatchingNames(pattern)` | 글로브 검색. `*ik*` → 15개 |
| `getSignature(name)` | `apex.Signature`. `.inputs()` / `.outputs()` |
| `getParmDefaults(name)` | `apex.Dict` |
| `getIsHidden(name)` | 내부용 콜백인지 |
| `getMinProductVersion(name)` | 최소 Houdini 버전 |
| `subGraphNames()` | 서브그래프 **174개** |

시그니처 원소는 `apex.Parm` 이고 `.name`, `.type_name`, `.isInplace()` 를 갖는다.
이름 앞의 `*` 는 제자리(in place) 인자 표시다 — 같은 값이 입력이자 출력이다.

```
fbik::SolveFABRIK
  inputs:  *solver (FBIKSolver, in place)
  outputs: skel (FBIKSkeleton), *solver (FBIKSolver), success (Bool)
```

> 초안은 콜백이 2,286개라고 적었다. `callbackDefinitions()` 로 세면 2,283개다.
> 세는 방법 차이로 보이고, 요점은 바뀌지 않는다.

## 파이썬 레이어는 전부 import 된다 — `soptoolutils` 같은 함정은 없다

`apex.*` 서브모듈을 hython 에서 하나씩 import 해 봤다. `apexsoputils`,
`control_2`, `constraintutils`, `scene_2`, `sceneevaluators`,
`ui.selectionmanager.utils` 까지 **전부 import 된다.**

딱 하나 `apex.animationcatalog` 만 `hdefereval is only available in a graphical
Houdini` 로 실패한다. MCP 서버는 진짜 Houdini 안에서 도니까 거기서는 뜨겠지만,
hython 으로 검증할 수 없으므로 이 팩은 쓰지 않았다.

쓸 만한 것:

- `apex.apexriggraphutils` — `getRoots`, `getLeaves`, `buildParentMap`,
  `buildDepthMap`, `getSkel`, `getRigGraphAtRest`, `createControlToJointMap`
  (인자가 그래프가 아니라 **parent_map / child_map 딕셔너리**다. 시그니처를
  먼저 보고 쓴다)
- `apex.apexutils` — `isCharacterGeo`, `extractCharGeo`, `findCharElements`
- `apex.utils` — `loadGraph`, `saveGraph`, `graphFromFile`
- `apex.graphscript` — 위의 디컴파일러

> **주의 — 실측 중 한 번 속았다.** 스크래치 디렉토리에서 hython 을 돌렸더니
> 거기 있던 남의 `dbg.py` 가 Houdini 자체 `dbg` 모듈을 가려서 `apex.*` 가
> 통째로 import 실패하는 것처럼 보였다. 스크립트는 격리된 디렉토리에서 돌린다.

## 컨스트레인트는 MCP 에서 닿지 않는다 — 만들지 않았다

초안은 `apex.ConstraintManager` 로 컨스트레인트를 만들자고 했다. 실측 결과
**헤드리스에서는 안 된다.**

```
apex.constraintRegistry().callbackDefinitions()  -> 0개
apex.controlRegistry().callbackDefinitions()     -> 0개
apex.componentRegistry().callbackDefinitions()   -> 0개
apex.brushRegistry().callbackDefinitions()       -> 0개
```

클래스는 import 되지만 레지스트리가 비어 있다. 컨스트레인트 서브그래프는 Animate
뷰어 스테이트가 뜰 때 로드되고, `apex.constraintutils.buildConstraint` 의 첫
인자는 그 스테이트가 소유하는 살아 있는 `apex.Scene` 이다
(`buildConstraint(scene, driven_path, driver_dict, graph_path, ...)`).

옛 OBJ/CHOP 경로로 대체할 수도 있었지만, 그러면 기존 구현 다섯이 한 것을 그대로
베끼는 것이 된다(제1원칙). **컨스트레인트 툴은 이번에 만들지 않았다.** 뷰어
스테이트 없이 `apex.Scene` 을 세우는 경로를 찾으면 그때 넣는다.

---

# 실측: KineFX 지오메트리 스키마

## 스켈레톤은 점과 폴리라인이다

`kinefx::rigdoctor` 를 거친 3조인트 스켈레톤의 실제 점 어트리뷰트:

| 이름 | 타입 | 크기 | 무엇 |
|---|---|---|---|
| `P` | float | 3 | 조인트의 **월드** 위치 |
| `name` | string | 1 | 조인트 이름 |
| `transform` | float (Matrix) | **9** | 월드 회전/스케일 **matrix3** |
| `localtransform` | float (Matrix) | 16 | 부모 기준 로컬 4x4 |
| `parent_idx` | int | 1 | 부모 점 번호. 루트는 -1 |
| `child_indices` | int **array** | - | 자식 점 번호들 |

> 초안은 `transform` 을 4x4 로 암시했다. **matrix3(9개)** 다. 4x4 는
> `localtransform` 이다.
>
> 어트리뷰트 이름은 `parentidx` 가 아니라 `parent_idx` 다.

`parent_idx` 와 `child_indices` 는 rigdoctor 의 `outputparentidx` /
`outputchildindices` 토글을 켜야 나온다. 기본은 꺼져 있다. 그래서 이 팩은
`parent_idx` 가 없으면 **폴리라인에서 부모를 유도한다** — 한 폴리라인 안에서 바로
앞 점이 부모다. 두 경로가 같은 답을 내는지 테스트로 못 박아 두었다.

### 벌크 경로가 없는 곳 하나

부모 유도만은 파이썬 프림 루프를 돈다. 다른 길이 없어서다.

- `hou.sopNodeTypeCategory().nodeVerb("attribwrangle")` 이 **None** 이다.
  attribwrangle 은 서브넷이라 verb 가 없다. `attribcreate`, `pointwrangle` 도
  없다. verb 가 있는 SOP 은 367개고 `attribvop`, `sort`, `groupcreate`, `add`
  등이 여기 든다.
- 정점-점 대응을 통째로 주는 지오메트리 인트린식이 없다. 디테일 인트린식은
  `pointcount`, `vertexcount`, `primitivecount` 뿐이고 프림에는
  `vertexpoints` 인트린식이 아예 없다(`vertexcount` 만 있다). `hou.Prim.points()`
  가 유일한 길이다.

문제가 되지 않는 이유는 **스켈레톤이 작기 때문**이다. 본 수는 조인트 수와 같아서
많아야 수백이다. 이 팩에서 실제로 커지는 데이터는 스킨 웨이트고, 그쪽은 전부
numpy 다.

## 스켈레톤을 만드는 길 — Skeleton SOP 은 못 쓴다

`kinefx::skeleton` 은 뷰포트에서 클릭으로 조인트를 놓는 노드라 MCP 에서 쓸 수
없다. `create_skeleton` 은 대신 이렇게 한다.

```
python SOP (점 + 폴리라인 + name 을 코드로 만든다)
  -> kinefx::rigdoctor (inittransforms, outputparentidx)
```

생성된 파이썬 코드는 이 팩을 import 하지 않는다. 팩이 없는 머신에서 씬을 열어도
노드가 쿡돼야 하기 때문이다(LOP 팩의 `author_python` 과 같은 원칙).

## 포즈 — `kinefx::rigpose` 도 못 쓴다

`kinefx::rigpose` 의 `transformations` 는 FolderParmTemplate(멀티파름)이고,
`.set(1)` 로 개수를 올려도 인스턴스 파라미터가 생기지 않는다. `commands` 는
문자열이 아니라 int(멀티파름 개수)다. 헤드리스로 포즈를 채워 넣을 길이 없다.

그래서 `pose_joints` 는 **`kinefx::rigattribwrangle` 을 조인트마다 하나씩 만들어
얕은 것부터 잇는다.** 부모를 먼저 돌려야 자식의 피벗이 맞기 때문에 체인이어야
한다. 생성되는 VEX 는 사람이 읽고 고칠 수 있다.

```c
int affected[] = array(1, 2);          // 이 조인트와 모든 자손
if (find(affected, @ptnum) < 0) return;
vector pivot = point(0, "P", 1);       // 피벗을 입력에서 직접 읽는다
matrix3 rot = ident();
rotate(rot, radians(45.0), {0, 0, 1});
matrix xform = ident();
translate(xform, -pivot);
xform *= matrix(rot);
translate(xform, pivot);
@P = @P * xform;
3@transform = 3@transform * rot;
```

> **함정**: attribwrangle 계열의 `class` 파라미터는 점이 **2** 다. 0 은 detail 이라
> 스니펫이 한 번만 돌고 아무 일도 일어나지 않는다 — 에러도 나지 않는다.

## `boneCapture` 레이아웃 — 웨이트 검증의 근거

`kinefx::jointcaptureproximity` 출력의 실제 모습:

```
점 어트리뷰트 boneCapture : float, size = 2 * maxinfluences, 자격 "Index Pair"
디테일 어트리뷰트 pCaptFrame (float), pCaptSkelRoot (string)
```

값은 **끼워 넣기(interleave)** 돼 있다.

```
[조인트번호0, 웨이트0, 조인트번호1, 웨이트1, ...]
```

빈 슬롯의 조인트 번호는 **-1** 이다. `max_influences=2` 로 캡처하면 size 가 4다.

조인트 번호가 가리키는 이름은 어트리뷰트에 딸린 **인덱스 페어 테이블**에 있다.

```python
table = geo.findPointAttrib("boneCapture").indexPairPropertyTables()[0]
table.numIndices()      # 조인트 수
table.propertyNames()   # ('pCaptPath', 'pCaptData')
table.stringPropertyValueAtIndex("pCaptPath", i)     # 조인트 이름
table.floatListPropertyValueAtIndex("pCaptData", i)  # float 20개
```

> `pCaptData` 는 float 20개짜리라 `floatPropertyValueAtIndex` 로는 못 읽는다
> (`Property not found` 가 난다). `floatListPropertyValueAtIndex` 를 쓴다.

`pCaptData` 20개 중 **앞 16개가 그 조인트의 역 바인드 월드 행렬**이다. 행 우선이고
이동 성분이 3행에 있다. 뒤집으면 캡처 당시의 조인트 월드 위치가 나온다 — 실측으로
확인했다.

```
joint world P : [(0, 0, 0), (0.5, 1, 0), (1, 2, 0)]
inv(pCaptData[:16]) 의 이동 성분 : [0 0 0], [0.5 1 0], [1 2 0]   # 정확히 일치
```

뒤 4개는 전부 1.0 이고 테이퍼/캡 값이라 스키닝에 쓰이지 않는다.

이것이 `validate_rig` 의 `bind_pose_drift` 검사의 근거다. 지금 스켈레톤이 캡처할
때 쓴 것과 다른지를 **추측이 아니라 데이터로** 안다.

## 디폼 체인

```
kinefx::jointdeform
  입력 0  Rest Geometry    (boneCapture 를 가진 메시)
  입력 1  Capture Pose     (바인드 포즈 스켈레톤)
  입력 2  Animated Pose    (목표 포즈 스켈레톤)
```

`apex::buildfkgraph` 의 입력 순서는 반대쪽으로 헷갈리기 쉽다.

```
apex::buildfkgraph
  입력 0  바탕 그래프  (빈 apex::graph 노드)
  입력 1  스켈레톤
```

거꾸로 꽂으면 `No transform attribute exists, unable to compute local transforms`
가 난다.

---

# `validate_rig` — 이 팩의 간판

기존 구현 다섯 중 리그를 검증하는 것이 하나도 없다. 검사는 전부 numpy 벌크다.

## 스켈레톤

| 검사 | 등급 | 언제 |
|---|---|---|
| `no_joints` / `no_root` | error | 조인트가 없거나 루트가 없다(계층이 고리) |
| `multiple_roots` | warning | 루트가 여럿 — 조각이 떨어져 있다 |
| `orphan_joints` | error | 부모 번호가 범위 밖 |
| `self_parented` | error | 자기 자신을 부모로 |
| `hierarchy_cycle` | error | 루트에서 닿지 않는 조인트 |
| `empty_joint_names` / `duplicate_joint_names` | error | 이름으로 조인트를 찾는 모든 단계가 깨진다 |
| `generic_joint_names` | info | `joint1` 같은 기본 이름 |
| `missing_transform` | error | `transform` 어트리뷰트가 없다 |
| `degenerate_transform` | error | 행렬식 ≈ 0, 축이 무너졌다 |
| `mirrored_transform` | warning | 행렬식 < 0, 축이 뒤집혔다 |
| `scaled_transform` / `nonuniform_scale` | warning | 회전에 스케일이 섞였다 |
| `zero_length_bone` | warning | 부모와 겹쳐 방향을 정의하지 못한다 |

## 스킨 (`skin` 인자를 주면)

| 검사 | 등급 | 언제 |
|---|---|---|
| `unweighted_points` | error | 웨이트 합이 0 — 디폼할 때 제자리에 남는다 |
| `weight_sum_not_one` | error | 합이 1이 아니다 (허용 오차 1e-4) |
| `negative_weights` | error | 점을 반대로 끌어당긴다 |
| `excess_influences` | warning | 점당 영향 조인트가 상한을 넘는다 |
| `invalid_joint_index` | error | 없는 조인트를 가리킨다 |
| `unknown_capture_joints` | error | 스킨과 스켈레톤이 다른 리그에서 왔다 |
| `unused_joints` | warning | 캡처에는 있는데 아무 점도 끌지 않는다 |
| `uncaptured_joints` | info | 스켈레톤에는 있는데 캡처에 없다 |
| `bind_pose_drift` | warning | 바인드 포즈와 지금 포즈가 벌어졌다 |

지적마다 `fix` 가 붙는다 — 어느 툴을 어떤 인자로 다시 부르면 되는지까지 적는다.

# 검증

`tests/rig/` 에 회귀 테스트가 있다. 28개 단정이고 `python -m pytest tests/rig -q`
로 돈다. **등록된 툴 19개를 하나도 빠짐없이 호출하고**, 부르지 않은 툴이 있으면
`uncalled` 로 테스트가 실패한다.

시나리오:

```
create_skeleton (hips/spine/chest)  -> list_joints 로 계층 확인
tube(240점) + capture_skin          -> weight_stats 로 합이 1인지 확인
pose_joints (spine Z 45도)          -> chest 만 움직였는가
deform_skin                         -> 240점 전부 따라왔는가, bbox 가 바뀌었는가
build_fk_rig -> apex_rig_script     -> TransformObject 3개가 코드로 나오는가
validate_rig                        -> 지적 0개
```

그리고 **일부러 망가뜨린다.**

| 망가뜨린 것 | 잡은 것 |
|---|---|
| chest 를 spine 에서 떼어냄 | `multiple_roots` (+ 겹친 neck 에 `zero_length_bone`) |
| rigdoctor 를 거치지 않은 날 스켈레톤 | `missing_transform` (ok = false) |
| 20개 점의 웨이트를 반으로 | `weight_sum_not_one` count 20 |
| 10개 점을 아무 데도 안 붙게 | `unweighted_points` count 10 |
| `max_influences=1` 로 검사 | `excess_influences` count 230 |
| 포즈 걸린 스켈레톤을 바인드 포즈로 | `bind_pose_drift` |

숫자까지 단정한다. "무언가 잡았다"가 아니라 "정확히 20개와 10개를 잡았다"를
못 박아야, 나중에 검사가 망가져도 조용히 지나가지 않는다. `weight_stats` 가 같은
데이터를 같은 수로 세는지도 함께 본다 — 두 툴이 다르게 세면 둘 중 하나가 틀린
것이다.

> **팩마다 `tests/<팩>/scenario.py` 를 두므로 `from scenario import MARKER` 로
> 읽으면 안 된다.** pytest 가 테스트 디렉토리를 `sys.path` 에 올리는데, 먼저 읽힌
> 팩의 것이 `sys.modules["scenario"]` 를 차지해 나중에 읽는 팩이 남의 MARKER 를
> 쓰게 된다. 실제로 밟았다 — sop 테스트 17개가 통째로 깨졌다.
> `importlib.util.spec_from_file_location` 으로 팩 전용 모듈 이름을 붙여 읽는다
> (`houdini_mcp_rig_scenario`). chop 팩이 먼저 세운 방식을 그대로 따랐다.
