# 경로 헬퍼를 base 로 올렸다

> 상태: **완료 (2026-09-13).** 핸드오프로 시작한 문서다. 작업하면서 실측이
> 핸드오프의 전제를 여럿 뒤집어, 무엇을 했고 무엇이 드러났는지의 기록으로
> 다시 썼다. 경로 코드를 고치기 전에 이 문서와
> `houdini_mcp_base/paths.py` 의 모듈 docstring 을 읽는다.

## 규칙

경로를 다루는 코드는 **`houdini_mcp_base.paths` 에만 있다.** 팩은 자기 경로
헬퍼를 두지 않는다. 툴이 아니라 헬퍼라 `TOOL_MODULES` 에는 없다.

| 할 일 | 쓸 것 |
|---|---|
| 노드 파라미터·hscript 인자에 넣는다 | `to_parm(raw)` — 변수 보존, 슬래시 |
| 파이썬 파일 조작·HOM 호출에 넘긴다 | `to_path(raw)` — 전개한 Path |
| 쓰기 전에 | `require_resolved(raw)`, `prepare_output(raw, overwrite)`, `ensure_parent(path)` |
| 읽기 전에 | `require_file(raw)`, `require_dir(raw)` — 없으면 같은 디렉토리의 이름을 보여 준다 |
| 툴 응답에 싣는다 | `describe(raw)` 를 `"file"` 같은 키 아래에. 전개판은 `.as_posix()` |
| 모은 파일을 다시 건다 | `portable(raw)` — 변수가 있으면 그대로, 절대 경로면 `$HIP`/`$JOB` 으로 접기 |
| 시퀀스·UDIM | `has_sequence_token`, `sequence_glob`, `resolve_files` |
| `$HFS/bin` 실행 파일 | `hfs_bin`, `require_hfs_bin`, `run_hfs_tool` |

하지 않는다:

- 사용자가 준 경로를 `Path(raw)` 로 만들어 파일시스템을 만진다
- `.expanduser()` 를 부른다
- `hou.text.expandString` 을 paths 밖에서 부른다
- 응답이나 파라미터에 `str(Path)` 를 넣는다 — Windows 에서 역슬래시가 된다

## 실측이 핸드오프를 뒤집은 것

| 핸드오프의 전제 | 실측 |
|---|---|
| `~` 는 hda 에서만 풀린다 | `expandString` 이 이미 푼다. 대신 **Houdini 의 `~` 는 `$HOME`** 이고, Windows 에서 HOME 이 없으면 Houdini 가 `Documents` 로 잡아 파이썬 `Path.home()` 과 갈라진다. `.expanduser()` 를 섞으면 같은 `~` 가 두 폴더가 된다 |
| io 의 `expand` 는 실패하면 원문을 돌려준다 | 그 `except` 는 한 번도 안 걸린다. `expandString` 은 예외를 던지지 않고 **모르는 변수를 빈 문자열로 지운다** |
| `nodetypes._origin` 이 `$HFS` 짧은 이름 때문에 틀릴 수 있다 | 아니다. `libraryFilePath()` 도 짧은 이름을 준다. 구분자를 손으로 바꾸던 스타일 위반만 고쳤다 |
| 응답을 `{"path", "resolved", "exists"}` 로 맞춘다 | 이미 많은 툴이 `"path"` 를 노드 경로로 쓴다. `"file": {...}` 처럼 감싼다 |
| 대상은 다섯 팩(io, mat, render, hda, lop) | **열 곳**이었다. base(cache, scene, nodetypes), dop, chop, sop, vex 가 더 있었다 |

## 드러난 조용한 실패

전부 예외 없이 틀리던 것이다. "실측" 은 고치기 전 코드로 증상을 재현한 것,
"코드" 는 코드를 읽어 확인하고 고친 뒤의 동작만 실측한 것이다.

| # | 무엇 | 어디서 | 증상 | 근거 |
|---|---|---|---|---|
| 1 | 원문을 `Path` 로 만들어 mkdir | base `write_cache` | cwd 에 `$HIP\geo` 폴더가 생기고, 파라미터에 역슬래시 경로가 들어가 **굽기가 실패**하고, "쓸 권한을 확인하라" 는 엉뚱한 안내 | 실측 |
| 2 | 같은 것 | dop `write_sim_cache`, `sim_cache_status` | 시뮬은 진짜 `$HIP/sim` 에 써졌는데 가짜 폴더를 뒤져 **`files_written: 0` 과 "디스크 공간을 확인하라"** 는 거짓 보고 | 실측 |
| 3 | 같은 것 | chop `export_channels` 등 4개, `load_audio`, sop `export_attribute` | cwd 에 쓰거나 없는 파일로 판정. `load_audio` 는 docstring 에 "$HIP 을 펼친 절대 경로를 주세요" 라고 우회법을 적어 두었다 | 코드 |
| 4 | `expandString` 이 역슬래시를 이스케이프로 읽는다 | 전개하는 모든 곳 | `C:\tmp\$F4.exr` 는 `C:\tmp$F4.exr`, UNC `\\server\share` 는 `\server\share` | 실측 |
| 5 | 역슬래시 경로를 ROP 파라미터에 | io `export_alembic`·`export_fbx` 의 `str(target)` | ROP 쓰기가 실패한다(Apprentice 라 이 두 툴은 돌려 보지 못했다) | API 실측 + 코드 |
| 6 | `$HIP` 원문을 HOM 에 | base `save_scene`·`load_scene`, chop `export_channels` | `hipFile.save/load` 실패, **`saveClip` 은 예외 없이 아무것도 안 쓴다** | API 실측 + 코드 |
| 7 | 모르는 변수가 빈 문자열 | 쓰는 모든 곳 | `$NOPE/cache/x` 가 `/cache/x` 로 풀려 루트에 쓴다 | 실측 |
| 8 | `$FPS` `$FSTART` 를 프레임 토큰으로 | io `\$F\d*`, dop `\$S?F\d*` 와 `"$F" in pattern` 검사 | `x.$FPS.txt` 를 시퀀스로 오인. Houdini 는 변수 이름을 끝까지 읽는다(`$F_b` 는 한 변수) | 실측 |
| 9 | relink 가 전개된 절대 경로를 파라미터에 | io `collect_dependencies` | 모은 씬을 다른 기계로 옮기면 다시 깨진다 - 모으는 목적이 사라진다 | 코드 |
| 10 | UDIM 을 `*` 로 글롭 | io | `tex.abcd.exr` 까지 타일로 센다. mat 은 네 자리로 맞게 하고 있었다 | 코드 |
| 11 | 디렉토리 이름의 `[` | io, mat, dop | 글롭 문자로 읽힌다 | 코드 |
| 12 | include 디렉토리를 전개하지 않음 | vex `validate_vex(include_dirs=)` | `$HIP/vexinc` 가 안 풀린다 | 코드 |

`$HIP` 을 그대로 받는지는 API 마다 다르다(실측). ROP 파라미터(슬래시)·hscript
`chwrite`·`createDigitalAsset`·`hda.definitionsInFile` 은 받고, ROP 파라미터(역슬래시)·
`hipFile.save/load`·`saveClip` 은 받지 않는다. 외워 둘 수 없으므로 HOM 에는 늘
전개판을 넘긴다.

## 옮긴 자리

| 팩 | 지운 것 | 지금 |
|---|---|---|
| base | `cache` 의 `Path(file_path)`, `scene` 의 `Path(path)`, `nodetypes` 의 구분자 치환 | 파라미터엔 원문, 디렉토리는 전개판으로. 응답에 `"file": describe(...)` |
| io | `_common.py` 의 경로 구역 전체(expand, to_path, 시퀀스, file_stat, prepare_output, is_inside, hfs_bin, run_hfs_tool, env_paths) | `paths` 를 쓴다. relink 는 `portable` |
| mat | `common.expand_path`, `texture` 의 UDIM 토큰·글롭 | `paths.UDIM_TOKENS`, `resolve_files` |
| render | `_common` 의 `expand_path`·`require_file`·`houdini_bin` | `paths.to_path`·`require_file`·`require_hfs_bin`. `houdini_mcp_render.json` 에 base requires 추가 |
| hda | 인라인 `expandString(...).expanduser()` 3곳 | `paths.to_path`, 쓰는 자리는 `require_resolved` |
| lop | 인라인 `expandString` 2곳 | `paths.require_file`, 파라미터엔 `to_parm` |
| dop | `_houdini_path`, `_FRAME_VAR`, `_glob_written`, `expanduser` | `paths.resolve_files`, `FRAME_TOKENS` |
| chop | `Path(file_path)` 5곳 | `require_file`/`prepare`, File CHOP 파라미터엔 원문 |
| sop | `export_attribute` 의 `Path(file_path)` | 원문에서 확장자를 고치고 전개판에 쓴다 |
| vex | `_houdini_bin` 의 `os.environ` 조회, include 의 `Path(directory)` | `paths.hfs_bin`, `require_dir` |

응답에 싣던 `str(Path)` 도 hda·mat·render·io·base 에서 `.as_posix()` 로 바꿨다.

## 함께 한 것

- **`io/export.py` 분해.** 761줄이라 경계에 닿아 있었다. 포맷별로 나눴다 -
  `export.py`(네이티브·`export_formats`, 227) / `usd.py`(324) /
  `interchange.py`(Alembic·FBX, 268). `load.py` 가 가져가던 `_parse_abcinfo` 는
  `interchange.parse_abcinfo` 로 공개했다.
- **테스트 모듈 이름 충돌.** 테스트마다 `tests/<팩>/scenario.py` 를 두는데
  `from scenario import MARKER` 로 읽으면 먼저 수집된 쪽이 `sys.modules` 를
  차지한다. rig 가 한 번 밟고 자기 파일만 고쳤는데, 이번에 추가한
  `tests/paths` 가 같은 방식이라 알파벳 순으로 sop 보다 먼저 수집되며 sop
  17개가 다시 깨졌다. paths 와 sop 둘 다 전용 이름으로 `importlib` 로드한다.

## 검증

- `tests/paths` 32개 신설 — 위 조용한 실패를 하나씩 못 박는다
- 전체 117 passed, 9 skipped
- 등록 툴 이름 277개가 작업 전후 **완전히 같다** — 리팩토링이 툴을 더하거나 빼지 않았다
- 통합 검증 세 묶음(io·sop·chop / dop·lop·vex·hda / mat·render)을 `$HIP` 경로로
  실제 호출. 격리한 현재 디렉토리에 새는 것 0. 주요 확인:
  - `write_cache("$HIP/geo/x")` 가 구워지고 파라미터에 원문이 걸린다
  - `write_sim_cache("$HIP/sim")` 가 `files_written: 3`
  - `collect_dependencies` 가 절대 경로로 걸린 참조까지 `$HIP/collected/...` 로 되돌린다
  - `$HMCP_NOPE/...` 경로는 노드 하나 남기지 않고 거절한다
- `export_usd` 를 HEAD 코드와 현재 코드로 같은 입력에 돌려 결과가 같다

## 이어서 - 파일 참조 툴도 base 로

헬퍼만이 아니라 **파일 참조를 다루는 툴**도 컨텍스트를 가리지 않는다.
io 의 `list_dependencies` / `collect_dependencies` / `remap_paths`(→ base `deps`)
와 `validate_scene`(→ base `portability`)을 옮겼고, mat 의 `list_textures` 는
같은 `hou.fileReferences()` 순회의 이미지판이라 지우고
`list_dependencies(kinds=["Image"])` 로 합쳤다. 툴 277 → 276.

파일 인자를 받더라도 도메인 작업인 툴(export_usd, load_audio, create_hda 등)과,
포맷 지식에 기대는 `probe_file`, 텍스처 캐시인 `reload_textures` 는 팩에 둔다.

## 남은 것

- `houdini_mcp_mat/color.py` 가 `$OCIO` 를 `expandString` 으로 읽는다. 경로를
  만지지 않고 보여 주기만 해서 두었다.
- `houdini_mcp/logs.py` 의 `$HOUDINI_USER_PREF_DIR` 는 서버 패키지라 팩 규칙
  밖이다.
- 테스트의 `_run_scenario` 가 sop·chop·rig·paths 네 곳에 복제돼 있다. 위 충돌도
  이 복제에서 났다. 하네스로 올릴 리팩토링 항목이다.
