"""vcc — Houdini 가 실행 파일로 들고 있는 VEX 컴파일러.

기존 MCP 구현들은 VEX 를 검증하려고 wrangle 노드를 만들어 쿡한다. 씬이
오염되고, 쿡은 컴파일보다 훨씬 비싸고, 에러가 노드 단위로 뭉개진다. Houdini 는
컴파일러를 `$HFS/bin/vcc` 에 그대로 갖고 있으므로 그걸 부르면 된다.

Houdini 22.0.368 에서 실측한 것:

    vcc -c <context> -o <out> <src.vfl>     컴파일. 진단은 stderr 로 나온다.
    vcc -X                                  컨텍스트 목록
    vcc --list-context-json=<context>       전역 변수 + 함수 시그니처 (JSON)
    vcc -I <dir>                            include 검색 경로 추가
    vcc -u <file>                           다이얼로그 스크립트 출력

진단 한 줄의 형식은 이렇다. 열 번호는 범위로 나오기도 한다.

    vex:3:2: Error 1088: Syntax error, unexpected identifier, expecting ';'.
    vex:1:5-9: Warning 2005: Implicit cast from float to int.

맨 앞의 `vex` 는 파일 이름이 아니라 우리가 소스에 심어 둔 `#line` 라벨이다.
덕분에 임시 파일 경로가 새지 않고, 줄 번호가 사용자가 준 코드 기준 그대로
나온다.

한 번 컴파일에 0.4초 정도 걸린다(실측). 쿡보다 훨씬 싸다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TIMEOUT = 60
"""vcc 한 번에 허용할 시간(초)."""

USER_LABEL = "vex"
"""사용자 코드 구간에 심는 #line 라벨. 진단의 파일 자리에 그대로 나온다."""

BINDING_LABEL = "vex_bindings"
"""우리가 생성한 래퍼 구간의 라벨. 여기서 난 진단은 사용자 코드 탓이 아니다."""

SCOPE_CODE = "code"
SCOPE_BINDINGS = "bindings"
SCOPE_COMPILER = "compiler"

_DIAGNOSTIC = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+)(?:-(?P<end_column>\d+))?:\s+"
    r"(?P<severity>Error|Warning|Info)\s+(?P<code>\d+):\s+(?P<message>.*)$"
)
"""진단 한 줄. 파일 자리에 Windows 경로(C:\\...)가 와도 non-greedy 로 되짚는다."""

_vcc_path: Path | None = None
_contexts: tuple[str, ...] | None = None
_context_json: dict[str, dict[str, Any]] = {}


# ---- vcc 찾기 ---------------------------------------------------------


def _houdini_bin() -> Path:
    """$HFS/bin. 경로를 하드코딩하지 않고 환경에서 얻는다."""
    hfs = os.environ.get("HFS")
    if not hfs:
        # Houdini 안이면 환경변수가 늘 있지만, 없더라도 hou 로 한 번 더 본다.
        import hou

        hfs = hou.text.expandString("$HFS")
    if not hfs:
        raise RuntimeError(
            "$HFS 를 찾지 못했습니다. Houdini 설치 경로를 알 수 없으면 VEX 를 "
            "컴파일할 수 없습니다. HFS 환경변수를 설정한 뒤 Houdini 를 다시 "
            "띄우세요."
        )
    return Path(hfs) / "bin"


def vcc_path() -> Path:
    """vcc 실행 파일 경로. 확장자는 플랫폼이 정하게 둔다.

    shutil.which 는 Windows 에서 PATHEXT 를 봐서 vcc.exe 를 찾아 준다. 그래서
    ".exe" 를 손으로 붙이지 않는다.
    """
    global _vcc_path
    if _vcc_path is not None:
        return _vcc_path

    bindir = _houdini_bin()
    found = shutil.which("vcc", path=str(bindir)) or shutil.which("vcc")
    if found is None:
        raise RuntimeError(
            f"VEX 컴파일러(vcc)를 {bindir} 에서도 PATH 에서도 찾지 못했습니다. "
            f"Houdini 설치가 온전한지 확인하세요."
        )
    _vcc_path = Path(found)
    return _vcc_path


def _spawn_options() -> dict[str, Any]:
    """자식 프로세스 생성 옵션."""
    if sys.platform == "win32":
        # Windows 에서 vcc 를 부를 때마다 콘솔 창이 깜빡이지 않게 한다.
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def run_vcc(args: list[str], *, timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    """vcc 를 부르고 결과를 그대로 돌려준다."""
    command = [str(vcc_path()), *args]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **_spawn_options(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"vcc 가 {timeout}초 안에 끝나지 않았습니다. 코드가 지나치게 크거나 "
            f"include 가 서로를 물고 있는지 보세요."
        ) from exc


# ---- 진단 파싱 --------------------------------------------------------


def parse_diagnostics(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """vcc 출력에서 진단을 뽑는다. (진단, 형식이 다른 나머지 줄)."""
    diagnostics: list[dict[str, Any]] = []
    notes: list[str] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        match = _DIAGNOSTIC.match(line)
        if match is None:
            notes.append(line)
            continue
        origin = match.group("file")
        if origin == USER_LABEL:
            scope = SCOPE_CODE
        elif origin == BINDING_LABEL:
            scope = SCOPE_BINDINGS
        else:
            scope = SCOPE_COMPILER
        end_column = match.group("end_column")
        diagnostics.append(
            {
                "severity": match.group("severity").lower(),
                "code": int(match.group("code")),
                "line": int(match.group("line")),
                "column": int(match.group("column")),
                "end_column": int(end_column) if end_column else None,
                "message": match.group("message"),
                "scope": scope,
            }
        )
    return diagnostics, notes


def attach_source(diagnostics: list[dict[str, Any]], code: str) -> None:
    """사용자 코드에서 난 진단에 그 줄의 원문을 붙인다.

    줄 번호만 주면 모델이 다시 코드를 세어 봐야 한다. 원문을 같이 주면 바로
    고칠 수 있다.
    """
    lines = code.splitlines()
    for diagnostic in diagnostics:
        if diagnostic.get("scope") != SCOPE_CODE:
            continue
        index = diagnostic["line"] - 1
        if 0 <= index < len(lines):
            diagnostic["source"] = lines[index]


# ---- 컴파일 -----------------------------------------------------------


def compile_source(
    source: str,
    *,
    context: str = "cvex",
    include_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """VEX 소스 한 덩어리를 컴파일한다. 노드는 만들지 않는다.

    출력 .vex 는 임시 디렉토리에 쓰고 바로 버린다. 우리가 원하는 건 진단뿐이다.

    Args:
        source: `#line` 라벨까지 포함해 vcc 에 그대로 넘길 소스.
        context: vcc 컨텍스트 이름(`sop`, `cvex`, `surface` …).
        include_dirs: 추가 include 검색 경로.
    """
    with tempfile.TemporaryDirectory(prefix="houdini_mcp_vex_") as workdir:
        work = Path(workdir)
        source_file = work / "check.vfl"
        source_file.write_text(source, encoding="utf-8")

        args = ["-c", context, "-o", str(work / "check.vex")]
        for directory in include_dirs or ():
            args += ["-I", str(Path(directory))]
        args.append(str(source_file))
        proc = run_vcc(args)

    diagnostics, notes = parse_diagnostics(proc.stderr)
    extra, extra_notes = parse_diagnostics(proc.stdout)
    diagnostics.extend(extra)
    notes.extend(extra_notes)

    errors = [d for d in diagnostics if d["severity"] == "error"]
    return {
        "ok": not errors and proc.returncode == 0,
        "returncode": proc.returncode,
        "diagnostics": diagnostics,
        "notes": notes,
    }


# ---- 컨텍스트 정보 ----------------------------------------------------


def contexts() -> tuple[str, ...]:
    """vcc 가 아는 컨텍스트 이름들. 프로세스 수명 동안 한 번만 묻는다."""
    global _contexts
    if _contexts is None:
        proc = run_vcc(["-X"])
        names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        _contexts = tuple(names)
    return _contexts


def context_info(context: str) -> dict[str, Any]:
    """컨텍스트의 전역 변수와 함수 시그니처. 컨텍스트당 700KB 라 캐시한다."""
    cached = _context_json.get(context)
    if cached is not None:
        return cached

    known = contexts()
    if context not in known:
        raise ValueError(
            f"그런 VEX 컨텍스트가 없습니다: {context!r}. "
            f"쓸 수 있는 것: {', '.join(known)}"
        )

    proc = run_vcc([f"--list-context-json={context}"])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"vcc 가 {context!r} 컨텍스트 정보를 JSON 으로 주지 않았습니다. "
            f"Houdini 버전이 바뀌어 출력 형식이 달라졌는지 확인하세요. ({exc})"
        ) from exc
    _context_json[context] = data
    return data
