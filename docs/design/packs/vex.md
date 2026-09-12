# houdini_mcp_vex — VEX 전문

> 먼저 [README.md](README.md) 를 읽는다. 이 팩은 **제1원칙의 가장 선명한 사례**다.
>
> 구현 완료. 아래는 계획이 아니라 **Houdini 22.0.368 실측 결과**다.

## 무엇을 담나

VEX 코드를 쓰고, **컴파일해 보고**, 진단하는 것.

기존 구현이 가진 것: dcc vex 7 (`create_wrangle`, `validate_vex_syntax`,
`diagnose_wrangle`, `cook_wrangle`, `get_vex_info`, `list_wrangles`,
`update_vex_snippet`), fx `create_wrangle`.

## 기존 구현이 한 방식과 그 한계

`validate_vex_syntax` 를 **노드를 만들고 쿡해서** 구현한다. 그러면:

- 씬이 오염된다 (검증하려고 노드를 만든다)
- 느리다 (쿡은 컴파일보다 훨씬 비싸다)
- 에러 위치가 부정확하다 (쿡 에러는 노드 단위로 뭉개진다)
- 입력 지오메트리가 없으면 검증조차 못 한다

## 우리가 쓰는 경로 — `vcc` 를 직접 부른다

Houdini 는 **VEX 컴파일러를 실행 파일로 갖고 있다.** 기존 구현 다섯 중 이걸
쓰는 곳은 **한 곳도 없다.**

찾는 법은 `shutil.which("vcc", path=$HFS/bin)` 다. Windows 에서는 which 가
PATHEXT 를 봐서 `vcc.exe` 를 찾아 준다 — 확장자를 손으로 붙이지 않는다.

### 실측한 플래그

| 플래그 | 하는 일 |
|---|---|
| `-c <context>` | 컨텍스트 지정 |
| `-o <file>` / `-o stdout` | VEX 라이브러리 출력 |
| `-I <dir>` | include 검색 경로 추가 |
| `-E` | 전처리만. **문법 검사가 아니다** — 틀린 코드도 통과한다 |
| `-X` | 컨텍스트 목록 |
| `--list-context-json=<ctx>` | 전역 변수 + 함수 시그니처를 JSON 으로 |
| `-u <file>` | 다이얼로그 스크립트 출력 |
| `-F` / `-Q` / `-q` | 경고를 에러로 / 경고 억제 / info 억제 |

한 번 컴파일에 **0.36초**. 쿡보다 훨씬 싸다.

### 진단 출력 형식

stderr 로 나온다. 열 번호는 범위로 나오기도 한다.

```
vex:3:2: Error 1088: Syntax error, unexpected identifier, expecting ';'.
vex:1:5-9: Warning 2005: Implicit cast from float to int. Use explicit cast instead.
```

정규식: `^(?P<file>.+?):(\d+):(\d+)(?:-(\d+))?:\s+(Error|Warning|Info)\s+(\d+):\s+(.*)$`
파일 자리에 Windows 경로(`C:\...`)가 와도 non-greedy 로 되짚으면 된다.

문법 에러는 첫 번째에서 멈추지만, 의미 에러(없는 함수, 타입 불일치)는 **여러
개를 한 번에** 낸다.

### 컨텍스트 (`vcc -X`, 10개)

`surface`, `displace`, `light`, `shadow`, `fog`, `chop`, `sop`, `cop2`,
`image3d`, `cvex`

`hou.vexContexts()` 도 10개를 주는데 이름 표기가 다르다(`Displacement` ↔
`displace`). `hou.VexContext` 에는 `name`, `shaderType`, `nodeTypeCategory`,
`pathsToLoadedVexFunctions` 가 있다.

`--list-context-json=sop` 은 전역 15개 + 함수 1,036개를 준다(약 700KB).
컨텍스트당 한 번만 부르고 캐시한다.

### `-u` 로는 ch() 파라미터를 못 뽑는다

계획에는 "파라미터 인터페이스 추출 — wrangle 의 `ch()` 호출에서 스페어 파라미터
유도"라고 적혀 있었지만 **틀렸다.** `-u` 는 컨텍스트 함수의 **시그니처**만
다이얼로그 스크립트로 내보낸다. 스니펫 안의 `chf("scale")` 은 보지 않는다.
그래서 ch() 호출은 우리가 직접 훑는다.

## 가장 큰 걸림돌 — 우리가 받는 것은 VEX 가 아니라 VEXpression 이다

계획서에 없던 것이고, 이 팩에서 가장 손이 많이 간 곳이다.

**둘은 다른 것이다.**

| | 무엇 | 누가 읽나 |
|---|---|---|
| VEX | 언어 자체. `@` 가 없다 | `vcc` 가 컴파일한다 |
| VEXpression | wrangle 스니펫 방언. `@P` 같은 바인딩이 있다 | Snippet VOP 이 CVEX 파라미터로 바꾼다 |

이름을 지어낸 것이 아니다. wrangle 의 `snippet` 파라미터는 Houdini 안에서
**라벨이 그대로 `VEXpression`** 이다(실측 — `attribwrangle`,
`volumewrangle`, `pointwrangle` 셋 다). 모델도 사용자도 "VEX 를 쓴다" 고
말하지만 실제로 손에 쥐는 것은 VEXpression 이다.

그래서 VEXpression 을 vcc 에 그냥 넣으면 안 된다.

```
$ vcc -c sop -o stdout bare.vfl
bare.vfl:1:1: Error 1109: Unknown token '@'
```

`@` 가 잘못된 것이 아니라 **층이 다른 것**이다. `@P` 는 Snippet VOP 이
CVEX 함수 파라미터로 바꿔 주는 설탕이고, vcc 는 그 변환이 끝난 뒤의 VEX 를
받는다. 그 변환을 Houdini 에게 시킬 수도 없다 — `attribwrangle` 안의
`attribvop1` 은 `canGenerateCookCode()` 가 False 라 생성된 코드를 꺼낼 수
없다.

**툴 이름이 `validate_vex` 인 것은 그대로 둔다.** 모델이 찾을 이름이 그쪽
이기 때문이다. 대신 docstring 에서 받는 것이 VEXpression 임을 밝히고,
`source` 모드로 순수 VEX 도 받는다.

그래서 **번역기를 우리가 쓴다**(`snippet.py`). 스니펫을 이렇게 감싼다.

```vex
#line 1 "vex_bindings"
cvex houdini_mcp_vex_check(
        export vector P = {0, 0, 0};
        export vector Cd = {0, 0, 0})
{
#line 1 "vex"
 P.y += 1.0;
 Cd = {1, 0, 0};
}
```

### 줄·열 번호를 지키는 두 장치

1. **`#line` 라벨.** 본문 앞에 `#line 1 "vex"` 를 심으면 진단의 줄 번호가
   사용자 코드 기준으로 나온다. 래퍼가 몇 줄이든 상관없고, 임시 파일 경로가
   모델에게 새지도 않는다. 래퍼 구간은 `vex_bindings` 라벨로 갈라 둬서 우리가
   만든 코드에서 난 에러와 구별한다.
2. **길이를 유지하는 치환.** `v@scale` → `  scale`. 접두사와 `@` 자리를 공백으로
   채우므로 **열 번호까지** 어긋나지 않는다.

실측 확인: 같은 스니펫을 Houdini 의 attribwrangle 로 쿡한 에러 위치 `(4,1)` 과
우리 진단의 `(4, 1)` 이 일치한다.

### `#include` 는 줄을 한 칸씩 민다

전처리기가 include 를 지날 때마다 줄 번호를 1 씩 밀어 놓는다(include 두 개면
두 줄). include 줄 **바로 다음에 `#line` 을 다시 박아** 되돌린다. `#line` 은
물리적인 줄 수와 무관하게 번호를 다시 잡으므로 줄을 끼워 넣어도 사용자 코드의
번호는 그대로다.

### cvex 컨텍스트에서 다 된다

`-c cvex` 로 컴파일하면 SOP·볼륨 함수가 전부 있다. 실측 확인: `npoints`,
`addpoint`, `point`, `setpointattrib`, `nearpoint`, `xyzdist`, `neighbours`,
`removepoint`, `addprim`, `volumesample`, `volumegradient`, `setattrib`,
`pcopen`, `chf`/`chi`/`chv`/`chs`, 배열·dict·matrix 전부.

스니펫 안의 `#include`, `#define`, **함수 정의**도 그대로 통과한다.

바인딩은 읽기만 해도 `export` 로 선언한다. 빼면 `@P.y += 1` 이
`Read-only expression on left side of assignment` 로 잘못 걸린다.

## 타입 추론 — 실측 표

접두사(`@` 앞 한 글자)로 타입이 정해진다. wrangle 이 만든 어트리뷰트의 크기를
읽어 확인했다.

| 접두사 | VEX 타입 | 실측 크기 |
|---|---|---|
| `f@` | float | 1 |
| `i@` | int | 1 (Non-arithmetic) |
| `u@` | vector2 | 2 |
| `v@` | vector | 3 |
| `p@` | vector4 | 4 |
| `2@` | matrix2 | 4 |
| `3@` | matrix3 | 9 |
| `4@` | matrix | 16 |
| `s@` | string | — |
| `d@` | dict | — |

배열은 `f[]@name` 처럼 쓴다.

**접두사가 없으면 입력 지오메트리를 보지 않는다.** 이게 중요하다. 업스트림에
`s@foo` 로 만든 문자열 어트리뷰트가 있어도 하류에서 `@foo = "baz"` 라고 쓰면
Houdini 는 `Invalid assignment from string to float` 를 낸다(실측). 즉 접두사가
없으면 **이름표**를 보고, 표에 없으면 float 다. 우리도 똑같이 한다.

| 이름 | 타입 |
|---|---|
| `P N Cd v up force torque center rest uv scale accel` | vector |
| `orient rot backtrack` | vector4 |
| `id nextid pstate ptnum numpt primnum numprim vtxnum numvtx elemnum numelem ix iy iz resx resy resz` | int |
| `name instance` | string |
| `group_*` | int |
| 그 밖의 전부 (`pivot`, `transform`, `path`, `shop_materialpath` 포함) | float |

접두사 없이 float 로 떨어진 이름은 응답의 `assumed_float` 에 적어 모델에게
알린다. 틀렸으면 `attrib_types={"myvec": "vector"}` 로 바로잡거나 접두사를
붙이면 된다.

## wrangle 노드 타입과 스니펫 파라미터 (실측)

| 카테고리 | 노드 타입 | 파라미터 |
|---|---|---|
| Sop | `attribwrangle`, `pointwrangle`, `volumewrangle`, `deformationwrangle`, `kinefx::rigattribwrangle` | `snippet` |
| Sop | `attribvop`, `attribwranglecore`, `volumevop`, `volumewranglecore` | `vexsnippet` |
| Dop | `popwrangle`, `geometrywrangle`, `gasfieldwrangle` | `snippet` |
| Chop | `channelwrangle` | `snippet` |
| Cop | `wrangle` | `vexsnippet` |
| Lop | `attribwrangle` | `snippet` |
| Vop | `snippet`, `inline` | `code` |

`snippet`/`vexsnippet` 를 이름으로 찾고, VOP 카테고리의 `snippet`/`inline` 만
`code` 를 본다(다른 노드의 `code` 는 VEX 가 아닐 수 있다). `attribwrangle` 의
`class` 파라미터는 0=Detail, 1=Primitives, 2=Points, 3=Vertices 다.

`list_wrangles` 는 `isInsideLockedHDA()` 로 wrangle 내부의 `attribvop1` 을
걸러 낸다.

## 툴

| 툴 | 하는 일 |
|---|---|
| `validate_vex` | `vcc` 로 컴파일만. 줄·열·원문 포함 진단. **노드를 만들지 않는다** |
| `wrangle_attribs` | 읽고 쓰는 어트리뷰트를 정적 분석. 입력 지오메트리와 대조 |
| `create_wrangle` | wrangle 노드 + 코드. **만들기 전에 컴파일을 통과시킨다** |
| `update_wrangle` | 코드 교체. 마찬가지로 먼저 검증. 실패하면 기존 코드를 지킨다 |
| `diagnose_wrangle` | 컴파일 + 쿡 + 어트리뷰트 + ch() 파라미터를 한 번에 |
| `list_wrangles` | 씬의 wrangle 과 코드 요약 |
| `list_vex_contexts` | 컨텍스트와 전역 변수 |
| `vex_function_info` | 함수 시그니처. 이름이 틀리면 비슷한 것을 준다 |

`create_wrangle` 이 검증을 먼저 하는 것이 핵심이다. 모델이 깨진 VEX 를 씬에
남기지 않는다.

### 컴파일러가 잡지 못하는 두 가지

VEX 는 **없는 어트리뷰트를 0 으로 읽고 넘어간다.** `ch()` 가 가리키는 파라미터가
노드에 없어도 0 이다. 둘 다 에러가 아니라서 wrangle 이 조용히 틀린다. 이것이
wrangle 디버깅의 대부분이므로 `wrangle_attribs` 와 `diagnose_wrangle` 이
입력 지오메트리·노드 파라미터와 대조해서 짚어 준다. 기존 구현에는 없다.

## 검증 (전부 통과)

```
틀린 VEX → validate_vex → 줄·열이 Houdini 쿡 에러와 일치
주석·문자열 안의 @ → 바인딩으로 세지 않음
#include 1~2개 → 줄 번호 유지
validate_vex 반복 호출 → /obj 하위 노드 수 불변
깨진 코드 → create_wrangle/update_wrangle 거절, 씬 그대로
없는 어트리뷰트 → wrangle_attribs/diagnose_wrangle 이 경고
```
