"""내보내기 툴 — 쓰고 나서 **반드시 다시 읽어 검증한다.**

기존 MCP 구현들은 ROP 을 만들고 렌더 버튼을 누른 뒤 `{"ok": true}` 를 돌려준다.
파일이 비어 있어도 모델은 알 수 없다. 여기서는 포맷마다 맞는 리더로 다시 열어
점·프리미티브 수를 대조하고, **안 맞으면 안 맞는다고 돌려준다.**

포맷별로 경로가 다른 이유는 실측 때문이다(Houdini 22.0.368).

| 포맷 | 쓰는 길 | 검증하는 길 |
|---|---|---|
| bgeo/geo/obj/ply/stl/vdb | `hou.Geometry.saveToFile` | `hou.Geometry.loadFromFile` 로 재독 |
| USD | `pxr.Usd.Stage.Export` (LOP 스테이지) | `Usd.Stage.Open` + 프림/포인트 대조 |
| Alembic | `rop_alembic` ROP | `$HFS/bin/abcinfo` (파이썬 바인딩 없음) |
| FBX | `rop_fbx` ROP | 파일 시그니처 + 크기 |

`saveToFile` 은 `.usd` / `.abc` / `.fbx` 를 받고도 내용은 ASCII `.geo` 를 쓴다.
확장자만 바뀐 가짜 파일이 생기고, Houdini 로 다시 읽으면 내용을 스니핑해서
읽히므로 왕복 검사로도 안 잡힌다. 그래서 `write_geometry` 는 그 확장자들을
거부하고 전용 툴로 보낸다.

Apprentice 라이선스는 Alembic·FBX 내보내기가 막혀 있다(실측 확인). 노드를
만들어 놓고 실패하느니 먼저 알려 준다.

모듈은 포맷별로 나뉜다. 여기에는 네이티브 포맷(`write_geometry`)과
`export_formats`, USD 는 usd.py, Alembic·FBX 는 interchange.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import hou

from houdini_mcp import tool

from houdini_mcp_base import paths

from ._common import (
    DELEGATED_FORMATS,
    NATIVE_FORMATS,
    USD_SUFFIXES,
    cooked_geometry,
    frame_list,
    geometry_summary,
    require_sop,
    suffix_of,
    verify_native_file,
)

MAX_REPORTED_FRAMES = 40
"""응답에 프레임별 항목을 몇 개까지 담을지. 1000 프레임을 다 실으면 컨텍스트만 탄다."""


# --------------------------------------------------------------------------
# 네이티브 지오메트리 포맷
# --------------------------------------------------------------------------


def _reject_delegated(target: Path) -> None:
    suffix = suffix_of(target)
    if suffix in DELEGATED_FORMATS:
        raise ValueError(
            f"{suffix} 는 write_geometry 로 쓰면 안 됩니다. Houdini 의 saveToFile 은 "
            f"이 확장자를 받고도 내용은 ASCII .geo 를 씁니다(확장자만 바뀐 가짜 파일). "
            f"{DELEGATED_FORMATS[suffix]} 를 쓰세요."
        )
    if suffix not in NATIVE_FORMATS:
        raise ValueError(
            f"{target.name} 의 확장자 {suffix!r} 로는 포맷을 정할 수 없습니다. "
            f"쓸 수 있는 확장자: {', '.join(NATIVE_FORMATS)}. "
            f"USD/Alembic/FBX 는 export_usd / export_alembic / export_fbx 를 쓰세요."
        )


def _write_one(geo: hou.Geometry, target: Path, verify: bool) -> dict[str, Any]:
    expected = geometry_summary(geo)
    try:
        geo.saveToFile(str(target))
    except hou.Error as exc:
        raise ValueError(
            f"{target} 로 저장하지 못했습니다: {exc} "
            f"디렉토리 권한과 확장자를 확인하세요."
        ) from exc

    entry: dict[str, Any] = {"file": target.as_posix(), **paths.file_stat(target)}
    if verify:
        entry["verification"] = verify_native_file(target, expected)
    return entry


@tool()
def write_geometry(
    path: str,
    file_path: str,
    overwrite: bool = False,
    frame_range: Sequence[float] | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    """SOP 지오메트리를 네이티브 포맷으로 쓰고, 다시 읽어 맞는지 확인한다.

    `houdini_mcp_sop` 의 `export_geometry` 는 한 프레임을 그냥 던지고 끝낸다.
    이 툴은 셋이 다르다.

    1. 쓴 파일을 **다시 읽어** 점·프림·어트리뷰트를 대조한다. 안 맞으면
       verification.mismatches 에 그대로 담는다.
    2. **프레임 범위**를 쓸 수 있다. 파일 이름에 $F4 를 넣으면 프레임마다 쓴다.
    3. `.usd` / `.abc` / `.fbx` 를 **거부한다.** saveToFile 은 그 확장자를 받고도
       내용은 .geo 를 쓰기 때문이다. export_usd / export_alembic / export_fbx 로
       가야 진짜 파일이 나온다.

    `.obj` / `.ply` / `.stl` / `.vdb` 는 왕복하면 수가 달라지는 것이 정상이라
    lossy 로 표시하고 델타만 보여 준다(.stl 은 삼각화, .vdb 는 볼륨만 담는다).

    Args:
        path: 내보낼 SOP 노드 경로.
        file_path: 저장할 경로. $HIP 같은 Houdini 변수를 써도 된다.
            쓸 수 있는 확장자: .bgeo.sc(권장) / .bgeo / .geo / .obj / .ply / .stl / .vdb
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
        frame_range: [start, end] 또는 [start, end, step]. 주면 프레임마다 쿡해서
            쓴다. 이때 file_path 에 $F4 같은 프레임 토큰이 있어야 한다.
        verify: False 면 다시 읽지 않는다. 아주 큰 캐시에만 쓴다.
    """
    node = require_sop(path)
    frames = frame_list(frame_range)

    probe = paths.to_path(file_path)
    _reject_delegated(probe)

    if frames is None:
        target = paths.prepare_output(file_path, overwrite)
        geo = cooked_geometry(node)
        entry = _write_one(geo, target, verify)
        return {
            "path": node.path(),
            "comment": node.comment(),
            "format": suffix_of(target),
            "expected": {
                key: geometry_summary(geo)[key] for key in ("points", "prims", "vertices")
            },
            "files": [entry],
            "frames": 1,
            "all_verified": bool(entry.get("verification", {}).get("verified", True)),
        }

    if not paths.has_sequence_token(file_path):
        raise ValueError(
            f"frame_range 를 줬는데 file_path 에 프레임 토큰이 없습니다: {file_path!r}. "
            f"프레임마다 같은 파일을 덮어쓰게 됩니다. $F4 를 넣으세요. "
            f"예: $HIP/geo/wall_body.$F4.bgeo.sc"
        )

    original = hou.frame()
    entries: list[dict[str, Any]] = []
    try:
        for frame in frames:
            hou.setFrame(frame)
            target = paths.prepare_output(file_path, overwrite)
            geo = cooked_geometry(node)
            entry = _write_one(geo, target, verify)
            entry["frame"] = frame
            entries.append(entry)
    finally:
        # 현재 프레임을 바꾼 채로 끝내지 않는다. 사용자의 플레이바가 움직인다.
        hou.setFrame(original)

    verified = [e for e in entries if e.get("verification", {}).get("verified", True)]
    return {
        "path": node.path(),
        "comment": node.comment(),
        "format": suffix_of(Path(entries[0]["file"])) if entries else None,
        "frames": len(entries),
        "verified_frames": len(verified),
        "all_verified": len(verified) == len(entries),
        "total_bytes": sum(e.get("bytes", 0) for e in entries),
        "files": entries[:MAX_REPORTED_FRAMES],
        "truncated": max(0, len(entries) - MAX_REPORTED_FRAMES),
    }


@tool(affinity="any")
def export_formats() -> dict[str, Any]:
    """어떤 포맷을 어느 툴로 써야 하는지, 이 설치에서 무엇이 되는지 알려 준다.

    라이선스와 `$HFS/bin` 실측을 섞어 돌려주므로, 내보내기를 시도하기 전에
    무엇이 가능한지 한 번에 알 수 있다. Apprentice 에서 Alembic ROP 을 돌려
    보고서야 막힌 것을 아는 왕복을 없앤다.
    """
    from ._common import license_name

    name = license_name()
    apprentice = name.startswith("Apprentice")
    return {
        "license": name,
        "native": {
            "tool": "write_geometry",
            "suffixes": list(NATIVE_FORMATS),
            "available": True,
            "verified_by": "hou.Geometry.loadFromFile 재독",
        },
        "usd": {
            "tool": "export_usd",
            "suffixes": list(USD_SUFFIXES),
            "available": True,
            "verified_by": "pxr.Usd.Stage.Open",
            "usdchecker": paths.hfs_bin("usdchecker") is not None,
        },
        "alembic": {
            "tool": "export_alembic",
            "suffixes": [".abc"],
            "available": not apprentice,
            "blocked_by": f"{name} 라이선스" if apprentice else None,
            "verified_by": "$HFS/bin/abcinfo",
            "abcinfo": paths.hfs_bin("abcinfo") is not None,
        },
        "fbx": {
            "tool": "export_fbx",
            "suffixes": [".fbx"],
            "available": not apprentice,
            "blocked_by": f"{name} 라이선스" if apprentice else None,
            "verified_by": "파일 시그니처만",
        },
        "warning": (
            "hou.Geometry.saveToFile 은 .usd/.abc/.fbx 확장자를 받고도 내용은 ASCII "
            ".geo 를 씁니다. write_geometry 가 그 확장자를 거부하는 이유입니다."
        ),
    }
