r"""경로 헬퍼. 툴은 없다 - TOOL_MODULES 에 넣지 않는다.

팩마다 따로 들고 있던 경로 코드를 한곳에 모았다(io, mat, render, hda, lop,
dop, chop, sop, vex, base). 합치면서 Houdini 22.0.368 에서 실측한 규칙이 있다.
어기면 조용히 틀린다 - 예외가 나지 않는다.

## 원문과 전개판을 구분한다

원문(`$HIP/geo/wall.$F4.bgeo.sc`)이 정본이다. 사용자가 준 것이고, 노드
파라미터에 걸 것이며, 씬을 다른 기계로 옮겨도 풀린다. 전개판
(`C:/Users/.../geo/wall.0012.bgeo.sc`)은 파일시스템을 실제로 만지는 순간에만
만든다.

    노드 파라미터, hscript 인자      to_parm(raw)    변수 보존, 슬래시
    모은 파일을 다시 걸 때            portable(raw)   절대 경로면 $HIP/$JOB 으로 접기
    파이썬 파일 조작, HOM 호출        to_path(raw)    전개한 Path
    툴 응답                           describe(raw)   둘 다

## hou.text.expandString (실측)

- `~` 를 Houdini 의 `$HOME` 으로 푼다. **파이썬 Path.home() 과 다를 수 있다** -
  Windows 에서 HOME 환경변수가 없으면(시작 메뉴로 띄운 보통의 경우) Houdini 는
  HOME 을 `Documents` 로 잡는다. 그러니 `.expanduser()` 를 섞어 쓰면 같은 `~`
  가 두 폴더로 갈라진다. 이 모듈 밖에서 expanduser 를 부르지 않는다.
- 예외를 던지지 않는다. **모르는 변수는 조용히 빈 문자열이 된다.**
  `$NOPE/x` 는 `/x` 가 되고, `$HIP/a_$F_b.exr` 은 `$F_b` 를 한 변수로 읽어
  `a_.exr` 이 된다. unresolved_vars 가 이것을 잡는다.
- `$SF` 도 빈 문자열이다. DOP 쿡 안에서만 뜻이 있어 모르는 변수와 구별되지
  않으므로 CONTEXT_VARS 로 뺀다.
- `$F4` 는 현재 프레임으로 굳는다. `<UDIM>` 은 전개하지 않고 둔다.
- **역슬래시를 이스케이프로 읽는다.** `C:\tmp\$F4.exr` 은 `\$` 가 글자 `$` 가
  되어 `C:\tmp$F4.exr` 로, UNC `\\server\share` 는 `\server\share` 로 망가진다.
  그래서 전개하기 전에 os.sep 을 슬래시로 바꾼다.
- `$FPS` `$FSTART` `$FEND` 가 있다. `$F` 로 시작한다고 프레임 토큰으로 보면
  `x.$FPS.txt` 를 시퀀스로 오인한다.

## 원문 `$HIP` 을 그대로 받는가 (실측)

    ROP 파라미터, 슬래시              받는다. mkpath=1 이 디렉토리도 만든다
    ROP 파라미터, 역슬래시            실패한다
    hou.hipFile.save / load          실패한다
    hou.ChopNode.saveClip            예외 없이 아무것도 쓰지 않는다
    hscript chwrite, createDigitalAsset, hda.definitionsInFile   받는다

받는 것도 있지만 받지 않는 것을 외워 둘 수는 없다. HOM 에는 늘 전개판을
넘긴다.

`Path("$HIP/geo")` 는 변수를 모른다. 그대로 mkdir 하면 **현재 디렉토리에
`$HIP` 이라는 폴더가 생긴다.** write_cache 와 write_sim_cache 가 실제로 그랬다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/text.html
"""

from __future__ import annotations

import glob as globmod
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import hou

MAX_SEQUENCE_FILES = 5000
"""시퀀스 하나에서 셀 파일 수 상한. 캐시 디렉토리를 통째로 훑지 않기 위해서."""

MAX_SIBLINGS = 8
"""없는 파일을 알릴 때 보여 줄 같은 디렉토리의 다른 이름 수."""

# --------------------------------------------------------------------------
# 토큰
# --------------------------------------------------------------------------

_WORD_END = r"(?![A-Za-z0-9_])"

FRAME_TOKENS = re.compile(r"\$\{(?:SF|FF|F)\d*\}|\$(?:SF|FF|F)\d*" + _WORD_END)
"""프레임마다 값이 달라지는 변수. `$F` `$F4` `$FF` `$SF` `${F4}`.

뒤에 글자·숫자·밑줄이 이어지면 다른 변수다. Houdini 는 변수 이름을 끝까지
읽는다(실측: `$F_b` 는 한 변수, `$FPS` 는 24).
"""

UDIM_TOKENS = re.compile(r"<UDIM>|<udim>|%\(UDIM\)d")
"""네 자리 타일 번호(1001~)로 풀리는 자리표시자."""

TILE_TOKENS = re.compile(r"<UVTILE>|<uvtile>")
"""`_u1_v1` 모양으로 풀리는 자리표시자. 자릿수가 정해져 있지 않다."""

PRINTF_TOKENS = re.compile(r"%0?\d*d")

SEQUENCE_TOKENS = re.compile(
    "|".join(
        f"(?:{pattern.pattern})"
        for pattern in (UDIM_TOKENS, TILE_TOKENS, FRAME_TOKENS, PRINTF_TOKENS)
    )
)
"""프레임·타일마다 값이 달라지는 토큰 전부. 글롭으로 바꿔 실제 파일을 센다."""

_UDIM_GLOB = "[0-9]" * 4

CONTEXT_VARS = frozenset(
    {"SF", "ST", "SFPS", "TIMESTEP", "SNOBJ", "OBJ", "OBJID", "OBJNAME", "DOPNET"}
)
"""쿡 문맥 안에서만 값이 있는 변수. 밖에서는 빈 문자열이라 모르는 변수와
구별되지 않는다. `$SF` 는 실측했고 나머지는 DOP 로컬 변수 문서를 따랐다."""

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


# --------------------------------------------------------------------------
# 원문 / 전개판
# --------------------------------------------------------------------------


def _normalize(raw: str | Path) -> str:
    """구분자를 슬래시로. 앞뒤 공백을 걷는다.

    expandString 이 역슬래시를 이스케이프로 읽어 경로를 망가뜨리므로(실측)
    전개 전에 반드시 거친다. os.sep 이 슬래시인 플랫폼에서는 아무 일도 없다 -
    거기서는 역슬래시가 파일 이름에 들어갈 수 있는 글자다.
    """
    text = str(raw).strip()
    if os.sep != "/":
        text = text.replace(os.sep, "/")
    return text


def expand(raw: str | Path, frame: float | None = None) -> str:
    """Houdini 변수·백틱 식·`~` 를 푼다. 예외를 던지지 않는다.

    모르는 변수는 빈 문자열이 된다(Houdini 동작 그대로). 그 사실을 알아야 하는
    자리에서는 unresolved_vars 를 함께 본다.

    Args:
        raw: 원문 경로.
        frame: 주면 그 프레임에서 푼다. `$F4` 같은 토큰이 그 프레임 숫자가 된다.
    """
    text = _normalize(raw)
    if not text:
        return ""
    if frame is None:
        return hou.text.expandString(text)
    return hou.text.expandStringAtFrame(text, float(frame))


def to_path(raw: str | Path, frame: float | None = None) -> Path:
    """파일시스템과 HOM 에 넘길 전개판."""
    return Path(expand(raw, frame))


def to_parm(raw: str | Path) -> str:
    """노드 파라미터와 hscript 인자에 넣을 원문. 변수는 그대로, 구분자는 슬래시.

    역슬래시가 든 경로를 ROP 파라미터에 넣으면 쓰기가 실패한다(실측).
    """
    return _normalize(raw)


def collapse(path: str | Path) -> str:
    """전개된 경로를 `$HIP` / `$JOB` 원문으로 되돌린다. 해당하지 않으면 슬래시판.

    hou.text.collapseCommonVars 는 슬래시 경로만 알아본다(실측 - 역슬래시판은
    그대로 돌려준다). 그래서 정규화한 뒤에 넘긴다.
    """
    return hou.text.collapseCommonVars(_normalize(path))


def portable(raw: str | Path) -> str:
    """파라미터에 걸 원문. 변수가 있으면 그대로, 절대 경로면 `$HIP`/`$JOB` 으로 접는다.

    씬을 다른 기계로 옮겨도 풀리게 하려는 것이다. 사용자가 쓴 변수
    (`$MYPROJ/tex`)는 건드리지 않는다 - collapseCommonVars 는 `$HIP`/`$JOB` 만
    알아서, 전개했다가 다시 접으면 그 변수를 잃는다.
    """
    text = to_parm(raw)
    if _VAR.search(text):
        return text
    return collapse(text)


def unresolved_vars(raw: str | Path) -> list[str]:
    """빈 문자열로 풀리는 변수 이름들. 비어 있으면 전부 풀린다.

    `$NOPE/cache/x.bgeo.sc` 는 `/cache/x.bgeo.sc` 로 풀린다. 그대로 쓰면 루트에
    쓴다. 쓰기 전에 이것으로 막는다.
    """
    names: list[str] = []
    for match in _VAR.finditer(_normalize(raw)):
        name = match.group(1) or match.group(2)
        if name in names or name in CONTEXT_VARS:
            continue
        if FRAME_TOKENS.fullmatch(f"${name}"):
            continue
        if hou.text.expandString(f"${name}") == "":
            names.append(name)
    return names


# --------------------------------------------------------------------------
# 시퀀스
# --------------------------------------------------------------------------


def has_sequence_token(raw: str | Path) -> bool:
    return SEQUENCE_TOKENS.search(_normalize(raw)) is not None


def sequence_glob(raw: str | Path) -> str:
    """시퀀스 토큰을 글롭 와일드카드로 바꾼 전개판 패턴.

    토큰 치환이 전개보다 먼저다. 전개를 먼저 하면 `$F4` 가 현재 프레임 숫자로
    굳는다. 토큰 사이 조각만 전개하고 glob.escape 로 감싼다 - 디렉토리 이름에
    `[` 가 있으면 글롭 문자로 읽히기 때문이다. UDIM 은 네 자리 숫자만 맞춘다.
    """
    text = _normalize(raw)
    parts: list[str] = []
    last = 0
    for match in SEQUENCE_TOKENS.finditer(text):
        parts.append(globmod.escape(expand(text[last : match.start()])))
        parts.append(_UDIM_GLOB if UDIM_TOKENS.fullmatch(match.group()) else "*")
        last = match.end()
    parts.append(globmod.escape(expand(text[last:])))
    return "".join(parts)


def resolve_files(
    raw: str | Path, limit: int = MAX_SEQUENCE_FILES
) -> tuple[list[Path], bool]:
    """참조 하나가 실제로 가리키는 파일들과, 시퀀스인지 여부.

    시퀀스가 아니면 파일 하나(없으면 빈 목록). 시퀀스면 글롭으로 실제 있는 것만
    센다 - 없는 프레임이 섞여 있어도 있는 것만 나온다.
    """
    if not has_sequence_token(raw):
        target = to_path(raw)
        return ([target] if target.is_file() else []), False

    found: list[Path] = []
    for hit in globmod.iglob(sequence_glob(raw)):
        path = Path(hit)
        if path.is_file():
            found.append(path)
            if len(found) >= limit:
                break
    return sorted(found), True


# --------------------------------------------------------------------------
# 응답과 검사
# --------------------------------------------------------------------------


def describe(raw: str | Path, frame: float | None = None) -> dict[str, Any]:
    """툴 응답에 넣을 경로 묶음.

    `path` 가 정본이다 - 다음 툴에 넣을 것도, 노드 파라미터에 걸 것도 이것이다.
    `resolved` 는 이 기계에서 실제로 본 자리이고, 파라미터에 다시 꽂으라고 주는
    값이 아니다. 툴 응답에서는 노드 경로와 섞이지 않게 `"file"` 같은 키 아래에
    담는다.
    """
    entry: dict[str, Any] = {"path": to_parm(raw)}
    if frame is None and has_sequence_token(raw):
        files, _ = resolve_files(raw)
        entry["sequence"] = True
        entry["pattern"] = Path(sequence_glob(raw)).as_posix()
        entry["file_count"] = len(files)
        entry["exists"] = bool(files)
    else:
        resolved = to_path(raw, frame)
        entry["resolved"] = resolved.as_posix()
        entry["exists"] = resolved.exists()
    missing_vars = unresolved_vars(raw)
    if missing_vars:
        entry["unresolved"] = missing_vars
    return entry


def file_stat(path: Path) -> dict[str, Any]:
    """존재·크기·수정시각. 없으면 exists=False 만."""
    try:
        info = path.stat()
    except OSError:
        return {"exists": False}
    return {
        "exists": True,
        "bytes": info.st_size,
        "modified": datetime.fromtimestamp(info.st_mtime, timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds"),
    }


def _vars_hint(raw: str | Path) -> str:
    names = unresolved_vars(raw)
    if not names:
        return ""
    listed = ", ".join(f"${name}" for name in names)
    return f" {listed} 가 비어 있어 경로에서 사라졌습니다. 변수 이름을 확인하세요."


def _not_found(raw: str | Path, resolved: Path, subject: str) -> ValueError:
    """subject 는 조사까지 붙인 말이다("파일이", "디렉토리가")."""
    hint = _vars_hint(raw)
    if not hint:
        parent = resolved.parent
        if parent.is_dir():
            siblings = sorted(p.name for p in parent.iterdir())[:MAX_SIBLINGS]
            if siblings:
                hint = f" 같은 디렉토리에 있는 것: {', '.join(siblings)}"
        else:
            hint = f" 디렉토리 자체가 없습니다: {parent.as_posix()}"
    return ValueError(f"그런 {subject} 없습니다: {resolved.as_posix()}.{hint}")


def require_file(raw: str | Path, frame: float | None = None) -> Path:
    """있는 파일의 전개판. 없으면 무엇이 문제인지 알려 준다."""
    resolved = to_path(raw, frame)
    if resolved.is_file():
        return resolved
    if resolved.exists():
        raise ValueError(f"{resolved.as_posix()} 는 파일이 아니라 디렉토리입니다.")
    raise _not_found(raw, resolved, "파일이")


def require_dir(raw: str | Path) -> Path:
    """있는 디렉토리의 전개판."""
    resolved = to_path(raw)
    if resolved.is_dir():
        return resolved
    if resolved.exists():
        raise ValueError(f"{resolved.as_posix()} 는 디렉토리가 아니라 파일입니다.")
    raise _not_found(raw, resolved, "디렉토리가")


def require_resolved(raw: str | Path) -> None:
    """모든 변수가 풀리는지. 쓰기 전에 부른다 - 안 풀리면 엉뚱한 곳에 쓴다."""
    hint = _vars_hint(raw)
    if hint:
        raise ValueError(f"경로를 풀 수 없습니다: {to_parm(raw)}.{hint}")


def require_absent(target: Path, overwrite: bool, what: str = "파일") -> None:
    """이미 있는 것을 말없이 덮어쓰지 않는다. base 의 save_scene 과 같은 규약."""
    if target.exists() and not overwrite:
        raise ValueError(
            f"이미 있는 {what}입니다: {target.as_posix()}. 덮어쓰려면 overwrite=True 를 "
            f"주세요. 남의 작업을 말없이 덮어쓰지 않기 위한 장치입니다."
        )


def prepare_output(
    raw: str | Path, overwrite: bool, frame: float | None = None
) -> Path:
    """출력 경로를 확정하고 부모 디렉토리를 만든다. 전개판을 돌려준다.

    풀리지 않는 변수가 있으면 아무것도 만들기 전에 거절한다.
    """
    require_resolved(raw)
    target = to_path(raw, frame)
    if not target.name:
        raise ValueError(
            f"파일 이름이 없습니다: {to_parm(raw)!r}. 디렉토리가 아니라 파일 경로를 주세요."
        )
    require_absent(target, overwrite)
    ensure_parent(target)
    return target


def ensure_parent(target: Path) -> None:
    """전개판의 부모 디렉토리를 만든다. 원문을 Path 로 만들어 mkdir 하지 않는다."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(
            f"출력 디렉토리를 만들지 못했습니다: {target.parent.as_posix()} ({exc}) "
            f"쓸 수 있는 경로인지 확인하세요."
        ) from exc


def is_inside(child: Path, parent: Path) -> bool:
    """child 가 parent 아래에 있는지. Windows 짧은 이름(PROGRA~1)도 풀어서 본다."""
    try:
        child.resolve().relative_to(parent.resolve())
    except (ValueError, OSError):
        return False
    return True


# --------------------------------------------------------------------------
# $HFS
# --------------------------------------------------------------------------


def hfs_bin(name: str) -> Path | None:
    """`$HFS/bin` 의 실행 파일. 없으면 None.

    shutil.which 가 Windows 의 PATHEXT 를 봐서 `.exe` 를 찾아 준다. 확장자를
    손으로 붙이지 않는다.
    """
    hfs = expand("$HFS")
    if not hfs:
        return None
    found = shutil.which(name, path=str(Path(hfs) / "bin"))
    return Path(found) if found else None


def require_hfs_bin(name: str) -> Path:
    """`$HFS/bin` 의 실행 파일. 없으면 무엇을 확인할지 알려 준다."""
    found = hfs_bin(name)
    if found is None:
        raise RuntimeError(
            f"{name} 을(를) $HFS/bin 에서 찾지 못했습니다 ({expand('$HFS') or '$HFS 없음'}). "
            f"Houdini 설치가 온전한지 확인하세요."
        )
    return found


def run_hfs_tool(
    name: str, args: Sequence[str], timeout: float = 60.0
) -> dict[str, Any]:
    """`$HFS/bin` 의 CLI 를 돌려 결과를 돌려준다. 예외를 던지지 않는다.

    출력은 UTF-8 로 읽는다. 로케일 기본 코덱(한국어 Windows 는 cp949)으로 읽으면
    디코딩에서 깨진다.
    """
    exe = hfs_bin(name)
    if exe is None:
        return {"available": False, "reason": f"$HFS/bin 에 {name} 이 없습니다."}
    try:
        proc = subprocess.run(
            [str(exe), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "ok": False, "error": str(exc)}
    return {
        "available": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr.strip()[:2000],
    }


def env_paths(variable: str) -> list[Path]:
    """`HOUDINI_PATH` 처럼 여러 경로를 담는 변수를 가른다.

    구분자는 플랫폼마다 다르므로 os.pathsep 으로 가른다. `&` 는 Houdini 의
    "기본 경로 자리" 표시라 경로가 아니다.
    """
    raw = hou.text.expandString(f"${variable}")
    return [Path(part) for part in raw.split(os.pathsep) if part and part != "&"]
