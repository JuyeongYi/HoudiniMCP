# houdini_mcp_dop — DOP 공통

> 먼저 [README.md](README.md) 를 읽는다.

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

## 우리가 쓸 경로

### 1. `doptoolutils` 를 먼저 본다 (실측 확인: 번들돼 있다)

셸프의 "Pyro from Object" 등이 쓰는 코드다. 우리가 셋업 매크로를 처음부터
쓰는 것보다, 셸프가 하는 일을 그대로 하고 **무엇을 만들었는지 설명해서
돌려주는** 편이 낫다.

```bash
hython -c "import doptoolutils; print([f for f in dir(doptoolutils) if not f.startswith('_')])"
```

관련 모듈도 확인한다: `dopsmoketoolutils`, `dopfluidtoolutils`,
`doppyrotoolutils`, `dopparticlefluidtoolutils` 등이 있을 수 있다.

### 2. 셋업 툴은 만든 것을 전부 설명한다

```python
return {
    "created": [
        {"path": "/obj/pyro_sim", "type": "dopnet", "role": "시뮬 컨테이너"},
        {"path": "/obj/pyro_sim/pyrosolver", "type": "pyrosolver",
         "role": "연소·확산 솔버", "key_parms": {"diffusion": 0.0}},
    ],
    "next_steps": ["소스 지오메트리를 /obj/source 에 연결", "해상도는 divsize 로"],
}
```

블랙박스를 주지 않는다. 모델이 이어서 손볼 수 있어야 한다.

### 3. 돌려 보고 결과를 준다

이것이 핵심이다. 시뮬은 **터지는 게 정상**이고, 터졌는지 아는 것이 전부다.

```python
# 프레임을 순차로 진행시키며 매 프레임 상태를 기록
for frame in range(start, end + 1):
    hou.setFrame(frame)
    dopnet.cook()
    # 프레임마다: 오브젝트 수, 파티클/복셀 수, 쿡 시간, 메모리, 에러
```

돌려줄 것: 프레임별 시간, 요소 수 추이, **발산 감지**(값이 폭발하거나 NaN),
메모리 증가율, 에러가 처음 난 프레임.

낮은 해상도로 몇 프레임만 돌려 보는 `test_simulation` 툴이 실제로 유용하다.
기존 구현에 없다.

### 4. DOP 데이터는 HOM 이 주는 대로 읽는다

`hou.DopNode`, `hou.DopObject`, `hou.DopData`, `hou.DopSimulation` 의 실제
메서드를 `dir()` 로 확인하고 쓴다. 필드(볼륨)는 `hou.Volume` 경로로 통계만
뽑는다 — 복셀을 통째로 넘기지 않는다.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `setup` | `create_dopnet`, `setup_simulation` (pyro/flip/rbd/vellum/grain). 만든 것 전부 설명 |
| `inspect` | `list_dop_objects`, `dop_object_info`, `list_dop_fields`, `field_stats` (해상도·복셀·값 범위) |
| | `dop_relationships`, `simulation_info` (솔버, 서브스텝, 캐시 상태) |
| `run` | `step_simulation`, `test_simulation` (저해상도 N프레임 + 프레임별 리포트) |
| | `reset_simulation`, `sim_memory` |
| `cache` | `write_sim_cache`, `cache_status` — DOP 캐시는 여기, 일반 캐시는 base |
| `check` | `validate_simulation` — 솔버 연결, 소스 유무, 프레임 범위, 서브스텝, 충돌 객체 |

## 하위 팩

`houdini_mcp_dop` 가 자리잡은 뒤에 나눈다. 각각 `"requires":
["houdini_mcp", "houdini_mcp_dop"]`.

- `houdini_mcp_dop_pyro` — 연소·확산·난류·업레스
- `houdini_mcp_dop_flip` — 점성·표면장력·화이트워터·메시화
- `houdini_mcp_dop_rbd` — 프랙처·컨스트레인트·글루
- `houdini_mcp_dop_vellum` — 천·헤어·소프트바디

**지금은 만들지 않는다.** 공통 팩 없이 하위를 먼저 만들면 중복이 생긴다.

## 먼저 확인할 것

1. `doptoolutils` 계열 모듈 전체 목록과 각 함수
2. `hou.DopNode` / `DopObject` / `DopData` / `DopSimulation` 실제 메서드
3. 시뮬을 프레임 진행시키는 올바른 방법 — `hou.setFrame` + `cook` 이 맞는지,
   `dopnet.displayNode().cook()` 이 필요한지
4. 22.0 의 발산 감지 수단 — 필드 max 값으로 볼지, 솔버가 경고를 내는지

## 검증

```
create_dopnet → setup_simulation("pyro") → 만든 노드 목록이 설명과 맞는가
→ validate_simulation → 소스 없음 경고
→ 소스 연결 → test_simulation(5프레임, 저해상도)
→ 프레임별 복셀 수 증가가 보이는가, 에러 없이 끝나는가
```
