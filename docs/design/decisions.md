# 설계 결정 기록

Houdini MCP 의 구조를 정하면서 내린 결정과 그 근거다. 대부분 Houdini 설치본을
직접 실측해서 얻은 사실에 기대고 있으므로, 같은 실험을 반복하지 않으려면 여기를
먼저 본다.

측정 환경: Houdini 22.0.368 / Python 3.13 / Windows 11 / Apprentice
측정일: 2026-09-09
회귀 테스트: `tests/package_order/` (25개)

---

## 1. 배포 단위는 2개다 — 서버와 툴 팩

**결정**: `houdini_mcp`(서버 + 레지스트리)와 `houdini_mcp_tools_*`(툴 팩, N개).
레지스트리를 별도 패키지로 빼지 않는다.

**이유**: 툴 팩이 서버 패키지의 모듈을 import 하는 것은 **로드 순서와 무관하게
항상 성공**한다. 패키지 처리(HOUDINI_PATH·`sys.path` 구성)가 모든 스크립트
실행보다 먼저 끝나기 때문이다. 양쪽 순서를 모두 실측했고 둘 다 통과했다.

**기각한 대안 — UE 식 3분할**: UE 는 `ToolsetRegistry` 를
`ModelContextProtocol` 에서 분리했지만, 그 이유는 설계 미학이 아니라 C++ 빌드
제약이다.

| UE 의 분리 이유 | 우리 상황 |
|---|---|
| C++ 모듈 링크 의존성 | Python 은 빌드 타임 링크가 없다 |
| `EditorOnly` vs Runtime 타겟 분리 | Houdini 에 그런 구분이 없다 |
| 플러그인 개별 on/off | 해당 없음 |

조사한 기존 구현 중 레지스트리 구조를 가진 dcc-mcp-houdini 도 레지스트리를 별도
배포 단위로 빼지 않았다.

**단, 논리적 분리는 유지한다**: `registry.py` 는 `hou` 에도 `mcp` 에도 의존하지
않는 순수 파이썬이다. Houdini 없이 단위 테스트할 수 있고, 나중에 패키지를 쪼개야
하면 파일 이동으로 끝난다.

**나중에 분리가 정당해지는 조건**: ① 제3자가 툴 팩을 서버와 독립적으로 버전
관리해야 할 때 ② 레지스트리에 MCP 외 소비자가 생길 때 ③ 서버 없이 툴만 설치하는
시나리오가 생길 때. 현재는 셋 다 해당 없다.

---

## 2. 순서는 "단계 경계"에 건다 — `requires` 나 `process_order` 가 아니라

**결정**:

```
pythonrc.py   ← 툴 팩 N개가 레지스트리에 등록      (상호 순서 무관)
     │           단계 경계는 Houdini 가 보장한다
uiready.py    ← 서버가 기동. 이 시점에 모든 툴이 등록되어 있다
```

**이유**: 단계 간 순서는 절대 보장되지만, 같은 단계 안에서 패키지들의 순서를
제어하는 수단은 전부 취약하다.

| 수단 | 실측 결과 |
|---|---|
| `requires` | **순서를 바꾸지 않는다.** 대상이 아직 처리되지 않았어도 통과한다 |
| `process_order` | **같은 디렉토리 안에서만** 유효하다. 다른 슬롯에 설치하면 무력화 |
| `hpath` prepend | 실행 순서가 **처리 순서의 역순**이 된다. 오독하기 쉽다 |

`process_order: 1` 을 준 패키지는 가장 먼저 처리되지만 `pythonrc.py` 는 가장
나중에 실행된다. 직관과 반대다.

UE 는 플러그인 의존성으로 로드 순서가 보장되는데도 옵저버 + `PostEngineInit`
지연 + 즉시 시도로 3중 방어한다. Houdini 는 그 보장조차 없다.

---

## 3. 훅 선택 — `123.py` 는 쓰지 않는다

| 훅 | 여러 패키지에 있을 때 | 용도 |
|---|---|---|
| `pythonrc.py` | **전부 실행** | 툴 등록 |
| `ready.py` | **전부 실행** | (미사용) |
| `uiready.py` | **전부 실행** | 서버 기동 |
| `123.py` | **첫 번째 1개만** | **금지** |
| `456.py` | 씬 로드마다 | 부적합 |

`123.py` 는 HOUDINI_PATH 최상위 하나만 이기고 나머지는 조용히 무시된다. 사용자
개인 `123.py` 까지 덮어친다.

**`uiready.py` 를 고른 이유**: UI 없이 MCP 를 쓸 일이 없다고 결정했다. UI 가 완전히
뜬 뒤라 `hdefereval` 의 이벤트 루프를 믿을 수 있다. 헤드리스(hython/hbatch)까지
지원하려면 `ready.py` 로 옮기고 `hou.isUIAvailable()` 로 분기해야 한다.

---

## 4. `requires` 표기 규칙

툴 팩은 `"requires": ["houdini_mcp"]` 를 반드시 넣는다. 순서용이 아니라 **오설치를
조기에 드러내는** 용도다 — 서버 없이 설치되면 그 패키지가 통째로 차단되므로,
조용히 반쯤 동작하는 상태를 막는다.

| 값 | 결과 |
|---|---|
| `["houdini_mcp"]` | 통과 — JSON 파일명에서 확장자를 뺀 이름 |
| `["houdini_mcp.json"]` | 차단 — 확장자를 붙이면 안 된다 |
| `["Houdini_MCP"]` | 차단 — **대소문자를 구분한다** |

디렉토리 슬롯을 넘어서도 찾는다. Houdini 가 전체 패키지 파일 목록을 먼저 수집한
뒤 판정하기 때문에, 서버와 툴 팩을 서로 다른 위치에 설치해도 된다.

**`houdini_mcp.json` 이라는 파일명이 공개 인터페이스다.** 바꾸면 모든 툴 팩이
차단된다.

---

## 5. 서버는 Houdini 프로세스 안에서 돈다

**결정**: MCP 서버를 Houdini 인프로세스로 구동하고, MCP SDK 를 Houdini 의
파이썬에 설치한다.

**기각한 대안 — 외부 서버 + 내장 `hwebserver` RPC** (fxhoudinimcp 방식): Houdini 에
아무것도 설치하지 않아도 되고 크래시가 격리되지만, 배포 단위가 Houdini 패키지 +
외부 pip 패키지로 늘어난다. "서버 패키지 로드 시 서버 실행"이라는 요구사항의
문자 그대로가 아니게 된다.

**대가**: Houdini 빌드를 올리면 SDK 설치가 따라오지 않는다. `uiready.py` 가
`ImportError` 를 잡아 재설치를 안내한다.

**설치 위치**: `$HFS/python313/Lib/site-packages` (관리자 권한 필요).
user site(`%APPDATA%\Python\Python313\site-packages`)도 동작하지만 — GUI 에서도
`sys.path` 에 잡히는 것을 확인했다 — 계정별이고 다른 Python 3.13 앱과 공유된다.

**버전은 `requirements.txt` 에 범위로 박는다**: `mcp>=2.2,<3`. 2.0 에서 FastMCP 가
MCPServer 로 바뀌는 파괴적 변경이 있었으므로 메이저를 넘기면 안 된다. `uiready.py`
는 import 실패 시 설치된 버전을 확인해서, 아예 없는 것과 버전이 안 맞는 것을
구분해 안내한다.

---

## 6. 트랜스포트는 streamable-http

**결정**: `http://127.0.0.1:22926/mcp`

포트는 `int("HOU", 36) = 22926` 이다. 알파벳을 36진수로 읽은 값이라 기억하기
쉽고, 흔히 쓰이는 8000/9000번대를 피해 충돌 가능성이 낮다.

| 트랜스포트 | 가능? | 이유 |
|---|---|---|
| streamable-http | 채택 | 이미 떠 있는 프로세스에 클라이언트가 붙을 수 있는 유일한 방식 |
| stdio | 불가 | 클라이언트가 서버를 **자식 프로세스로 띄우는** 구조. Houdini 는 이미 떠 있고 stdin/stdout 도 Houdini 가 쓴다 |
| SSE | 불가 | MCP 스펙에서 streamable-http 로 대체된 레거시 |

`HOUDINI_MCP_HOST` / `HOUDINI_MCP_PORT` / `HOUDINI_MCP_PATH` 로 조정한다. 기본은
루프백 바인딩이라 외부에 열리지 않는다.

---

## 7. Houdini 의 asyncio 정책을 우회한다

**함정**: Houdini 22 는 asyncio 를 자체 구현(`haio.py`)으로 대체하고
`HoudiniEventLoopPolicy` 를 설치한다(`hwebserver.py:1705`, GUI 가 이미 켜 놓는다).

```python
def new_event_loop(self):
    return get_event_loop()   # 스레드와 무관하게 항상 같은 루프
def set_event_loop(self, loop):
    pass                       # 무시한다
```

그 루프는 메인 스레드에서만 돈다(`check_thread`). 그래서 백그라운드 스레드에서
`asyncio.new_event_loop()` 를 쓰면 이렇게 죽는다:

```
RuntimeError: Current thread is not the main thread
```

**해결**: 정책을 거치지 않고 표준 루프 클래스를 직접 인스턴스화한다.

```python
asyncio.ProactorEventLoop()   # win32
asyncio.SelectorEventLoop()   # 그 외
```

**전역 정책은 건드리지 않는다.** Houdini 자신이 그 정책에 의존한다.

조사한 기존 구현 문서에는 이 함정이 없다. 인프로세스 HTTP 를 하는 건
dcc-mcp-houdini 뿐이고, 나머지는 서버가 Houdini 밖이라 마주칠 일이 없었다.

---

## 8. `hou` 호출은 메인 스레드로 넘긴다

**결정**: `affinity="main"`(기본값) 인 툴은 `hdefereval` 로 메인 스레드에
위임한다. `mainthread.run_in_main_thread()` 가 담당한다.

`executeInMainThreadWithResult()` 대신 `executeDeferred()` + `threading.Event`
조합을 쓴다. 전자는 타임아웃을 받지 않아서, Houdini 가 긴 작업에 붙들리면 워커
스레드가 영원히 매달린다. 기본 한도 120초.

이미 메인 스레드이거나 UI 가 없으면 마샬링 없이 직접 호출한다. 전자를 거르지
않으면 자기 자신을 기다려 데드락이 난다.

**참고 — 기존 구현들의 처리**:

| | 툴 수 | 메인 스레드 처리 |
|---|---|---|
| dcc-mcp-houdini | 259 | `hou.ui.addEventLoopCallback` 큐/펌프 + affinity 태그 |
| fxhoudinimcp | 188 | `executeInMainThreadWithResult()` + 120초 |
| capoomgit | 25 | `QTimer` 100ms 폴링 |
| oculairmedia | 43 | **없음** |
| eliiik | 33 | **없음** |

---

## 9. `mcp` 2.x — `FastMCP` 가 아니라 `MCPServer`

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'.
This is mcp 2.x, where FastMCP was renamed to MCPServer ...
```

조사한 기존 구현 5종은 **전부 1.x `FastMCP` 기반**이다. `docs/research/` 문서도 그
기준이므로, 아키텍처 패턴은 참고하되 API 코드는 그대로 쓸 수 없다.

쓰는 API: `MCPServer(name=, version=, instructions=)`,
`add_tool(fn, name=, description=, ...)`, `remove_tool(name)`,
`run_streamable_http_async(host=, port=, streamable_http_path=)`.

`add_tool` 은 함수 시그니처로 입력 스키마를 만든다. 그래서 어댑터가 메인 스레드
래퍼를 씌울 때 `functools.wraps` 로 `__wrapped__` 를 달아 시그니처를 보존한다.

`add_tool`/`remove_tool` 이 있으므로 서버가 뜬 뒤 등록된 툴도 반영할 수 있다.
`adapter.ToolSync` 가 레지스트리를 구독해 처리한다.

---

## 10. 포트 충돌은 first-wins

**결정**: 포트가 이미 쓰이고 있으면 서버를 띄우지 않고 경고만 남긴다. 보통 다른
Houdini 인스턴스가 먼저 떠 있는 경우다.

경고는 로그와 **Houdini 상태바**(`hou.ui.setStatusMessage`) 양쪽에 낸다.
로그는 기본적으로 파일에만 쌓이므로(11번 항목), 사용자가 바로 알아채야 하는
이런 경고는 상태바에도 띄운다.

두 번째 인스턴스를 따로 붙이려면 `HOUDINI_MCP_PORT` 를 다르게 준다
(`scripts/run-houdini.ps1 -Port 22927`).

**기각한 대안 — 포트 자동 증가**: 실제 포트가 매번 달라져 `.mcp.json` 의 고정
URL 과 어긋난다. dcc-mcp-houdini 는 고정 포트 게이트웨이 + first-wins 로 풀었다.

---

## 11. 로깅 — JSONL 통합 파일 하나

**결정**: 파일 로그는 `houdini_mcp.jsonl` **하나**에 JSONL 로 남긴다.
[JsonlLogViewer](https://github.com/JuyeongYi/JsonlLogViewer) 로 읽는다.

**툴 팩별로 파일을 가르지 않는다.** 뷰어가 `category` 필드로 걸러 볼 수 있으므로
파일을 나눌 이유가 없다. 나누면 한 요청이 여러 파일에 흩어져 시간순으로 읽기만
어려워진다.

뷰어가 요구하는 스키마:

| 필드 | 우리가 넣는 값 |
|---|---|
| `timestamp` (필수) | ISO 8601, 로컬 타임존 오프셋 포함 |
| `level` (필수) | `error` / `warn` / `info` / `debug` — Python 레벨을 소문자로 매핑 |
| `msg` (필수) | 메시지 |
| `category` (선택) | `server`, `adapter`, `tools.<팩이름>` |

여기에 `exception`(스택 트레이스)을 덧붙인다. 실제 출력:

```json
{"timestamp": "2026-09-10T00:02:42.856537+09:00", "level": "error",
 "msg": "failed node_info", "category": "tools.houdini_mcp_tools_demo",
 "exception": "Traceback (most recent call last):\n..."}
```

`ensure_ascii=False` 로 한글을 그대로 남긴다.

**콘솔 출력은 기본으로 끈다.** 켜 두면 툴을 부를 때마다 Houdini 콘솔 창이 떠서
작업을 방해한다. 로그는 파일에만 쌓고, 필요할 때 뷰어로 본다.
`HOUDINI_MCP_LOG_CONSOLE=1` 로 켜면 평문으로 낸다(콘솔은 사람이 읽으므로).

**툴 팩 이름은 자동으로 잡는다**: `tool` 데코레이터가 함수의 `__module__` 최상위
이름을 `ToolSpec.package` 에 채운다(`registry.infer_package`). 툴 작성자가 따로
선언할 것이 없다.

`adapter.bind()` 가 모든 툴 호출을 감싸며 호출·실패를 그 팩 로거로 남긴다.
그래서 툴이 던진 예외는 어느 팩에서 났는지와 함께 자동으로 기록된다.

| 환경변수 | 기본 | 뜻 |
|---|---|---|
| `HOUDINI_MCP_LOG_DIR` | `$HOUDINI_USER_PREF_DIR/log` | `off` 로 파일 로깅 해제 |
| `HOUDINI_MCP_LOG_LEVEL` | `INFO` | |
| `HOUDINI_MCP_LOG_CONSOLE` | `0` | `1` 이면 Houdini 콘솔에도 출력 |

파일은 5MB 단위로 3개까지 로테이션한다.

---

## 12. 툴 팩은 도메인마다 별도 패키지로 가른다

**결정**: 관련 있는 툴끼리 묶어 별도 Houdini 패키지로 분리한다. 경계는 Houdini 의
컨텍스트·도메인 계층을 따른다.

```
houdini_mcp                  서버 + 레지스트리 (툴 없음)
├─ houdini_mcp_base          컨텍스트를 가리지 않는 것 전부 (조회·편집·파라미터·
│                            지오메트리·뷰포트)
├─ houdini_mcp_sop           SOP 전문
├─ houdini_mcp_dop           DOP 공통
│  ├─ houdini_mcp_dop_pyro   솔버별 전문
│  └─ ...
└─ houdini_mcp_example       툴 팩 만드는 법을 보여주는 최소 예시
```

이렇게 하면 사용자가 필요한 팩만 설치·제거할 수 있고, 로그의 `category` 가
팩 경계와 일치해 어디서 난 문제인지 바로 드러난다.

**`houdini_mcp_base` 는 예외다.** 어떤 컨텍스트에서 무엇을 하든 쓰이는 것을 모두
담고, 모듈로만 나눈다: `info`, `edit`, `parms`, `geometry`, `viewport`.

지오메트리 조회를 SOP 팩으로 뺐다가 base 로 되돌렸다. `geometry()` 를 가진 노드면
무엇이든 받으므로 DOP 등에서도 필요하기 때문이다. 뷰포트도 마찬가지로, 결과를
눈으로 확인하는 일은 모든 작업에 따라붙는다.

하위 전문 팩은 상위 팩을 `requires` 에 넣는다. 순서 보장이 아니라 존재 보장이
목적이다(2·4번 항목 참고).

**팩마다 반복될 등록 코드는 `houdini_mcp.pack.register_pack()` 으로 뽑았다.**
툴 팩의 `pythonrc.py` 는 팩 이름만 넘기면 되고, import 실패 처리와 로깅은 한
곳에 모인다.

---

## 13. 툴 예외는 ToolError 로 바꿔 올린다

**문제**: 툴이 던진 예외 메시지가 클라이언트에 닿지 않았다. 모델이 보는 것은
`Error executing tool node_info` 뿐이라, 무엇이 잘못됐는지 알 수 없어 스스로
고칠 수 없다.

**원인**: MCP SDK 는 `ToolError` 만 메시지를 실어 보낸다. 다른 예외는 크래시로
보고 툴 이름만 담은 일반 메시지를 돌려준다(`UnexpectedToolError`).

**결정**: `adapter.bind()` 가 툴 예외를 `ToolError` 로 감싸 올린다. 원본 예외와
스택은 이미 우리 로그에 ERROR 로 남으므로 진단 정보는 잃지 않는다.

덕분에 툴이 쓰는 오류 메시지가 그대로 모델에게 간다. 그래서 메시지는 다음에
무엇을 하면 되는지 알려주도록 쓴다:

```
't' 은 벡터 파라미터입니다. 성분 이름으로 거세요: tx, ty, tz
/obj/castle 안에 '존재하지않는타입' 노드를 만들지 못했습니다.
그 네트워크에서 쓸 수 있는 타입인지 확인하세요.
```

---

## 부록: 실측하다 걸린 환경 함정

**`HOUDINI_USER_PREF_DIR` 은 `__HVER__` 없으면 무시된다**

```
EnvControl: HOUDINI_USER_PREF_DIR missing __HVER__, ignored.
```

`.../houdini__HVER__` 형태로 줘야 하고 Houdini 가 `houdini22.0` 으로 치환한다.
무시되면 사용자의 진짜 pref 가 쓰여 테스트 격리가 조용히 샌다.

**셸의 `HOME` 이 pref 디렉토리를 바꾼다**

| 셸 | `$HOUDINI_USER_PREF_DIR` |
|---|---|
| PowerShell | `C:/Users/<user>/Documents/houdini22.0` |
| Git Bash (`HOME` 설정됨) | `C:/Users/<user>/houdini22.0` |

hython 을 Git Bash 에서 돌리면 엉뚱한 위치에 pref 디렉토리가 생긴다. 테스트
하네스는 서브프로세스 환경에서 `HOME` 을 제거한다.
