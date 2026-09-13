# houdini_mcp_dop — DOP 공통

> 먼저 [README.md](README.md) 를 읽는다.

**상태: 구현 완료 (툴 18개).** 아래는 초안이 아니라 실제로 만든 것과 그렇게
만든 이유다. 실측으로 확인한 사실에는 (실측) 을 달아 두었다 —
Houdini 22.0.368 기준이다.

## 무엇을 담나

시뮬레이션 네트워크를 짓고, **돌려 보고, 무슨 일이 일어났는지 아는** 것.
솔버별 전문은 하위 팩으로 뺀다 (`houdini_mcp_dop_pyro` 등).

기존 구현이 가진 것: fx DOPs 8 (`get_dop_object`, `get_dop_field`,
`get_dop_relationships`, `list_dop_objects`, `get_simulation_info`,
`get_sim_memory_usage`, `reset_simulation`, `step_simulation`),
dcc simulation 4, fx Workflows 의 `setup_pyro_sim` / `setup_flip_sim` /
`setup_rbd_sim` / `setup_vellum_sim`.

## 기존 구현이 한 방식과 그 한계

- **셋업 매크로가 블랙박스다.** `setup_pyro_sim()` 이 노드 열 개를 만들고 끝난다.
  무엇을 만들었는지, 왜 그렇게 했는지 모델이 모른다. 고치려면 다시 뜯어야 한다.
- **시뮬을 돌려 보지 않는다.** 만들고 끝난다. 터지는지, 몇 초 걸리는지,
  메모리를 얼마나 먹는지 모른다.
- **DOP 데이터 구조를 얕게 본다.** `hou.DopObject` / `hou.DopData` 가 주는
  것을 거의 안 쓴다.

---

## 실측 결과 — 초안과 달랐던 것

### 1. `doptoolutils` 의 셋업 매크로는 MCP 에서 쓸 수 없다

초안은 "셸프가 하는 일을 그대로 하자"고 했다. 실제로 불러 보니 **핵심 함수가
셸프 툴 문맥을 요구한다.**

`genericConvertToDopObject(objectnode, dopobjecttype, nodename)` 는 시그니처만
보면 뷰어를 요구하지 않는다. 오브젝트 타입 18개를 전부 넣어 보면 이렇다.

| 결과 | 타입 |
|---|---|
| 통과 | clothobject(::2.0), femhybridobject, femsolidobject, fluidobject, rbdpointobject, sandobject, smokeobject, solidobject, staticobject, terrainobject, wireobject |
| `hou.shelves.runningTool()` 이 None | **rbdobject**, rbdfracturedobject, rbdglueobject |
| `hou.ui` 없음 | **flipfluidobject**, particlefluidobject, rbdpackedobject |

강체와 FLIP — 가장 많이 쓰는 둘이 막힌다. `doprbdtoolutils._appendRestNode` 가
`hou.shelves.runningTool().name()` 을 부르기 때문인데, 이것은 hython 뿐 아니라
**GUI 에서도** 셸프 버튼을 거치지 않으면 None 이다. `doptoolutils.
createNewDopNetwork(init_dopnet=True)` 도 `toolutils.setUpOrientation` 을 거쳐
`hou.ui.orientationUpAxis()` 를 탄다.

`doppyrotoolutils` / `dopsmoketoolutils` / `dopsparsepyrotools` /
`dopparticlefluidtoolutils` 는 공개 함수 대부분이 `kwargs`(셸프 scriptargs)를
첫 인자로 받는다. SOP 팩이 `soptoolutils` 에서 겪은 것과 같다.

**그래서 조립은 우리가 직접 한다.** doptoolutils 에서는 **데이터만** 가져온다.

- `theDopObjectTypeDict` — 오브젝트 타입 -> 솔버 타입, 오브젝트 합침 여부
- `theSolverOrder` — 솔버 머지 순서(정적 → 강체 → 천 → 파티클 → 유체)

이 표는 `_common.recipes()` / `_common.solver_order()` 가 읽고, 거기에 없는
타입(popobject, vellumobject, mpmobject, smokeobject_sparse, filamentobject,
rippleobject, crowdobject)만 우리 표로 보탠다. doptoolutils 가 깨져도 팩은
우리 표만으로 동작한다.

결과적으로 **초안이 걱정한 블랙박스 문제가 저절로 해결된다.** 우리가 조립하니
무엇을 왜 만들었는지 전부 설명해 돌려줄 수 있다.

### 2. 프레임 진행은 `hou.setFrame` + `dopnet.cook()` 이 맞다

`hou.DopSimulation.setTime` 은 dopnet 이 소유한 시뮬에서 `hou.PermissionError`
를 낸다(HOM 문서에 명시, 실측 일치). `dopnet.displayNode().cook()` 은 필요
없고 `dopnet.cook()` 이면 된다. 시뮬은 앞 프레임에 의존하므로 프레임을
건너뛰지 않고 순차로 돈다.

### 3. `hou.DopObject.geometry()` 는 오브젝트 공간이다 (실측)

강체가 떨어져도 `geometry().boundingBox()` 는 변하지 않는다. 월드 위치는
`transform().extractTranslates()` 에 있다. 이걸 모르면 "시뮬이 안 돈다"고
잘못 판단한다.

스모크·FLIP 컨테이너는 `geometry()` 가 **None** 이다. 필드는
`obj.fieldGeometry(name)` 으로 얻는다 — `fieldGeometry` 는 인자 없이 못 부르고
필드 이름을 받는다.

### 4. 발산 감지 — 싼 경로가 있다 (실측)

필드에 NaN 이 섞이면 `hou.Volume.volumeAverage()` 가 NaN 을, Inf 가 섞이면
`volumeMax()` 가 Inf 를 돌려준다. 복셀을 numpy 로 전부 읽지 않고도 잡을 수
있다. 그래서 프레임별 감시는 `volumeMin/Max/Average` 세 값만 쓰고(복셀 수와
무관하게 싸다), 히스토그램·NaN 복셀 개수가 필요할 때만
`allVoxelsAsString` + `numpy.frombuffer` 로 간다(`deep=True`).

속도는 두 곳을 봐야 한다. 파티클·FLIP 은 점 어트리뷰트 `v` 에 있지만,
**강체는 점 속도가 없다.** 강체 속도는 `Position` 서브데이터(`RBD_State`)의
`vel` / `angvel` 에 있다. 초안은 이걸 놓쳤고, 처음 구현에서 강체 발산이
감지되지 않아 실측으로 찾았다.

### 5. Output DOP 의 `execute` 는 플레이바 범위를 쓴다 (실측)

Output DOP 에 `f1`/`f2` 파라미터가 있어서 범위를 지정할 수 있어 보이지만,
1~5 를 넣고 `execute` 를 눌렀더니 **240 프레임(플레이바 범위)** 이 구워졌다.
사용자의 플레이바를 건드리게 되므로 쓰지 않는다.

대신 File DOP 을 write 모드로 체인 끝에 끼우고 프레임을 우리가 진행시킨다.
그러면 굽는 동안의 프레임별 리포트도 함께 나온다. File DOP 의 `mode` 는 토큰을
받지 않는 순서 메뉴라 인덱스로 걸어야 한다(`auto`/`read`/`write`/`none`).

File DOP 은 **시뮬 타임스텝마다** 쓴다. 서브스텝이 2면 파일이 대략 두 배로
나온다(실측: substep=2 로 5프레임 → 파일 9개). 그래서 파일 이름을 프레임에서
계산해 맞히지 않고, 패턴의 `$SF`/`$F` 를 와일드카드로 바꿔 디렉토리를 훑는다.
`hou.text.expandStringAtFrame` 은 `$SF` 를 모른다(빈 문자열이 된다).

---

## 만든 툴 18개

| 모듈 | 툴 | 기존 다섯 구현과 다른 점 |
|---|---|---|
| `setup` | `create_dopnet` | 만든 노드 4개를 역할·파라미터와 함께 설명해 돌려준다 |
| | `add_dop_object` | 셋업 매크로를 대체한다. 오브젝트 타입 하나로 널·DOP 오브젝트·솔버·머지·DOP Import 까지 잇고 전부 설명한다 |
| | `add_dop_force` | 체인 어디에 끼웠는지와 바뀐 체인을 돌려준다 |
| `objects` | `list_dop_objects` | 이름·경로만이 아니라 월드 위치, 요소 수, 메모리, affector, 가진 필드 |
| | `dop_object_info` | 레코드 4종(Basic/Options/RelInGroup/RelInAffectors)과 서브데이터별 메모리 |
| | `dop_relationships` | 릴레이션십 + 오브젝트별 affector 목록 |
| | `simulation_info` | 솔버를 머지 순서로 정렬해 준다. 캐시·타이밍 설정 전부 |
| | `dop_node_info` | **체인에 실제로 연결됐는지**(`in_solve_chain`). base 의 `node_info` 가 못 알려 주는 것 |
| `fields` | `list_dop_fields` | 해상도·복셀 수·메모리. 값은 안 읽는다 |
| | `field_stats` | 싼 층/깊은 층 2단. 벡터는 MAC 성분별로 |
| | `field_data_types` | 서브데이터 30개를 필드/임시필드/컨테이너/그 밖으로 가른다 |
| `run` | `step_simulation` | 프레임별 쿡 시간·메모리·요소 수·필드 통계·발산 징후 |
| | `test_simulation` | **기존 구현에 없다.** 해상도를 낮춰 N프레임 돌리고 되돌린다 |
| | `reset_simulation` | 버린 메모리와 리셋 직후의 초기 상태를 돌려준다 |
| | `sim_memory` | 오브젝트별·서브데이터별로 갈라 준다. 총량 하나가 아니다 |
| `cache` | `write_sim_cache` | 굽는 동안의 프레임별 리포트를 함께 준다 |
| | `sim_cache_status` | 메모리 캐시와 디스크 캐시 양쪽 |
| `check` | `validate_simulation` | 쿡 없이 8가지를 점검하고 **고치는 법**을 함께 준다 |

파일은 여덟이다. 헬퍼는 씬을 만지는 `_common`(359줄)과 결과를 읽는
`_state`(541줄)로 갈랐다 — 합치면 900줄이라 전역 규칙의 800줄 경계를 넘는다.

## 일부러 만들지 않은 것

- **`setup_simulation("pyro"/"flip"/"vellum")` 매크로.** 초안 표에 있었지만
  만들지 않았다. 파이로·FLIP 은 소스 볼륨 플러밍(fluidsource SOP →
  sourcevolume DOP → 솔버의 Sourcing 입력)이 솔버마다 다르고, 그걸 하나의 툴에
  넣으면 이 팩이 비판하는 블랙박스가 된다. `add_dop_object` 로 컨테이너를
  만드는 데까지가 공통 팩의 경계이고, 소스 플러밍은 `houdini_mcp_dop_pyro` /
  `_flip` 의 일이다.
- **하위 팩 자체.** 초안대로 공통 팩이 자리잡은 뒤에 나눈다.
- **강체 프랙처·컨스트레인트 툴.** `houdini_mcp_dop_rbd` 로 간다.

## 하위 팩

`houdini_mcp_dop` 가 자리잡았으니 이제 나눌 수 있다. 각각 `"requires":
["houdini_mcp", "houdini_mcp_dop"]`.

- `houdini_mcp_dop_pyro` — 소스 플러밍, 연소·확산·난류·업레스
- `houdini_mcp_dop_flip` — 점성·표면장력·화이트워터·메시화
- `houdini_mcp_dop_rbd` — 프랙처·컨스트레인트·글루. **진단부터 시작했다
  (2026-09-13).** `rbd_piece_stats`(시뮬 전 조각 부피·질량·얇은 파편·glue 없는
  조각), `rbd_sim_report`(프레임별 이동·끊긴 제약·충돌 전 움직임). dopnet 이
  아니라 packed 조각을 내는 SOP 을 받아 RBD Bullet Solver SOP 도 본다. 만든
  계기와 실측은 `diagnose.py` 모듈 docstring 에 있다. 프랙처·제약 생성 툴은
  아직 없다.
- `houdini_mcp_dop_vellum` — 천·헤어·소프트바디

하위 팩이 쓸 수 있는 것: `_common.recipes()` 의 타입 표는 하위 팩이 그대로
쓸 수 있고, `_state.run_frames` 의 프레임 리포트 형식도 같이 쓰면 된다.
다만 **팩끼리 import 하지 않는 것이 저장소 규칙**이므로, 공유가 필요해지면
그때 base 로 올린다.

## 검증

초안의 시나리오를 그대로 돌렸고, 18개 툴을 하나도 빠짐없이 실호출했다.

```
create_dopnet → validate_simulation → 솔버 없음 에러
→ add_dop_object(rbdobject) → validate → 충돌체 없음 경고
→ add_dop_object(staticobject) → add_dop_force(windforce) → validate → ok
→ test_simulation(1~8, 해상도 1/8) → 박스가 y 로 -0.42 이동, 에러 없음
→ step/list/info/relationships/memory/reset/write_sim_cache/sim_cache_status
```

스모크 시나리오에서 초안이 보자고 한 "프레임별 증가"가 실제로 보인다.
복셀 수는 고정이라 `element_trend` 로는 안 보이고, `field_trend` 의
density max 로 본다.

```
smoke_container.density: [0.0, 0.53, 1.06, 1.59, 2.12, 2.65]
```

발산 감지는 `speed_limit` 를 0.01 로 낮춘 자유 낙하로 확인했다 — 프레임 2에서
`max body speed 2.0 exceeds 0` 이 잡히고 `first_divergence_frame: 2` 가 나온다.
NaN/Inf 경로는 필드 상태를 꾸며 넣어 세 가지 경고가 모두 나오는 것을 확인했다.

성능: 이 규모(강체 2개, 스모크 16³~16×24×16)에서는 프레임당 10~20ms 로
대화형으로 충분하다. 실제 프로덕션 해상도는 훨씬 느리므로 `test_simulation` 의
`resolution_factor` 가 제 몫을 한다.
