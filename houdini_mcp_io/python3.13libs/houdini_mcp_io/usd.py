"""USD 내보내기 - LOP 스테이지를 pxr 로 직접 쓰고 다시 열어 대조한다.

포맷마다 쓰는 길과 검증하는 길이 다른 이유는 export.py 모듈 docstring 의 표에
있다. export.py 가 800줄 경계에 닿아 포맷별로 나눴다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool, undoable

from houdini_mcp_base import paths

from ._common import (
    USD_SUFFIXES,
    cooked_geometry,
    geometry_summary,
    require_node,
    require_sop,
    suffix_of,
    temp_node,
)


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
        checker = paths.run_hfs_tool("usdchecker", [str(target)])
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
    target = paths.prepare_output(file_path, overwrite)
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
        "file": target.as_posix(),
        "flattened": flatten,
        "metadata": metadata,
        **paths.file_stat(target),
        "verification": verification,
        "verified": verification["verified"],
    }


