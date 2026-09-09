# Houdini 패키지 로드 순서 실측

MCP 서버 패키지와 툴 패키지를 분리하려면 "어느 패키지의 초기화 코드가 언제
실행되는가"가 확정돼야 한다. Houdini 문서는 이 부분을 절반만 규정하고, 나머지는
직접 재현해야 알 수 있다. 이 디렉토리는 그 규칙을 실측하고 회귀 테스트로 고정한다.

측정 환경: Houdini 22.0.368 / Python 3.13 / Windows 11 / Apprentice (2026-09-09)

## 실행

```sh
cd tests/package_order
python -m unittest discover -v          # 시스템 python 으로도 된다
```

hython 을 서브프로세스로 띄우므로 시스템 python 으로 실행해도 된다.
`$HFS` 가 없으면 `C:\Program Files\Side Effects Software` 에서 최신 버전을 찾는다.

실제 사용자 pref 디렉토리(`Documents\houdini22.0\packages`)에 설치해서 검증하는
테스트는 부작용이 있어 기본 비활성이다. 켜려면:

```sh
HMCP_TEST_REAL_PREF=1 python -m unittest test_load_order.RealUserPrefSlotTest
```

테스트가 만든 파일은 `zzhmcptest_` 접두사로 식별해서 반드시 정리한다.

## 실측으로 확정된 규칙

### 1. 처리 순서와 실행 순서는 서로 반대다

```
패키지 처리 순서
  = 디렉토리 스캔순 → (같은 디렉토리 내) process_order 오름차순 → 없으면 파일명 알파벳순
      ↓  hpath 는 기본이 prepend
HOUDINI_PATH = 처리 순서의 역순
      ↓  스크립트는 HOUDINI_PATH 순서로 실행된다
스크립트 실행 순서 = 처리 순서의 역순
```

`process_order: 1` 을 준 패키지는 가장 먼저 처리되지만 `pythonrc.py` 는 가장
나중에 실행된다. 직관과 반대라서 테스트로 못 박아 두었다.

디렉토리 스캔 순서는 다음과 같이 고정돼 있다:

1. `$HOUDINI_USER_PREF_DIR/packages`
2. `$HSITE/houdini<major>.<minor>/packages`
3. `$HOUDINI_PACKAGE_DIR`
4. `$HFS/packages`

`process_order` 는 **같은 디렉토리 안에서만** 유효하다. 패키지를 서로 다른
슬롯에 흩어 놓으면 순서 제어가 무력해진다.

### 2. 훅마다 다중 실행 여부가 다르다

| 훅 | 여러 패키지에 있을 때 | 순서 |
|---|---|---|
| `python3.13libs/pythonrc.py` | **전부 실행** | HOUDINI_PATH 순 |
| `python3.13libs/ready.py` | **전부 실행** | HOUDINI_PATH 순 |
| `python3.13libs/uiready.py` | **전부 실행** | HOUDINI_PATH 순 |
| `scripts/123.py` | **첫 번째 1개만** | — |
| `scripts/456.py` | 미확정 | 씬을 로드할 때만 실행된다 |

`123.py` 는 패키지에서 쓰면 안 된다. HOUDINI_PATH 최상위 하나만 이기고 나머지는
조용히 무시되며, 사용자 개인 `123.py` 까지 덮어친다.

`456.py` 는 씬을 로드할 때마다 재실행되므로 서버 기동에는 부적합하다.

### 3. 단계 간 순서는 보장된다

`pythonrc.py` 가 모든 패키지에서 끝난 뒤에 `ready.py` 가 시작된다. 섞이지 않는다.

### 4. `requires` 는 로드 순서를 보장하지 않는다

| 검증 | 결과 |
|---|---|
| 대상 패키지가 없을 때 | 그 패키지가 **통째로 차단됨** (hpath·훅 전부) |
| 대상이 나중에 처리되는 패키지일 때 | **순서 안 바뀜**, 그리고 **requires 는 통과** |

즉 `requires` 는 "그 JSON 파일이 존재하느냐"만 본다. 대상 패키지가 실제로
로드됐는지, `hpath`/`env` 가 적용됐는지는 전혀 보장하지 않는다. UE 플러그인의
`"Plugins": [...]` 의존성과는 성격이 완전히 다르다.

**설계 함의**: 서버 패키지와 툴 패키지 사이의 순서 의존을 `requires` 로 해결할 수
없다. 대신 순서는 단계 경계(`pythonrc` → `uiready`)에 걸고, `requires` 는
오설치를 조기에 드러내는 용도로만 쓴다.

### 5. `requires` 표기 규칙

툴 패키지가 서버 패키지를 가리킬 때 쓰는 표기를 실측으로 고정했다.

| `requires` 값 | 결과 |
|---|---|
| `["houdini_mcp"]` | **통과** — JSON 파일명에서 확장자를 뺀 이름 |
| `["houdini_mcp.json"]` | 차단 — 확장자를 붙이면 안 된다 |
| `["Houdini_MCP"]` | 차단 — **대소문자를 구분한다** |

디렉토리 슬롯을 넘어서도 찾는다. 툴 패키지가 먼저 스캔되는 슬롯(user pref)에
있고 서버 패키지가 나중 슬롯(`HOUDINI_PACKAGE_DIR`)에 있어도 통과한다. Houdini 가
전체 패키지 파일 목록을 먼저 수집한 뒤 판정하기 때문이다. 따라서 사용자가 서버와
툴 팩을 서로 다른 위치에 설치해도 문제없다.

**서버 패키지의 JSON 파일명이 곧 공개 인터페이스다.** 이름을 바꾸면 모든 툴
패키지가 차단된다.

## 함정: `HOUDINI_USER_PREF_DIR` 과 `__HVER__`

`HOUDINI_USER_PREF_DIR` 은 값에 `__HVER__` 토큰이 없으면 **통째로 무시된다**:

```
EnvControl: HOUDINI_USER_PREF_DIR missing __HVER__, ignored.
```

`.../houdini__HVER__` 형태로 줘야 하고, Houdini 가 이를 `houdini22.0` 으로 치환한다.
무시되면 사용자의 진짜 pref 디렉토리가 쓰이므로 테스트 격리가 조용히 샌다.

## 함정: 셸의 `HOME` 이 pref 디렉토리를 바꾼다

Git Bash 처럼 `HOME` 이 설정된 셸에서 hython 을 돌리면 pref 디렉토리가
`$HOME/houdini22.0` 으로 빗나간다. Windows 정상 경로는
`Documents/houdini22.0` 이다.

| 셸 | `$HOUDINI_USER_PREF_DIR` |
|---|---|
| PowerShell | `C:/Users/<user>/Documents/houdini22.0` |
| Git Bash (`HOME` 설정됨) | `C:/Users/<user>/houdini22.0` |

하네스는 서브프로세스 환경에서 `HOME` 을 제거해 이 차이를 없앤다.

## 구성

| 파일 | 역할 |
|---|---|
| `harness.py` | 임시 패키지 트리 생성, hython 실행, 실행 순서 로그 파싱 |
| `test_load_order.py` | 위 규칙들의 회귀 테스트 |

`PackageLab` 은 세 가지 설치 슬롯을 지원한다:

| 슬롯 | 설치 위치 | 부작용 |
|---|---|---|
| `SLOT_PACKAGE_DIR` | `HOUDINI_PACKAGE_DIR` (스캔 3번) | 없음 |
| `SLOT_USER_PREF` | 샌드박스 pref 의 packages (스캔 1번) | 없음 |
| `SLOT_USER_PREF_REAL` | 사용자의 진짜 pref packages | 있음 — opt-in |

세 슬롯 모두에서 위 규칙이 동일하게 성립하는 것을 확인했다.

`uiready.py` 는 인터랙티브 세션에서만 실행되므로 hython 으로는 검증할 수 없다.
실제 GUI 세션으로 측정한 결과는 다음과 같다:

```
HOUDINI_PATH : [zzhmcptest_c, zzhmcptest_b, zzhmcptest_a, zzhmcptest_watchdog]
pythonrc     -> ['C', 'B', 'A']
ready        -> ['C', 'B', 'A']
uiready      -> ['C', 'B', 'A']      # pythonrc 와 동일한 순서
123          -> ['C']                # 하나만
456          -> (실행 안 됨)
```

즉 `uiready.py` 는 `pythonrc`/`ready` 와 같은 그룹이다 — 전부 실행되고, 순서도
HOUDINI_PATH 순으로 동일하다. **서버 기동 훅으로 쓸 수 있다.**

## 미검증 항목

- `456.py` 의 다중 실행 여부 — 새 씬으로 시작하면 `123.py` 만 돌고 `456.py` 는
  돌지 않는다. hython 에서 `hou.hipFile.load()` 로도 트리거되지 않았다. 씬 로드
  때마다 재실행되는 훅이라 서버 기동에는 어차피 부적합해서 우선순위가 낮다.
