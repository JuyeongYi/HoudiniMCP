# houdini_mcp_top — PDG / TOPs

> 먼저 [README.md](README.md) 를 읽는다.

## 무엇을 담나

TOP 네트워크를 짓고 쿡하고, **워크아이템이 왜 실패했는지** 아는 것.

기존 구현이 가진 것: fx PDG/TOPs 10 (`get_pdg_graph`, `cook_top_node`,
`cancel_top_cook`, `pause_top_cook`, `dirty_work_items`,
`generate_static_items`, `get_work_item_info`, `get_work_item_states`,
`get_top_network_info`, `get_top_scheduler_info`), dcc pdg 5, dcc
`cook_top_network`.

## 기존 구현이 한 방식과 그 한계

- **워크아이템 상태를 개수로만 준다.** "실패 3개"라고 알려 주고 끝난다.
  **왜** 실패했는지 — 어느 커맨드였고 stderr 에 뭐가 찍혔는지 — 를 주지 않는다.
  PDG 를 쓰는 이유의 절반이 배치 작업 디버깅인데 거기서 멈춘다.
- **쿡을 블로킹으로 돈다.** TOP 쿡은 몇 시간이 걸릴 수 있다.
- **`pdg` 모듈을 얕게 쓴다.** `hou.TopNode` 래퍼만 쓰고 `pdg` 자체 API를
  거의 안 건드린다.

## 우리가 쓸 경로

### 1. `pdg` 모듈을 직접 쓴다 (실측 확인: 번들)

`hou.TopNode` 가 다리를 놓아 준다:

```
getPDGGraphContext / getPDGGraphContextName / getPDGNode / getPDGNodeId / getPDGNodeName
addPDGFilter / enablePDGFilter / removePDGFilter / isPDGFilter
```

`pdg` 최상위에 있는 것 일부(실측):

```
GraphContext, BaseType, BaseTypeRegistry, BatchWorkItem, ActiveItemBlock
AttributeInfo, AttributeOwner, AttributeUtils, AttributePattern
AttributeInt / Float / String / File / Geometry / PyObject / Dictionary
AddNodeResult, AddDependencyResult, AddParameterResult, AddSchedulerResult
```

워크아이템 하나에서 얻을 것: 인덱스, 상태, **실행된 커맨드 문자열**,
stdout/stderr 로그 경로, 출력 파일 목록, 어트리뷰트 전체, 쿡 시간,
의존 관계.

### 2. 실패를 설명한다 — 이 팩의 핵심 툴

`failed_work_items` 가 돌려줄 것:

```json
{
  "failed_count": 3,
  "items": [{
     "index": 17,
     "node": "/tasks/topnet1/ropfetch1",
     "command": "hython ... -f 17",
     "exit_code": 1,
     "stderr_tail": "...마지막 20줄...",
     "log_path": "...",
     "attributes": {"frame": 17}
  }],
  "common_cause": "3개 모두 같은 에러: 출력 디렉토리가 없습니다"
}
```

같은 에러로 여러 개가 죽었으면 **묶어서 한 번만** 보여 준다. 모델 컨텍스트를
아끼고 원인을 바로 보여 준다. 기존 구현에 이런 게 없다.

### 3. 쿡은 비동기로

`cook_top_node` 를 블로킹으로 만들지 않는다. 거는 툴과 상태를 묻는 툴을
분리한다. `houdini_mcp_render` 와 같은 구조다 — 두 팩이 같은 패턴을 쓰도록
맞춘다.

PDG 는 이벤트 콜백을 제공한다. `GraphContext` 에 콜백을 걸어 상태를 모으고,
`top_status` 툴이 그 스냅샷을 돌려주는 구조가 폴링보다 낫다. 콜백 API가
실제로 무엇인지 조사한다.

### 4. 스케줄러

`scheduler_info` 는 스케줄러 종류와 설정, **현재 가용 슬롯과 실행 중인
작업 수**를 준다. 로컬 스케줄러면 코어 수와 동시 실행 수. 그래야 왜 느린지
안다.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `build` | `create_top_network`, `create_top_node`, `connect_top_nodes` — base 의 `create_node` 로 되면 만들지 않는다 |
| `cook` | `cook_top` (비동기), `top_status`, `cancel_top_cook`, `pause_top_cook`, `dirty_work_items`, `generate_static_items` |
| `inspect` | `top_graph` (노드 + 아이템 수 + 상태 요약), `list_work_items` (상태 필터, 개수 제한), `work_item_info` (전체 상세) |
| `debug` | **`failed_work_items`** — 위 형태. 이 팩의 간판 툴 |
| | `work_item_log` (stdout/stderr 꼬리) |
| `scheduler` | `scheduler_info` |

## 먼저 확인할 것

1. `pdg.GraphContext` 에서 노드·워크아이템을 순회하는 정확한 경로
2. 워크아이템의 커맨드·로그 경로를 얻는 API
3. PDG 이벤트 콜백 API
4. 비 UI 세션(hython)에서 TOP 쿡이 되는지 — 서버는 UI Houdini 안에서 돈다
5. 워크아이템 상태 enum 값들

## 검증

```
TOP 네트워크 → generic generator (아이템 5개) → python script
→ cook_top → top_status 폴링 → 완료
→ list_work_items → 5개 확인
→ 일부러 실패하는 스크립트로 바꿈 → cook_top
→ failed_work_items → stderr 에 실제 에러가 담겼는가, 공통 원인이 묶였는가
```
