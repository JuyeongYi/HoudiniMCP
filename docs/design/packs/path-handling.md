# 핸드오프 — 경로 헬퍼를 base 로 올리고 팩에서 지운다

> 상태: **착수 전.** 이 문서 하나만 읽고 시작할 수 있게 썼다.
> 먼저 [README.md](README.md) 의 다섯 원칙과 프로젝트 `CLAUDE.md` 를 읽는다.

## 왜

팩을 열한 개 만들고 보니 **경로를 푸는 코드가 다섯 팩에 따로 있다.** 이름도
다르고 동작도 다르다. 어느 하나도 필요한 일을 다 하지 못한다.

| 자리 | 이름 | 갖고 있는 것 | 없는 것 |
|---|---|---|---|
| `io/_common.py:93` | `expand` / `to_path` | 실패 관용, 시퀀스 토큰 | 프레임, `~` |
| `mat/common.py:191` | `expand_path` | — | 전부 |
| `render/_common.py:76` | `expand_path(path, frame)` | 프레임 | 실패 관용, `~`, 시퀀스 |
| `hda/_common.py:184,197`, `vcs.py:121` | (인라인) | **`~` (유일)** | 나머지 전부 |
| `lop/composition.py` | (인라인) | — | 전부 |

그래서 `~/out.exr` 은 hda 에서만 열리고 `$F4` 는 render 에서만 맞는다.
합집합이 아니라 각자 자기한테 필요한 조각만 갖고 있다.

`$HFS` 조회도 셋으로 갈라져 있다 — `base/nodetypes.py:165`,
`render/_common.py`, `vex/compiler.py`. vex 는 `vcc`, render 는 `husk`,
io 는 `abcinfo` 를 찾으려고 같은 일을 한다.

전역 `CLAUDE.md` 의 코드 스멜 ② "같은 로직 3곳 복제" 다.

**곁다리로 같이 고칠 것**: `base/nodetypes.py:165` 가
`expandString("$HFS").replace("\\", "/")` 로 구분자를 손으로 바꾼다.
프로젝트 `CLAUDE.md` 의 멀티플랫폼 규칙 위반이다. `Path` 를 쓰면 없어진다.

## 무엇을 만드나

### 1단계 — `houdini_mcp_base/paths.py`

**io 의 `_common.py` 가 이미 거의 완성품이다.** 79~200줄과 370~420줄,
477~490줄이 경로 구역이고, 이것을 base 로 옮기는 것이 작업의 뼈대다.
처음부터 새로 쓰지 않는다.

옮길 것:

```
SEQUENCE_TOKENS      $FF $F\d* <UDIM> <udim> <UVTILE> <uvtile> %(UDIM)d %0?\d*d
MAX_SEQUENCE_FILES   5000
expand               hou.Error 를 잡아 원문 반환
to_path              expand + Path
has_sequence_token
sequence_pattern     토큰을 * 로 바꾼 뒤 전개 (순서가 중요하다, 아래 함정 참고)
resolve_files        참조 하나가 실제로 가리키는 파일들 + 시퀀스 여부
file_stat            존재·크기·수정시각
require_absent       덮어쓰기 방지. base 의 save_scene 과 같은 규약
prepare_output       출력 경로 확정 + 부모 디렉토리 생성
is_inside            경로 포함 관계
hfs_bin              $HFS/bin 의 실행 파일. win32 면 .exe 를 먼저 본다
run_hfs_tool         $HFS/bin CLI 실행
env_paths            os.pathsep 으로 가른다
```

**여기에 두 가지를 더한다** — 지금 어느 한 곳에만 있는 것들이다.

```python
def expand(raw: str, frame: float | None = None) -> str:
    """frame 을 주면 expandStringAtFrame. ~ 도 푼다."""
```

- `frame` — render 의 `expand_path(path, frame)` 에서 가져온다.
  `hou.text.expandStringAtFrame(text, float(frame))`
- `~` — hda 의 `.expanduser()`. `Path(...).expanduser()` 를
  `to_path` 안으로 넣는다

그리고 render 의 `require_file` 도 올린다. 없는 파일일 때 **같은 디렉토리의
다른 파일 이름을 최대 8개 보여 준다** — 프로젝트 `CLAUDE.md` 의 "실패는
다음에 무엇을 할지 알려 준다" 를 가장 잘 지키는 코드라 팩 하나에 두기 아깝다.

**툴이 아니라 헬퍼다. `TOOL_MODULES` 에 넣지 않는다.** `parmtemplate.py` 와
같은 자리다 — `houdini_mcp_base/__init__.py` 의 docstring 에 "툴이 없는
모듈" 절이 이미 있으니 거기 한 줄 더한다.

### 2단계 — 팩에서 지운다

| 팩 | 지울 것 | 바꿀 호출 지점 |
|---|---|---|
| `io` | `_common.py` 의 경로 구역 전체 | 21곳 (`check.py` 1, `deps.py` 6, `export.py` 2, `load.py` 5, `_common.py` 7) |
| `mat` | `common.py:191` `expand_path` | 7곳 (`preset.py` 3, `query.py` 1, `texture.py` 3) |
| `render` | `_common.py:76,90` `expand_path` / `require_file` | 15곳 (`result.py` 8, `run.py` 5, `_usdrender.py` 1, `_common.py` 1) |
| `hda` | 인라인 3곳 | `_common.py:184,197`, `vcs.py:121` |
| `lop` | 인라인 2곳 | `composition.py` |
| `base` | `nodetypes.py:165` 의 `$HFS` + `.replace` | `hfs_bin` 또는 `to_path("$HFS")` |
| `vex` | `compiler.py` 의 `$HFS` 조회 | `hfs_bin("vcc")` |

`.json` 의 `requires` 에 `houdini_mcp_base` 가 있는지 확인한다. 없으면
더한다 — `houdini_mcp_hda.json` 이 이미 그렇게 하고 있으니 본뜬다.

io 의 `_common.py` 는 484줄이고 경로 구역이 빠지면 300줄쯤 된다. 같은 팩의
`export.py` 가 **765줄로 경계에 35줄 남았으니** 이 작업에 얹어 함께 쪼갠다.

### 3단계 — 변수를 살려서 주고받는다

**여기가 이 작업의 본론이다.** 1·2단계는 중복 제거일 뿐이다.

지금 툴들은 경로를 받자마자 전개하고 **전개된 절대 경로를 돌려준다.**
`$HIP/cache/wall.bgeo.sc` 가 `C:/Users/Jooyo/proj/cache/wall.bgeo.sc` 로
나간다. 그러면:

- 모델이 그 값을 다른 툴에 다시 넣을 때 **기계에 박힌 경로**를 넣는다
- 씬을 다른 기계로 옮기면 깨진다. io 의 `remap_paths` 가 하는 일이 정확히
  이것을 `$HIP` 상대로 되돌리는 것이다 — **애초에 안 풀었으면 되돌릴 일도
  없다**
- `hou.fileReferences()` 는 **미전개 문자열**을 준다(io 실측). Houdini
  자신이 변수 형태를 정본으로 들고 있는데 우리만 풀어서 버린다

규칙:

**입력** — `$HIP` / `$JOB` / `$F4` / `<UDIM>` / `~` 를 그대로 받는다.
전개는 파일시스템을 실제로 만지는 순간에만 한다. 경로를 받는 툴의 docstring
에 "변수를 그대로 써도 된다" 를 적는다.

**출력** — 셋을 함께 준다.

```json
{
  "path": "$HIP/cache/wall.bgeo.sc",
  "resolved": "C:/Users/Jooyo/proj/cache/wall.bgeo.sc",
  "exists": true
}
```

`path` 가 정본이고 모델이 다음 툴에 넣을 것이다. `resolved` 는 "내가 실제로
어디를 봤는가" 이지 **파라미터에 다시 꽂으라고 주는 값이 아니다.**
docstring 에 그렇게 적는다.

**노드 파라미터에 걸 때는 미전개판을 쓴다.** 이게 이 작업의 성패다.

이미 `"resolved"` 키를 쓰는 자리가 셋 있다(`io/load.py:213`,
`mat/query.py:162`, `mat/texture.py:413`). 같은 모양으로 맞춘다.

## 함정 — 실측으로 확인된 것

이미 값을 치른 것들이다. 다시 밟지 않는다.

- **`sequence_pattern` 은 토큰 치환이 전개보다 먼저다.** 전개를 먼저 하면
  `$F4` 가 현재 프레임 숫자로 굳는다. io 의 주석에 이유가 적혀 있으니
  옮길 때 주석도 같이 옮긴다.
- **`hou.text.expandStringAtFrame` 은 `$SF` 를 모른다** — 빈 문자열로
  푼다(dop 실측). `$F` 와 `$SF` 가 섞이는 자리는 글롭으로 가야 한다.
  이 차이를 뭉개지 말고 함수로 드러낸다.
- **`<UDIM>` 은 `expandString` 이 전개하지 않고 그대로 둔다**(io 실측).
  `$F4` 와 동작이 다르다. 둘 다 `SEQUENCE_TOKENS` 가 잡는다.
- **Houdini 설치(`$HFS`) 안의 파일은 `hou.fileReferences()` 목록에서 통째로
  빠진다**(io 실측). 의존성 수집이 이것에 기댄다.
- **`hou.hipFile.collisionFreeName` 은 없다**(io 실측).

## 검증

```bash
hython -c "from houdini_mcp import get_registry; import collections; \
  print(collections.Counter(s.package for s in get_registry().all()))"
python -m pytest tests -q
python -m pyflakes houdini_mcp_*/python3.13libs/
wc -l houdini_mcp_*/python3.13libs/houdini_mcp_*/*.py | sort -rn | head
```

기준선: 팩별 툴 수가 **하나도 변하지 않아야 한다.** 이 작업은 리팩토링이고
툴을 더하거나 빼지 않는다. 테스트는 현재 기준선을 유지한다. 800줄 초과 0.

그리고 실제로 돌려 본다.

```
$HIP / $JOB / $F4 / <UDIM> / ~ 를 각각 넣어
→ 전개 결과가 hou.text.expandString 과 같은가
→ 없는 변수를 넣었을 때 예외가 아니라 원문이 오는가
→ 돌려받은 path 를 그대로 다른 툴에 넣어 도는가
→ 노드 파라미터에 걸린 값이 전개판이 아니라 변수 형태인가
```

**마지막 항목이 핵심이다.** 이것이 되면 씬을 다른 기계로 옮길 수 있다.

## 하지 않을 것

- 경로를 다루는 **새 툴**을 만들지 않는다. 헬퍼만 옮긴다
- 전개 규칙을 우리가 새로 정하지 않는다. `hou.text.expandString` 이
  하는 그대로를 따른다 — 진단이 Houdini 와 어긋나면 쓸모가 없다
  (vex 팩이 타입 추론에서 같은 판단을 했다)
- 팩의 `.json` 이름·구조를 건드리지 않는다
