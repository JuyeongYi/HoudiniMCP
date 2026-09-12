# 툴 팩 구현 계획

기존 MCP 구현 다섯(fxhoudinimcp, dcc-mcp-houdini, oculairmedia, capoomgit, eliiik)의
툴을 정규화해 **463개 유니크**를 뽑았다. 그중 `houdini_mcp_base` 로 덮이는 것은
62개다. 나머지를 도메인별 팩으로 나눈 것이 이 디렉토리의 문서들이다.

팩 목록과 상세는 [팩 인덱스](#팩-인덱스)를 본다. 먼저 **모든 팩에 공통으로
적용되는 원칙**을 읽는다. 이것이 이 프로젝트가 기존 구현과 갈라지는 지점이다.

---

## 제1원칙 — 기존 구현을 베끼지 않는다

조사한 다섯 구현의 툴 목록은 **무엇이 필요한지를 알려 주는 요구사항 명세**이지,
**어떻게 만들지에 대한 설계**가 아니다. 목록은 참고하되 구현은 처음부터 다시
생각한다.

### 기존 구현의 공통 한계

다섯 모두 거의 같은 패턴에 머물러 있다.

```python
# 기존 구현들이 하는 것 — HOM 의 가장 얕은 층만 쓴다
node = parent.createNode("bevel")
node.parm("offset").set(0.1)
return {"path": node.path()}
```

이 방식의 문제는 세 가지다.

1. **정보가 아니라 조작만 한다.** 만들고 나서 그게 맞는지 모른다. 결과를
   확인하려면 모델이 다시 물어봐야 하고, 왕복이 늘수록 품질이 떨어진다.
2. **느리다.** 점 10만 개를 돌려줄 때 `for pt in geo.points()` 로 파이썬 루프를
   돈다. Houdini 는 배열을 통째로 넘기는 경로를 따로 갖고 있는데 쓰지 않는다.
3. **Houdini 가 이미 가진 전문 API를 놓친다.** USD 를 다루면서 `pxr` 를 안 쓰고
   LOP 파라미터만 긁고, VEX 를 검증하면서 컴파일러(`vcc`)를 안 쓰고 노드를
   쿡해 본다. 쓸 수 있는 도구가 있는데 우회한다.

### 우리가 하는 것

**먼저 그 도메인의 파이썬 라이브러리를 찾는다.** 툴을 쓰기 전에 조사한다.
Houdini 22.0.368 에 무엇이 번들돼 있는지는 실측해 두었다.

| 모듈 | 버전 | 어디에 쓰나 |
|---|---|---|
| `numpy` | 2.3.2 | 지오메트리·CHOP 대량 데이터 |
| `pxr` (OpenUSD) | 0.26.5 | LOP 스테이지를 노드가 아니라 USD 로 질의 |
| `pdg` | 번들 | TOP 그래프·워크아이템을 직접 |
| `apex` | 번들 | 리그 그래프 (2,286개 콜백) |
| `MaterialX` | 1.39.5 | 셰이더 그래프 검증·상호운용 |
| `OpenImageIO` | 2.5.18.0 | 렌더 결과·텍스처를 읽어서 확인 |
| `husd`, `loptoolutils` | 번들 | SideFX 자체 LOP 헬퍼 |
| `soptoolutils` 등 | 번들 | 셸프 툴이 쓰는 검증된 조립 로직 |
| `PySide6` | 6.8.3 | UI 가 필요한 곳 (주의: hython 에 `hou.ui` 없음) |

실행 파일도 있다: `vcc`(VEX 컴파일러), `husk`(USD 렌더), `hotl`(HDA 조작),
`gplay`. `$HFS/bin` 에서 찾는다 — **경로를 하드코딩하지 않고
`hou.text.expandString("$HFS")` 와 `pathlib` 로 얻는다.**

없는 것도 실측했다: `scipy` 없음, `alembic` 파이썬 바인딩 없음,
`kinefx` 는 import 는 되지만 비어 있음(실제 API는 `apex` 에 있다).

### 조사 없이 구현을 시작하지 않는다

팩을 맡으면 **먼저 그 도메인의 API를 hython 으로 실측한다.** 문서의 API 설명은
2026-09-13 기준 실측이지만, 세부 시그니처까지는 확인하지 않았다. 추측으로
코드를 쓰지 말고 `dir()` 과 `help()` 로 확인한다.

```bash
"$HFS/bin/hython" -c "import hou; print([a for a in dir(hou.LopNode) if 'stage' in a])"
```

공식 문서: <https://www.sidefx.com/docs/houdini/hom/index.html>

---

## 제2원칙 — 툴은 결과를 돌려준다

조작만 하고 `{"ok": true}` 를 돌려주는 툴을 만들지 않는다. 모델이 다음 판단을
할 수 있는 정보를 함께 준다.

```python
# 나쁘다 — 이게 잘 됐는지 모델이 알 수 없다
return {"path": node.path()}

# 좋다 — 결과를 보고 다음을 정할 수 있다
return {
    "path": node.path(),
    "points": len(geo.points()),
    "prims": len(geo.prims()),
    "bbox": [...],
    "warnings": node.warnings(),
}
```

성을 만들다가 원뿔이 뒤집힌 것을 뷰포트 캡처로만 겨우 잡아낸 적이 있다.
툴이 값을 돌려줬으면 바로 알았을 것이다.

## 제3원칙 — 대량 데이터는 벌크 경로로

파이썬 루프로 점을 돌지 않는다. Houdini 는 배열 경로를 따로 제공한다.

```python
# 나쁘다 — 점 10만 개에 수 초가 걸린다
values = [pt.attribValue("P") for pt in geo.points()]

# 좋다 — C++ 쪽에서 한 번에 넘어온다
values = geo.pointFloatAttribValues("P")          # tuple
arr = numpy.array(values, dtype=numpy.float32).reshape(-1, 3)
```

`pointFloatAttribValuesAsString` 계열은 바이트로 받아 `numpy.frombuffer` 로
꽂을 수 있다. MCP 응답으로 나갈 때는 **요약해서 보낸다** — 모델에게 점 10만 개를
그대로 보내면 컨텍스트만 태운다. 통계·샘플·히스토그램으로 압축하고, 원본이
필요하면 파일로 쓰고 경로를 돌려준다.

## 제4원칙 — 저장소 규칙을 그대로 따른다

`CLAUDE.md` 가 전부 적용된다. 요약하면:

- **멀티플랫폼**: 경로는 `pathlib`, 구분자는 `os.sep`/`os.pathsep`. 하드코딩 금지.
- **`@undoable`**: 씬을 바꾸는 툴은 전부. `@tool()` 아래에 놓는다.
- **코멘트 강제**: 노드를 만드는 툴은 `comment` 를 기본값 없는 인자로 둔다.
  노드를 읽어 돌려주는 툴은 `comment` 를 포함한다.
- **영어 문자열**: 노드 이름·코멘트·undo 레이블은 영어. 코드 주석과 docstring 은
  한국어.
- **에러 메시지는 다음 할 일을 알려 준다**: "잘못됐다"로 끝내지 않는다.
- **팩은 서버 없이도 Houdini 를 막지 않는다**: `pythonrc.py` 는
  `except Exception`, `__init__.py` 는 `TOOL_MODULES` 선언만.
- **파일 크기**: 모듈 하나가 800줄을 넘으면 쪼갠다.

팩 하나를 만드는 데 필요한 파일은 넷뿐이다. `houdini_mcp_example` 을 베껴
시작한다.

```
houdini_mcp_<도메인>.json
houdini_mcp_<도메인>/python3.13libs/pythonrc.py
houdini_mcp_<도메인>/python3.13libs/houdini_mcp_<도메인>/__init__.py
houdini_mcp_<도메인>/python3.13libs/houdini_mcp_<도메인>/<모듈>.py
```

## 제5원칙 — 실측으로 검증한다

구현이 끝나면 hython 으로 확인한다. "될 것이다"로 끝내지 않는다.

```bash
hython -c "from houdini_mcp import get_registry; print(len(get_registry()))"
```

최소한 다음을 확인한다.

1. 모든 툴이 등록되는가 (`get_registry().names()`)
2. 대표 툴이 실제로 동작하는가 — 빈 씬에서 만들고, 쿡하고, 값을 읽는다
3. 서버 패키지가 없을 때 Houdini 가 뜨는가 (`pythonrc.py` 보호회로)
4. `python -m pytest tests/package_order -q` 가 통과하는가

---

## 팩 인덱스

우선순위는 "우리가 실제로 막혔던 순서"다. 성을 만들면서 부족했던 것이 위로 온다.

| 순위 | 팩 | 문서 | 툴 수(초안) | 핵심 라이브러리 |
|---|---|---|---|---|
| 1 | `houdini_mcp_sop` | [sop.md](sop.md) | ~30 | `numpy`, `soptoolutils` |
| 2 | `houdini_mcp_vex` | [vex.md](vex.md) | ~8 | `vcc` 컴파일러 |
| 3 | `houdini_mcp_mat` | [mat.md](mat.md) | ~20 | `MaterialX`, `UsdShade` |
| 4 | `houdini_mcp_lop` | [lop.md](lop.md) | ~22 | `pxr`, `husd` |
| 5 | `houdini_mcp_render` | [render.md](render.md) | ~18 | `husk`, `OpenImageIO` |
| 6 | `houdini_mcp_dop` | [dop.md](dop.md) | ~16 | `doptoolutils` |
| 7 | `houdini_mcp_hda` | [hda.md](hda.md) | ~16 | `hou.HDADefinition`, `hotl` |
| 8 | `houdini_mcp_io` | [io.md](io.md) | ~12 | `pxr`, `hou.fileReferences` |
| 9 | `houdini_mcp_chop` | [chop.md](chop.md) | ~14 | `numpy`, `hou.Track` |
| 10 | `houdini_mcp_rig` | [rig.md](rig.md) | ~18 | `apex` |
| 11 | `houdini_mcp_top` | [top.md](top.md) | ~14 | `pdg` |

`houdini_mcp_base` 에 남은 결핍 86개는 팩이 아니라 base 확장이다.
[base-gaps.md](base-gaps.md) 를 본다.

### 미결 항목

구현하면서 드러난 것들이다. 팩 하나의 문제가 아니라 여러 팩에 걸쳐 있어
따로 적어 둔다.

| 문서 | 무엇 |
|---|---|
| [base-gaps.md](base-gaps.md) | base 에 있어야 하는데 없는 툴들 |
| [path-handling.md](path-handling.md) | 경로 전개가 팩마다 따로 있다. 그리고 변수(`$HIP`)를 살려서 주고받아야 한다 |

## 범위 밖

의도적으로 만들지 않는 것들이다. 기존 구현에 있지만 우리 것이 아니다.

| 무엇 | 왜 안 하나 |
|---|---|
| GSplat 릴라이팅 (4) | 특정 워크플로 전용. 범용성이 없다 |
| OPUS 에셋 생성 (6) | 외부 SaaS 연동. MCP 서버를 따로 두는 게 맞다 |
| 스튜디오 파이프라인 (11) | 샷/에셋 명명 규칙이 스튜디오마다 다르다 |
| 원격 디버깅 (`start_debugpy` 등, 8) | 개발자용. MCP 툴로 노출할 이유가 없다 |
