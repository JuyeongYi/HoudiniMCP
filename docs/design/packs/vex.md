# houdini_mcp_vex — VEX 전문

> 먼저 [README.md](README.md) 를 읽는다. 이 팩은 **제1원칙의 가장 선명한 사례**다.

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

## 우리가 쓸 경로 — `vcc` 를 직접 부른다

Houdini 는 **VEX 컴파일러를 실행 파일로 갖고 있다.** 실측 확인:

```
$HFS/bin/vcc.exe
```

기존 구현 다섯 중 이걸 쓰는 곳은 **한 곳도 없다.**

```python
import subprocess
from pathlib import Path
import hou

vcc = Path(hou.text.expandString("$HFS")) / "bin" / "vcc"   # 확장자는 붙이지 않는다
# Windows 에서는 vcc.exe 를 찾아야 한다. shutil.which 로 해결한다.
```

`vcc` 가 주는 것:

- 문법 에러를 **줄·열 번호**와 함께 준다. 노드 없이, 씬 오염 없이.
- 컨텍스트별 검증 (`-c sop`, `-c cop`, `-c surface` …)
- 함수 시그니처 덤프 — 어떤 VEX 함수가 있고 인자가 무엇인지
- 파라미터 인터페이스 추출 — wrangle 의 `ch()` 호출에서 스페어 파라미터 유도

**먼저 `vcc --help` 를 실행해 22.0 의 실제 플래그를 확인한다.** 플래그를
추측해서 쓰지 않는다.

```bash
"$HFS/bin/vcc" --help
```

`hou.vexContexts()` 도 있다(실측 확인). 컨텍스트 목록과 각 컨텍스트가 받는
전역 변수를 여기서 얻는다.

## 툴 초안

| 툴 | 하는 일 |
|---|---|
| `validate_vex` | `vcc` 로 컴파일만. 줄·열 포함 에러 목록. **노드를 만들지 않는다** |
| `vex_function_info` | VEX 함수 시그니처. `vcc` 덤프 또는 `$HFS/houdini/vex/include` 파싱 |
| `list_vex_contexts` | `hou.vexContexts()`. 컨텍스트별 전역 변수 |
| `create_wrangle` | wrangle 노드 + 코드. **만들기 전에 `validate_vex` 를 통과시킨다** |
| `update_wrangle` | 코드 교체. 마찬가지로 먼저 검증 |
| `diagnose_wrangle` | 쿡 에러 + 컴파일 에러 + 참조하는 어트리뷰트가 실제로 있는지 |
| `list_wrangles` | 씬의 wrangle 과 코드 요약 |
| `wrangle_attribs` | 코드가 읽고 쓰는 어트리뷰트를 정적 분석. 입력에 있는지 대조 |

`create_wrangle` 이 검증을 먼저 하는 것이 핵심이다. 모델이 깨진 VEX 를 씬에
남기지 않는다.

## 먼저 확인할 것

1. `vcc --help` 전체 플래그 — 특히 에러 포맷과 JSON 출력 지원 여부
2. Windows 에서 `vcc.exe` 를 어떻게 찾을지 — `shutil.which` 는 PATH 에
   `$HFS/bin` 이 있어야 한다. 없으면 `pathlib` 로 직접 찾는다
3. `hou.vexContexts()` 가 돌려주는 것의 구조
4. wrangle 노드 타입별 snippet 파라미터 이름 (`snippet`, `vexpression` 등이
   노드마다 다르다)

## 검증

```
문법 틀린 VEX → validate_vex → 줄 번호가 정확한가
문법 맞는 VEX → create_wrangle → 노드 생성 + 쿡 성공
없는 어트리뷰트 참조 → wrangle_attribs → 경고
```

씬에 노드가 남지 않는 것도 확인한다 — `validate_vex` 호출 전후로
`len(hou.node("/obj").allSubChildren())` 이 같아야 한다.
