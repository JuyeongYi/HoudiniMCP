# houdini_mcp_dop_rbd

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_dop_rbd.json` |
| requires | `houdini_mcp`, `houdini_mcp_base`, `houdini_mcp_dop` |
| 툴 | 2개 |
| 모듈 (`TOOL_MODULES`) | `diagnose` |

## 개요

```text
DOP 의 RBD 전문 팩 - 조각과 강체 시뮬을 진단한다.

    diagnose  rbd_piece_stats(시뮬 전 조각 점검), rbd_sim_report(프레임별 시뮬 읽기)

houdini_mcp_dop 은 솔버를 가리지 않는 것을 담고, RBD 에만 뜻이 있는 것은 여기에
둔다(프로젝트 CLAUDE.md 의 팩 분리 규칙). RBD Bullet Solver SOP 처럼 dopnet 없이
도는 RBD 도 받는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`rbd_piece_stats`](#rbd_piece_stats) | `diagnose` | RBD 조각을 시뮬 전에 점검한다. 시작하자마자 떨어질 조각을 미리 찾는다. |  |
| [`rbd_sim_report`](#rbd_sim_report) | `diagnose` | RBD 시뮬을 프레임별로 읽어 무엇이 언제 움직이고 끊겼는지 돌려준다. |  |

## 모듈별 상세

### `diagnose`

RBD 조각과 시뮬을 진단한다 - 무너지면 왜 무너졌는지 수치로 안다.

#### rbd_piece_stats

```python
rbd_piece_stats(path: str, constraints: str | None = None, constraints_output: int = 0, density: float = 1000.0, sliver_volume: float = 0.05, output: int = 0, limit: int = 10)
```

RBD 조각을 시뮬 전에 점검한다. 시작하자마자 떨어질 조각을 미리 찾는다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 조각을 내는 SOP. 예: rbdmaterialfracture, voronoifracture, assemble |
| `constraints` | `str \| None` | `None` | 제약 지오메트리를 내는 SOP. 주면 조각마다 glue 수를 센다. 예: connectadjacentpieces |
| `constraints_output` | `int` | `0` | constraints 노드의 출력 번호. RBD Constraint Properties 는 1. |
| `density` | `float` | `1000.0` | 질량 추정에 쓸 밀도(kg/m³). 조각에 density 가 있으면 그것을 쓴다. |
| `sliver_volume` | `float` | `0.05` | 이보다 부피가 작으면 얇은 파편으로 센다(m³). |
| `output` | `int` | `0` | path 노드의 출력 번호. |
| `limit` | `int` | `10` | 목록에 담을 조각 수. 최대 50. |

#### rbd_sim_report

```python
rbd_sim_report(path: str, frames: list[float] | None = None, start: float = 1, end: float = 24, exclude: str = '', quiet_until: float | None = None, constraints_output: int | None = None, moved_threshold: float = 0.1, output: int = 0, group_by: str = '', limit: int = 10)
```

RBD 시뮬을 프레임별로 읽어 무엇이 언제 움직이고 끊겼는지 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | 시뮬 결과 조각을 내는 SOP. 예: rbdbulletsolver, dopimport |
| `frames` | `list[float] \| None` | `None` | 볼 프레임들. 생략하면 start~end 를 12개쯤으로 나눈다. |
| `start` | `float` | `1` | frames 를 생략했을 때 시작 프레임. |
| `end` | `float` | `24` | frames 를 생략했을 때 끝 프레임. |
| `exclude` | `str` | `''` | 통계에서 뺄 조각 이름 패턴. 공백으로 여러 개. 예: "projectile". 빠진 조각은 위치만 따로 보여 준다. |
| `quiet_until` | `float \| None` | `None` | 이 프레임까지는 조각이 가만히 있어야 한다(보통 충돌 직전). |
| `constraints_output` | `int \| None` | `None` | 제약 출력 번호. 생략하면 라벨에 Constraint 가 든 출력을 찾는다(RBD Bullet Solver 는 1). |
| `moved_threshold` | `float` | `0.1` | 이보다 많이 움직이면 "움직였다" 로 센다(m). |
| `output` | `int` | `0` | 조각을 읽을 출력 번호. RBD Bullet Solver 는 3(Simulation Points)이 조각마다 점 하나라 가장 빠르다. |
| `group_by` | `str` | `''` | 조각별 문자열 어트리뷰트 이름. 주면 프레임마다 그 값별로 움직인 수를 나눠 준다(0번 출력에서 읽는다). 예: "part" - 지붕만 떨어지는지 벽도 밀리는지 가른다. |
| `limit` | `int` | `10` | 목록에 담을 조각 수. 최대 50. |
