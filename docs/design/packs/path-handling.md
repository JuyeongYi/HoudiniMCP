# 경로 다루기를 한 곳으로 모은다

> 상태: **미결.** 아직 고치지 않았다. 팩 구현이 끝나가면서 드러난 것이고,
> 다음 작업 묶음에서 처리한다.

팩을 열한 개 만들고 보니 **경로를 푸는 코드가 팩마다 따로 있다.** 이름도
다르고 동작도 다르다. 어느 것도 필요한 일을 다 하지 못한다.

## 지금 있는 것 (실측, 2026-09-13)

| 자리 | 이름 | 하는 일 |
|---|---|---|
| `houdini_mcp_io/_common.py:93` | `expand` / `to_path` | `hou.Error` 를 잡아 **원문을 그대로 돌려준다**. 시퀀스 토큰(`$F`, `<UDIM>`)을 따로 안다 |
| `houdini_mcp_mat/common.py:191` | `expand_path` | `Path(expandString(raw))`. 그뿐 |
| `houdini_mcp_render/_common.py:76` | `expand_path(path, frame)` | `frame` 을 주면 `expandStringAtFrame`. 렌더 출력 경로가 거의 항상 변수를 담기 때문 |
| `houdini_mcp_hda/_common.py`, `vcs.py` | (인라인) | `Path(expandString(...)).expanduser()` — **`~` 를 푸는 유일한 자리** |
| `houdini_mcp_lop/composition.py` | (인라인) | `Path(expandString(file_path))` |

`$HFS` 를 찾는 코드도 셋으로 갈라져 있다 —
`houdini_mcp_base/nodetypes.py`, `houdini_mcp_render/_common.py`,
`houdini_mcp_vex/compiler.py`. vex 는 `vcc`, render 는 `husk` 를 찾으려고
같은 일을 한다.

**어느 하나도 네 가지를 다 하지 않는다**: 실패 관용 · 프레임 · `~` 전개 ·
시퀀스 토큰 인식. 합집합이 아니라 각자 자기한테 필요한 조각만 갖고 있고,
그래서 `~/out.exr` 은 hda 에서만 열리고 `$F4` 는 render 에서만 맞는다.

전역 `CLAUDE.md` 의 코드 스멜 ② "같은 로직 3곳 복제" 에 걸린다.

## 두 갈래로 고친다

### 1. 헬퍼를 base 로 올린다

경로 전개는 렌더 기능도 머티리얼 기능도 아니다. **어떤 컨텍스트에서 무엇을
하든 쓰인다** — 프로젝트 `CLAUDE.md` 가 말하는 `houdini_mcp_base` 의 기준
그대로다.

base 에 둘 것은 위 다섯의 **합집합**이다.

```python
expand(raw, frame=None)     # 변수·백틱 식·~ 를 푼다. 실패하면 원문
to_path(raw, frame=None)    # 위 + Path
has_sequence_token(raw)     # $F / $SF / <UDIM> 이 들어 있나
sequence_pattern(raw)       # 시퀀스 토큰을 * 로 바꾼 글롭 패턴
hfs_bin(name)               # $HFS/bin/<name> — vcc, husk, abcinfo, hotl
```

`hfs_bin` 은 셋으로 갈라진 `$HFS` 조회를 합친다. Windows 에서 `.exe` 가
붙는 것도 한 곳에서만 알면 된다.

**주의**: `hou.text.expandStringAtFrame` 은 `$SF` 를 모른다(빈 문자열로
푼다 — dop 이 실측). `$F` 와 `$SF` 를 같이 다루는 자리는 글롭으로 가야
한다. 합칠 때 이 차이를 없애지 말고 함수로 드러낸다.

### 2. 더 중요한 것 — **변수를 살려서 주고받는다**

지금 툴들은 경로를 받자마자 전개하고, 전개된 절대 경로를 돌려준다.
`$HIP/cache/wall.bgeo.sc` 가 `C:/Users/.../cache/wall.bgeo.sc` 가 되어
나간다. 그러면:

- 모델이 그 값을 다시 다른 툴에 넣을 때 **기계에 박힌 경로**를 넣게 된다
- 씬을 다른 기계로 옮기면 깨진다. `houdini_mcp_io` 의 `remap_paths` 가
  하는 일이 정확히 이걸 되돌리는 것이다 — 애초에 만들지 않았으면 되돌릴
  일도 없다
- `hou.fileReferences()` 는 **미전개 문자열**을 준다(io 실측). Houdini
  자신이 변수 형태를 정본으로 들고 있는데 우리만 풀어서 버린다

그래서 규칙을 세운다.

**입력**: `$HIP` / `$JOB` / `$F4` / `<UDIM>` / `~` 를 **그대로 받는다.**
전개는 파일시스템을 실제로 만질 때만, 그 순간에만 한다.

**출력**: 둘 다 준다.

```json
{
  "path": "$HIP/cache/wall.bgeo.sc",
  "resolved": "C:/Users/Jooyo/proj/cache/wall.bgeo.sc",
  "exists": true
}
```

`path` 가 정본이다. 모델이 다음 툴에 넣을 것은 이쪽이다. `resolved` 는
"내가 실제로 어디를 봤는가" 를 보여 주는 것이고, 파라미터에 다시 꽂으라고
주는 값이 아니다. docstring 에 그렇게 적는다.

**노드 파라미터에 쓸 때는 미전개판을 쓴다.** 이미 `io.remap_paths` 가
`$HIP` 상대로 되돌리는 일을 하고 있고, 애초에 변수 형태로 걸면 그 툴이
필요 없어지는 자리가 많다.

## 할 일

1. base 에 `paths` 모듈을 만들고 위 합집합을 넣는다. 툴이 아니라 헬퍼이므로
   `TOOL_MODULES` 에 넣지 않는다 — `parmtemplate.py` 와 같은 자리다
2. 다섯 팩의 자체 헬퍼를 지우고 base 것을 쓴다
3. 경로를 돌려주는 툴의 반환을 `path` / `resolved` / `exists` 로 맞춘다
4. 경로를 받는 툴의 docstring 에 "변수를 그대로 써도 된다" 를 적는다
5. `$HFS` 조회 셋을 `hfs_bin` 으로 합친다

2·3 은 팩 코드를 함께 고쳐야 하므로 팩 구현이 전부 끝난 뒤에 한 묶음으로
한다. 지금 하면 동시에 돌던 구현과 충돌한다.

## 검증

```
경로에 $HIP / $JOB / $F4 / <UDIM> / ~ 를 각각 넣어
→ 전개 결과가 hou.text.expandString 과 같은가
→ 없는 변수를 넣었을 때 예외가 아니라 원문이 오는가
→ 돌려준 path 를 그대로 다시 다른 툴에 넣어 도는가
→ 노드 파라미터에 걸린 값이 전개판이 아니라 변수 형태인가
```

마지막 항목이 핵심이다. 이것이 되면 씬을 다른 기계로 옮길 수 있다.
