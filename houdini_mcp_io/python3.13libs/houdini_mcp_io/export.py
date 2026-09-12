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
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from ._common import (
    DELEGATED_FORMATS,
    NATIVE_FORMATS,
    USD_SUFFIXES,
    cooked_geometry,
    expand,
    file_stat,
    frame_list,
    geometry_summary,
    has_sequence_token,
    hfs_bin,
    prepare_output,
    require_commercial,
    require_node,
    require_sop,
    run_hfs_tool,
    suffix_of,
    temp_node,
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

    entry: dict[str, Any] = {"file": str(target), **file_stat(target)}
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

    probe = Path(expand(file_path))
    _reject_delegated(probe)

    if frames is None:
        target = prepare_output(file_path, overwrite)
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

    if not has_sequence_token(file_path):
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
            target = prepare_output(file_path, overwrite)
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


# --------------------------------------------------------------------------
# USD
# --------------------------------------------------------------------------


def _usd_stage_of(node: hou.Node) -> tuple[Any, hou.Node | None, dict[str, Any]]:
    """내보낼 USD 스테이지를 얻는다. (stage, 임시노드, 소스요약).

    LOP 이면 그 노드의 스테이지를 그대로 쓴다. SOP 이면 `/stage` 에 임시
    `sopimport` LOP 을 만들어 통과시킨다. 임시 노드는 부른 쪽이 지운다.
    """
    if isinstance(node, hou.LopNode):
        try:
            node.cook()
            stage = node.stage()
        except hou.Error as exc:
            raise ValueError(
                f"{node.path()} 의 USD 스테이지를 얻지 못했습니다: {exc} "
                f"validate_stage 로 이 LOP 의 에러를 먼저 확인하세요."
            ) from exc
        return stage, None, {"kind": "lop"}

    sop = require_sop(node.path())
    geo = cooked_geometry(sop)
    summary = geometry_summary(geo)

    stage_net = hou.node("/stage")
    if stage_net is None:
        raise ValueError("/stage 네트워크를 찾지 못했습니다. 이 Houdini 빌드에 LOP 이 없습니다.")

    importer = temp_node(stage_net, "sopimport", "USD 내보내기")
    try:
        importer.parm("soppath").set(sop.path())
        # sopimport 는 기본적으로 SOP 지오메트리를 $HIP/usd/<노드>.usd 로 따로
        # 흘려 쓴다(실측 확인). 임시 노드가 사용자 프로젝트에 파일을 남기면 안 되고,
        # 우리는 스테이지를 통째로 Export 하므로 사이드카가 필요 없다.
        importer.parm("enable_savepath").set(0)
        importer.cook(force=True)
        stage = importer.stage()
    except hou.Error as exc:
        importer.destroy()
        raise ValueError(
            f"{sop.path()} 를 USD 로 변환하지 못했습니다: {exc}"
        ) from exc
    return stage, importer, {
        "kind": "sop",
        "points": summary["points"],
        "prims": summary["prims"],
    }


def _references_op_path(value: Any) -> bool:
    """값이 `op:/obj/...` 처럼 노드를 가리키는 에셋 경로인지.

    Houdini 세션 안에서만 풀리는 경로다. 파일에 남으면 다른 도구가 열 때
    해석 불가 의존성이 된다.
    """
    # pxr 는 asset[] 를 Vt 배열로 준다. list 도 tuple 도 아니므로 문자열이 아닌
    # 모든 이터러블을 펼친다.
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        items = [value]
    else:
        items = list(value)
    texts = [str(getattr(item, "path", item)) for item in items]
    return bool(texts) and all(text.startswith("op:") for text in texts)


def _author_stage_metadata(target: Path) -> dict[str, Any]:
    """쓴 파일에 upAxis 와 defaultPrim 을 채워 넣는다.

    `Usd.Stage.Export()` 는 스테이지 메타데이터를 저자하지 않아서, 나온 파일을
    `usdchecker` 에 물리면 MissingUpAxisMetadata / MissingDefaultPrim 이 뜬다
    (실측 확인). `usd_rop` 은 `ensuremetricsset` / `defaultprim` 파라미터로 이걸
    해 주는데, 그 ROP 이 파일을 쓰지 않으므로 여기서 직접 채운다.

    Houdini 는 언제나 Y-up 이므로 upAxis 는 Y 다. defaultPrim 은 루트에 내용
    프림이 하나뿐일 때만 정한다 — 여럿이면 무엇을 고를지는 씬 작성자의 몫이다.

    덤으로 `customLayerData` 에 남은 `op:/obj/...` 에셋 경로를 걷어낸다. Houdini
    가 자기 기록용으로 넣는 것인데(`HoudiniVolumeFilePaths`), 이 세션 밖에서는
    풀리지 않아 `usdchecker` 가 해석 불가 의존성으로 잡는다. 지오메트리와는
    무관하다.
    """
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(target))
    if stage is None:
        return {"authored": []}

    authored: list[str] = []
    layer = stage.GetRootLayer()

    stripped: list[str] = []
    for prim in stage.Traverse():
        for key, value in (prim.GetCustomData() or {}).items():
            if _references_op_path(value):
                prim.ClearCustomDataByKey(key)
                stripped.append(f"{prim.GetPath().pathString}.{key}")
    for key, value in dict(layer.customLayerData).items():
        if _references_op_path(value):
            custom = dict(layer.customLayerData)
            del custom[key]
            layer.customLayerData = custom
            stripped.append(f"(layer).{key}")
    if stripped:
        authored.append("stripped:" + ",".join(sorted(stripped)))
    if not stage.HasAuthoredMetadata("upAxis"):
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        authored.append("upAxis")
    if not stage.HasDefaultPrim():
        roots = [
            prim
            for prim in stage.GetPseudoRoot().GetChildren()
            if str(prim.GetTypeName()) != "HoudiniLayerInfo"
        ]
        if len(roots) == 1:
            stage.SetDefaultPrim(roots[0])
            authored.append("defaultPrim")
    if authored:
        layer.Save()
    return {"authored": authored}


def _verify_usd(target: Path, source: dict[str, Any], run_checker: bool) -> dict[str, Any]:
    """쓴 USD 를 pxr 로 다시 열어 확인한다.

    파일이 생겼는지가 아니라 **프림이 실제로 들어 있는지**를 본다. LOP 스테이지가
    비어 있으면 여기서 잡힌다.
    """
    result: dict[str, Any] = {"reread": False, "verified": False}
    if not target.is_file():
        result["error"] = "파일이 생기지 않았습니다."
        return result

    try:
        from pxr import Usd, UsdGeom
    except ImportError as exc:  # pragma: no cover - 번들에 항상 있다
        result["error"] = f"pxr 를 읽지 못해 검증할 수 없습니다: {exc}"
        return result

    try:
        stage = Usd.Stage.Open(str(target))
    except Exception as exc:  # pxr 는 hou.Error 를 쓰지 않는다
        result["error"] = f"USD 로 열리지 않습니다: {str(exc).strip()[:400]}"
        return result
    if stage is None:
        result["error"] = "USD 로 열리지 않습니다(스테이지가 None)."
        return result

    type_counts: dict[str, int] = {}
    # Mesh 만 세면 포인트 클라우드나 커브를 내보냈을 때 거짓 경보가 난다.
    # PointBased 는 Mesh / Points / BasisCurves / NurbsCurves 의 공통 조상이다.
    gprim_points = 0
    for prim in stage.Traverse():
        name = prim.GetTypeName() or "(untyped)"
        type_counts[str(name)] = type_counts.get(str(name), 0) + 1
        if prim.IsA(UsdGeom.PointBased):
            points = UsdGeom.PointBased(prim).GetPointsAttr().Get()
            if points:
                gprim_points += len(points)

    default_prim = stage.GetDefaultPrim()
    # HoudiniLayerInfo 는 Houdini 가 언제나 넣는 메타 프림이다. 이것만 남은 파일은
    # 비어 있는 것이므로 내용 프림을 따로 센다.
    content_prims = sum(
        count for name, count in type_counts.items() if name != "HoudiniLayerInfo"
    )
    result.update(
        {
            "reread": True,
            "prim_types": dict(sorted(type_counts.items())),
            "prim_count": sum(type_counts.values()),
            "content_prims": content_prims,
            "gprim_points": gprim_points,
            "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
            "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
            "default_prim": default_prim.GetPath().pathString if default_prim else None,
            "start_time": stage.GetStartTimeCode(),
            "end_time": stage.GetEndTimeCode(),
        }
    )

    mismatches: list[dict[str, Any]] = []
    if content_prims == 0:
        mismatches.append({"field": "content_prims", "expected": ">0", "actual": 0})
    expected_points = source.get("points")
    if expected_points is not None and gprim_points != expected_points:
        mismatches.append(
            {"field": "gprim_points", "expected": expected_points, "actual": gprim_points}
        )

    # 지오메트리 프림이 하나도 없고 감싸는 Xform 만 남았으면 빈 파일이다. 원본이
    # 비어 있어서 그랬더라도 알려 줘야 한다. 라이트·머티리얼만 담은 스테이지는
    # content_prims 가 여럿이므로 여기 걸리지 않는다.
    empty = gprim_points == 0 and content_prims <= 1
    result["empty"] = empty
    if empty:
        result["note"] = (
            "내보낸 USD 에 지오메트리 프림이 없습니다. 원본이 비어 있는지, "
            "LOP 이면 validate_stage 로 스테이지를 먼저 확인하세요."
        )
    result["mismatches"] = mismatches
    result["verified"] = not mismatches and not empty

    if run_checker:
        checker = run_hfs_tool("usdchecker", [str(target)])
        if checker.get("available"):
            result["usdchecker"] = {
                "passed": checker.get("ok"),
                "output": (checker.get("stdout") or checker.get("stderr") or "").strip()[:1500],
            }
        else:
            result["usdchecker"] = checker
    return result


@tool()
@undoable("Export USD")
def export_usd(
    path: str,
    file_path: str,
    overwrite: bool = False,
    flatten: bool = True,
    set_metadata: bool = True,
    run_usdchecker: bool = False,
) -> dict[str, Any]:
    """SOP 이나 LOP 을 USD 로 내보내고, pxr 로 다시 열어 확인한다.

    `usd_rop` 을 쓰지 않는다. 실측(22.0.368, Apprentice)에서 `usd_rop.render()` 는
    **에러도 없이 아무 파일도 쓰지 않았다.** 대신 LOP 스테이지를 `pxr` 로 직접
    받아 `Usd.Stage.Export()` 로 쓴다 — 번들된 OpenUSD 0.26.5 를 그대로 쓰는
    길이라 라이선스에도 걸리지 않는다.

    검증은 파일 존재가 아니라 내용이다. 다시 열어 프림 종류별 개수, 메시 포인트
    합계, up axis, default prim 을 읽어 원본 SOP 의 포인트 수와 대조한다.

    SOP 경로를 주면 `/stage` 에 임시 sopimport LOP 을 만들어 통과시킨 뒤 지운다.

    Args:
        path: 내보낼 SOP 또는 LOP 노드 경로.
        file_path: 저장할 경로. .usd / .usda(텍스트) / .usdc(바이너리) / .usdz
        overwrite: 이미 있는 파일을 덮어쓸 때 True.
        flatten: True 면 컴포지션을 평탄화해서 한 파일로 쓴다(참조·서브레이어가
            풀린 자립 파일). False 면 루트 레이어만 쓴다 — 참조가 상대 경로로
            남으므로 옮기면 깨질 수 있다.
        set_metadata: True(기본)면 쓴 뒤 upAxis 와 defaultPrim 을 채운다.
            pxr 의 Export 는 이 둘을 저자하지 않아서, 그냥 두면 다른 DCC 가
            읽을 때 방향과 진입 프림을 모른다.
        run_usdchecker: True 면 $HFS/bin/usdchecker 로 규격 검사까지 돌린다.
    """
    node = require_node(path)
    target = prepare_output(file_path, overwrite)
    if suffix_of(target) not in USD_SUFFIXES:
        raise ValueError(
            f"{target.name} 은 USD 확장자가 아닙니다. "
            f"쓸 수 있는 확장자: {', '.join(USD_SUFFIXES)}"
        )

    stage, temporary, source = _usd_stage_of(node)
    try:
        try:
            if flatten:
                stage.Export(str(target))
            else:
                stage.GetRootLayer().Export(str(target))
        except Exception as exc:
            raise ValueError(
                f"{target} 로 USD 를 쓰지 못했습니다: {str(exc).strip()[:400]} "
                f"디렉토리 권한과 확장자를 확인하세요."
            ) from exc
    finally:
        if temporary is not None:
            temporary.destroy()

    metadata: dict[str, Any] = {"authored": []}
    if set_metadata:
        try:
            metadata = _author_stage_metadata(target)
        except Exception as exc:
            # 메타데이터를 못 채워도 지오메트리는 이미 나갔다. 실패시키지 않고 알린다.
            metadata = {"authored": [], "error": str(exc).strip()[:300]}

    verification = _verify_usd(target, source, run_usdchecker)
    return {
        "path": node.path(),
        "comment": node.comment(),
        "source": source,
        "file": str(target),
        "flattened": flatten,
        "metadata": metadata,
        **file_stat(target),
        "verification": verification,
        "verified": verification["verified"],
    }


# --------------------------------------------------------------------------
# Alembic
# --------------------------------------------------------------------------

_ABC_OBJECT = re.compile(r"^(/\S*)\s+\((\w+)\)\s*$")
_ABC_COUNT = re.compile(r"^(\d+)\s+Objects displayed")


def _parse_abcinfo(stdout: str) -> dict[str, Any]:
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

    info = run_hfs_tool("abcinfo", ["-o", "-b", str(target)])
    if not info.get("available"):
        result["error"] = info.get("reason", "abcinfo 를 찾지 못했습니다.")
        result["verified"] = bool(result["signature_ok"])
        result["note"] = "abcinfo 가 없어 시그니처만 확인했습니다."
        return result
    if not info.get("ok"):
        result["error"] = f"abcinfo 가 실패했습니다: {info.get('stderr', '')[:300]}"
        return result

    parsed = _parse_abcinfo(info.get("stdout", ""))
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
    target = prepare_output(file_path, overwrite)
    if suffix_of(target) != ".abc":
        raise ValueError(f"{target.name} 은 .abc 가 아닙니다. Alembic 확장자를 주세요.")

    geo = cooked_geometry(node)
    source = geometry_summary(geo)
    frames = frame_list(frame_range)

    rop = temp_node(node.parent(), "rop_alembic", "Alembic 내보내기")
    try:
        rop.parm("filename").set(str(target))
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
        "file": str(target),
        "source": {key: source[key] for key in ("points", "prims", "vertices")},
        "frames": len(frames) if frames else 1,
        **file_stat(target),
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
    target = prepare_output(file_path, overwrite)
    if suffix_of(target) != ".fbx":
        raise ValueError(f"{target.name} 은 .fbx 가 아닙니다. FBX 확장자를 주세요.")

    start = node if isinstance(node, hou.ObjNode) else node.parent()
    frames = frame_list(frame_range)

    rop = temp_node(hou.node("/out"), "filmboxfbx", "FBX 내보내기")
    try:
        rop.parm("sopoutput").set(str(target))
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
        "file": str(target),
        "frames": len(frames) if frames else 1,
        **file_stat(target),
        "verification": verification,
        "verified": verification["verified"],
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
            "usdchecker": hfs_bin("usdchecker") is not None,
        },
        "alembic": {
            "tool": "export_alembic",
            "suffixes": [".abc"],
            "available": not apprentice,
            "blocked_by": f"{name} 라이선스" if apprentice else None,
            "verified_by": "$HFS/bin/abcinfo",
            "abcinfo": hfs_bin("abcinfo") is not None,
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
