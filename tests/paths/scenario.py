"""houdini_mcp_base.paths 회귀 시나리오. hython 안에서 돈다.

시스템 python 에는 `hou` 가 없으므로 테스트는 이 파일을 hython 서브프로세스로
띄우고, 마지막에 찍는 JSON 한 줄을 읽어 검사한다(tests/sop 와 같은 방식).

여기서 못 박는 것은 전부 **예외 없이 조용히 틀리던 것**이다.

  - 역슬래시가 이스케이프로 먹혀 `C:\\tmp\\$F4.exr` 가 망가지던 것
  - `$FPS` 를 프레임 토큰으로 오인해 시퀀스로 보던 것
  - 모르는 변수가 빈 문자열이 되어 루트 경로에 쓰던 것
  - 원문을 Path 로 만들어 mkdir 해서 현재 디렉토리에 `$HIP` 폴더가 생기던 것
  - 디렉토리 이름의 `[` 가 글롭 문자로 읽히던 것
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

MARKER = "PATHSTEST_JSON:"
"""이 접두사가 붙은 줄 하나만 테스트가 읽는다. Houdini 자체 출력과 섞이기 때문."""


def main() -> int:
    import hou

    from houdini_mcp_base import paths

    out: dict[str, object] = {"windows": os.sep != "/"}
    errors: dict[str, str] = {}

    def check(name: str, fn) -> None:
        try:
            out[name] = fn()
        except Exception as exc:  # 어느 검사가 왜 깨졌는지 테스트가 알아야 한다.
            errors[name] = f"{type(exc).__name__}: {exc}"

    root = Path(tempfile.mkdtemp(prefix="hmcp_paths_"))
    hip_dir = root / "hip"
    cwd_dir = root / "cwd"
    hip_dir.mkdir()
    cwd_dir.mkdir()
    os.chdir(cwd_dir)
    hou.hipFile.save(str(hip_dir / "scene.hip"))
    hou.setFrame(12)
    hip = hou.text.expandString("$HIP")

    # --- 전개 ---------------------------------------------------------------
    native = str(hip_dir) + os.sep + "$F4.exr"
    check("backslash_frame", lambda: {
        "expanded": paths.expand(native),
        "expected": f"{hip}/0012.exr",
    })
    check("at_frame", lambda: paths.expand("$HIP/r.$F4.exr", frame=7))
    check("tilde", lambda: {
        "expanded": paths.expand("~/x.exr"),
        "houdini_home": hou.text.expandString("$HOME"),
        "python_home": Path.home().as_posix(),
    })
    if os.sep != "/":
        check("unc", lambda: paths.expand("\\\\server\\share\\x.exr"))
    check("to_parm", lambda: paths.to_parm(str(hip_dir) + os.sep + "geo" + os.sep + "a.bgeo.sc"))
    check("collapse_backslash", lambda: paths.collapse(str(hip_dir / "geo" / "a.bgeo.sc")))
    check("portable", lambda: {
        "absolute_inside_hip": paths.portable(str(hip_dir / "geo" / "a.bgeo.sc")),
        "keeps_user_variable": paths.portable("$HMCP_USER_ROOT/tex/a.exr"),
        "keeps_hip": paths.portable("$HIP/geo/a.bgeo.sc"),
        "outside": paths.portable("D:/elsewhere/x.exr"),
    })

    # --- 변수 ---------------------------------------------------------------
    check("unresolved_unknown", lambda: paths.unresolved_vars("$HMCP_NO_SUCH_VAR/cache/x.bgeo.sc"))
    check("unresolved_known", lambda: paths.unresolved_vars("$HIP/$F4/$SF/$FPS/${F4}/~/x"))
    check("unresolved_glued", lambda: paths.unresolved_vars("$HIP/a_$F_b.exr"))

    # --- 시퀀스 토큰 ----------------------------------------------------------
    check("tokens", lambda: {
        text: paths.has_sequence_token(text)
        for text in (
            "$HIP/x.$F4.exr", "$HIP/x.$F.exr", "$HIP/x.${F4}.exr", "$HIP/x.$SF.sim",
            "$HIP/t.<UDIM>.exr", "$HIP/t.%(UDIM)d.exr", "$HIP/t.<UVTILE>.exr",
            "$HIP/x.%04d.exr", "$HIP/x.$FPS.txt", "$HIP/$FSTART.txt", "$HIP/x.exr",
        )
    })

    seq = hip_dir / "seq"
    seq.mkdir()
    for name in ("wall.0001.exr", "wall.0002.exr", "wall.0003.exr",
                 "tex.1001.exr", "tex.1002.exr", "tex.abcd.exr"):
        (seq / name).write_bytes(b"x")
    bracket = hip_dir / "odd[dir]"
    bracket.mkdir()
    (bracket / "f.0001.exr").write_bytes(b"x")

    def files(raw: str) -> dict[str, object]:
        found, is_sequence = paths.resolve_files(raw)
        return {"names": [p.name for p in found], "sequence": is_sequence}

    check("frame_sequence", lambda: files("$HIP/seq/wall.$F4.exr"))
    check("udim_sequence", lambda: files("$HIP/seq/tex.<UDIM>.exr"))
    check("bracket_dir", lambda: files("$HIP/odd[dir]/f.$F4.exr"))
    check("single_file", lambda: files("$HIP/seq/wall.0002.exr"))
    check("single_missing", lambda: files("$HIP/seq/nope.exr"))

    # --- 응답 ---------------------------------------------------------------
    check("describe_file", lambda: paths.describe("$HIP/seq/wall.0001.exr"))
    check("describe_sequence", lambda: paths.describe("$HIP/seq/wall.$F4.exr"))
    check("describe_unresolved", lambda: paths.describe("$HMCP_NO_SUCH_VAR/x.exr"))

    # --- 쓰기 준비 -----------------------------------------------------------
    def prepared() -> dict[str, object]:
        target = paths.prepare_output("$HIP/out/deep/a.bgeo.sc", overwrite=False)
        return {
            "target": target.as_posix(),
            "parent_exists": target.parent.is_dir(),
            "cwd_entries": sorted(p.name for p in cwd_dir.iterdir()),
        }

    check("prepare_output", prepared)

    def refused_unresolved() -> dict[str, object]:
        try:
            paths.prepare_output("$HMCP_NO_SUCH_VAR/out/a.bgeo.sc", overwrite=False)
        except ValueError as exc:
            return {"message": str(exc), "cwd_entries": sorted(p.name for p in cwd_dir.iterdir())}
        return {"message": ""}

    check("prepare_unresolved", refused_unresolved)

    def refused_overwrite() -> str:
        (hip_dir / "exists.bgeo.sc").write_bytes(b"x")
        try:
            paths.prepare_output("$HIP/exists.bgeo.sc", overwrite=False)
        except ValueError as exc:
            return str(exc)
        return ""

    check("prepare_overwrite", refused_overwrite)
    check("prepare_overwrite_ok", lambda: paths.prepare_output(
        "$HIP/exists.bgeo.sc", overwrite=True).name)

    def missing_message() -> str:
        try:
            paths.require_file("$HIP/seq/wall.9999.exr")
        except ValueError as exc:
            return str(exc)
        return ""

    check("require_file_missing", missing_message)
    check("require_file_ok", lambda: paths.require_file("$HIP/seq/wall.$F4.exr", frame=2).name)

    def dir_as_file() -> str:
        try:
            paths.require_file("$HIP/seq")
        except ValueError as exc:
            return str(exc)
        return ""

    check("require_file_dir", dir_as_file)
    check("require_dir_ok", lambda: paths.require_dir("$HIP/seq").name)

    def missing_dir() -> str:
        try:
            paths.require_dir("$HIP/no_such_dir")
        except ValueError as exc:
            return str(exc)
        return ""

    check("require_dir_missing", missing_dir)
    check("file_stat", lambda: {
        "present": paths.file_stat(seq / "wall.0001.exr").get("bytes"),
        "absent": paths.file_stat(seq / "none.exr"),
    })
    check("is_inside", lambda: {
        "inside": paths.is_inside(seq / "wall.0001.exr", hip_dir),
        "outside": paths.is_inside(seq, cwd_dir),
        "hfs_short_name": paths.is_inside(
            Path(hou.text.expandString("$HFS")) / "bin",
            Path(hou.text.expandString("$HFS")).resolve(),
        ),
    })

    # --- $HFS ---------------------------------------------------------------
    check("hfs_bin", lambda: {
        "vcc": (paths.hfs_bin("vcc") or Path()).is_file(),
        "absent": paths.hfs_bin("hmcp_definitely_not_a_tool"),
    })

    def hfs_missing() -> str:
        try:
            paths.require_hfs_bin("hmcp_definitely_not_a_tool")
        except RuntimeError as exc:
            return str(exc)
        return ""

    check("require_hfs_bin_missing", hfs_missing)

    def vcc_contexts() -> dict[str, object]:
        result = paths.run_hfs_tool("vcc", ["-X"])
        return {"ok": result.get("ok"), "has_cvex": "cvex" in (result.get("stdout") or "")}

    check("run_hfs_tool", vcc_contexts)
    check("run_hfs_tool_absent", lambda: paths.run_hfs_tool("hmcp_definitely_not_a_tool", []))
    check("env_paths", lambda: len(paths.env_paths("HOUDINI_PATH")) > 0)

    out["cwd_after"] = sorted(p.name for p in cwd_dir.iterdir())
    out["hip"] = hip
    out["errors"] = errors
    print(MARKER + json.dumps(out, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
