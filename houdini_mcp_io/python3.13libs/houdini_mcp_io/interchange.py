"""Alembic·FBX 내보내기 - DCC 교환 포맷. 둘 다 ROP 으로 쓴다.

Apprentice 라이선스는 둘 다 막혀 있다(실측). 검증 경로가 서로 다르다 -
Alembic 은 `$HFS/bin/abcinfo`(파이썬 바인딩이 번들에 없다), FBX 는 파일
시그니처만 본다. 포맷별 표는 export.py 모듈 docstring 에 있다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from houdini_mcp_base import paths

from ._common import (
    cooked_geometry,
    frame_list,
    geometry_summary,
    require_commercial,
    require_node,
    require_sop,
    suffix_of,
    temp_node,
)


# --------------------------------------------------------------------------
# Alembic
# --------------------------------------------------------------------------

_ABC_OBJECT = re.compile(r"^(/\S*)\s+\((\w+)\)\s*$")
_ABC_COUNT = re.compile(r"^(\d+)\s+Objects displayed")


def parse_abcinfo(stdout: str) -> dict[str, Any]:
    """abcinfo -o -b 출력을 읽는다. Alembic 파이썬 바인딩이 번들에 없어서 CLI 다."""
    objects: list[dict[str, str]] = []
    type_counts: dict[str, int] = {}
    declared = None
    for line in stdout.splitlines():
        match = _ABC_OBJECT.match(line.strip())
        if match:
            objects.append({"path": match.group(1), "type": match.group(2)})
            type_counts[match.group(2)] = type_counts.get(match.group(2), 0) + 1
            continue
        count = _ABC_COUNT.match(line.strip())
        if count:
            declared = int(count.group(1))
    return {
        "objects": objects[:40],
        "object_count": declared if declared is not None else len(objects),
        "object_types": dict(sorted(type_counts.items())),
    }


def _verify_alembic(target: Path) -> dict[str, Any]:
    """abcinfo 로 다시 읽는다. Houdini 로 읽으면 packed 프림 1개라 대조가 안 된다."""
    result: dict[str, Any] = {"reread": False, "verified": False}
    if not target.is_file():
        result["error"] = "파일이 생기지 않았습니다."
        return result

    header = target.open("rb").read(8)
    result["signature_ok"] = header.startswith(b"Ogawa") or header.startswith(b"\x89HDF")

    info = paths.run_hfs_tool("abcinfo", ["-o", "-b", str(target)])
    if not info.get("available"):
        result["error"] = info.get("reason", "abcinfo 를 찾지 못했습니다.")
        result["verified"] = bool(result["signature_ok"])
        result["note"] = "abcinfo 가 없어 시그니처만 확인했습니다."
        return result
    if not info.get("ok"):
        result["error"] = f"abcinfo 가 실패했습니다: {info.get('stderr', '')[:300]}"
        return result

    parsed = parse_abcinfo(info.get("stdout", ""))
    result.update({"reread": True, **parsed})
    result["mismatches"] = (
        [] if parsed["object_count"] else [{"field": "object_count", "expected": ">0", "actual": 0}]
    )
    result["verified"] = bool(result["signature_ok"] and parsed["object_count"])
    return result


@tool()
@undoable("Export Alembic")
def export_alembic(
    path: str,
    file_path: str,
    overwrite: bool = False,
    frame_range: Sequence[float] | None = None,
) -> dict[str, Any]:
    """SOP 을 Alembic 으로 내보내고, abcinfo 로 다시 열어 확인한다.

    Alembic 파이썬 바인딩은 Houdini 에 번들돼 있지 않다(실측 확인). 그래서 쓰는
    것은 `rop_alembic` ROP 으로 하고, 검증은 `$HFS/bin/abcinfo` 로 한다 —
    Houdini 로 다시 읽으면 packed 프림 하나로 보여서 대조가 되지 않기 때문이다.
    abcinfo 는 아카이브 안의 오브젝트 계층과 타입(PolyMesh / Xform / Camera)을
    그대로 보여 준다.

    **Apprentice 라이선스는 Alembic 내보내기를 지원하지 않는다**(실측 확인).
    그 경우 노드를 만들기 전에 거절하고, 대신 write_geometry 로 .bgeo.sc 를
    쓰라고 알려 준다.

    Args:
        path: 내보낼 SOP 노드 경로.
        file_path: 저장할 .abc 경로.
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
        frame_range: [start, end] 또는 [start, end, step]. 생략하면 현재 프레임만.
            Alembic 한 파일 안에 프레임들이 시간 샘플로 들어간다.
    """
    require_commercial("Alembic", "write_geometry 로 .bgeo.sc 를 쓰거나 export_usd")
    node = require_sop(path)
    target = paths.prepare_output(file_path, overwrite)
    if suffix_of(target) != ".abc":
        raise ValueError(f"{target.name} 은 .abc 가 아닙니다. Alembic 확장자를 주세요.")

    geo = cooked_geometry(node)
    source = geometry_summary(geo)
    frames = frame_list(frame_range)

    rop = temp_node(node.parent(), "rop_alembic", "Alembic 내보내기")
    try:
        rop.parm("filename").set(target.as_posix())
        rop.parm("use_sop_path").set(True)
        rop.parm("sop_path").set(node.path())
        if frames is None:
            rop.parm("trange").set(0)
        else:
            rop.parm("trange").set(1)
            rop.parmTuple("f").set((frames[0], frames[-1], frames[1] - frames[0] if len(frames) > 1 else 1.0))
        try:
            rop.render()
        except hou.OperationFailed as exc:
            raise ValueError(
                f"Alembic 내보내기에 실패했습니다: {str(exc).strip()[:400]} "
                f"라이선스와 출력 경로를 확인하세요."
            ) from exc
    finally:
        rop.destroy()

    verification = _verify_alembic(target)
    return {
        "path": node.path(),
        "comment": node.comment(),
        "file": target.as_posix(),
        "source": {key: source[key] for key in ("points", "prims", "vertices")},
        "frames": len(frames) if frames else 1,
        **paths.file_stat(target),
        "verification": verification,
        "verified": verification["verified"],
    }


# --------------------------------------------------------------------------
# FBX
# --------------------------------------------------------------------------


def _verify_fbx(target: Path) -> dict[str, Any]:
    """FBX 시그니처와 크기를 본다.

    FBX SDK 파이썬 바인딩도 번들에 없고, Houdini 로 다시 읽는 유일한 길인
    `hou.hipFile.importFBX` 는 **현재 씬에 노드를 쏟아붓는다**. 검증하려다
    사용자 씬을 더럽힐 수는 없으므로 여기서는 헤더까지만 본다.
    다시 읽어 대조가 필요하면 import_geometry 로 새 씬에서 열어 보라고 알려 준다.
    """
    result: dict[str, Any] = {"reread": False, "verified": False}
    if not target.is_file():
        result["error"] = "파일이 생기지 않았습니다."
        return result

    header = target.open("rb").read(23)
    binary = header.startswith(b"Kaydara FBX Binary")
    ascii_fbx = b"FBX" in header or target.open("rb").read(512).find(b"FBXHeaderExtension") >= 0
    size = target.stat().st_size
    result.update(
        {
            "reread": True,
            "binary": binary,
            "signature_ok": bool(binary or ascii_fbx),
            "bytes": size,
            "note": (
                "FBX 는 파이썬 바인딩이 없고, Houdini 로 다시 읽으면 현재 씬에 노드가 "
                "쏟아지므로 헤더까지만 확인합니다. 내용을 보려면 새 씬에서 "
                "import_geometry 로 여세요."
            ),
        }
    )
    result["verified"] = bool(result["signature_ok"] and size > 0)
    return result


@tool()
@undoable("Export FBX")
def export_fbx(
    path: str,
    file_path: str,
    overwrite: bool = False,
    frame_range: Sequence[float] | None = None,
    ascii_format: bool = False,
) -> dict[str, Any]:
    """OBJ 서브트리나 SOP 을 FBX 로 내보내고, 헤더를 확인한다.

    `rop_fbx` ROP 을 쓴다. startnode 에 OBJ 노드를 주면 그 아래를 통째로,
    SOP 을 주면 그 SOP 이 든 지오메트리 오브젝트를 내보낸다.

    **Apprentice 라이선스는 FBX 내보내기를 지원하지 않는다**(실측 확인).
    그 경우 노드를 만들기 전에 거절한다.

    검증이 얕은 것은 의도적이다 — FBX SDK 파이썬 바인딩이 번들에 없고, Houdini 로
    다시 읽는 길(`hou.hipFile.importFBX`)은 현재 씬에 노드를 쏟아붓는다. 검증하려고
    사용자 씬을 망가뜨리지 않는다.

    Args:
        path: 내보낼 노드 경로. OBJ 노드(서브트리 통째로) 또는 SOP.
        file_path: 저장할 .fbx 경로.
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
        frame_range: [start, end] 또는 [start, end, step]. 생략하면 현재 프레임만.
        ascii_format: True 면 텍스트 FBX 로 쓴다. 디버깅용이고 파일이 커진다.
    """
    require_commercial("FBX", "export_usd 나 write_geometry")
    node = require_node(path)
    target = paths.prepare_output(file_path, overwrite)
    if suffix_of(target) != ".fbx":
        raise ValueError(f"{target.name} 은 .fbx 가 아닙니다. FBX 확장자를 주세요.")

    start = node if isinstance(node, hou.ObjNode) else node.parent()
    frames = frame_list(frame_range)

    rop = temp_node(hou.node("/out"), "filmboxfbx", "FBX 내보내기")
    try:
        rop.parm("sopoutput").set(target.as_posix())
        rop.parm("startnode").set(start.path())
        rop.parm("vcformat").set(1 if ascii_format else 0)
        if frames is None:
            rop.parm("trange").set(0)
        else:
            rop.parm("trange").set(1)
            rop.parmTuple("f").set((frames[0], frames[-1], frames[1] - frames[0] if len(frames) > 1 else 1.0))
        try:
            rop.render()
        except hou.OperationFailed as exc:
            raise ValueError(
                f"FBX 내보내기에 실패했습니다: {str(exc).strip()[:400]} "
                f"라이선스와 startnode({start.path()})를 확인하세요."
            ) from exc
    finally:
        rop.destroy()

    verification = _verify_fbx(target)
    return {
        "path": node.path(),
        "start_node": start.path(),
        "comment": node.comment(),
        "file": target.as_posix(),
        "frames": len(frames) if frames else 1,
        **paths.file_stat(target),
        "verification": verification,
        "verified": verification["verified"],
    }


