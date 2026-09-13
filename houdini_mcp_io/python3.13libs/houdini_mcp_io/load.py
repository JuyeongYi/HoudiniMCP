"""들이는 툴 — 파일을 씬으로, 그리고 들이기 전에 파일을 열어 본다.

모듈 이름이 `import` 가 아닌 이유는 그것이 파이썬 예약어라 모듈로 쓸 수 없기
때문이다.

`probe_file` 이 이 모듈의 핵심이다. 기존 구현의 `probe_file` 은 경로와 확장자로
추측한다. 여기서는 **실제로 연다** — USD 는 `pxr` 로, Alembic 은 `abcinfo` 로,
지오메트리는 `hou.Geometry` 로. 임포트하기 전에 한 번 부르면 잘못된 파일을
씬에 들이는 왕복이 없어진다.

이미지 파일은 `houdini_mcp_mat` 의 `texture_info` 가 해상도·채널·컬러스페이스까지
읽는다. 여기서는 이미지라고 알려 주고 그쪽으로 보낸다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool, undoable

from houdini_mcp_base import paths

from ._common import (
    NATIVE_FORMATS,
    SCENE_SUFFIXES,
    USD_SUFFIXES,
    geometry_summary,
    require_comment,
    require_node,
    set_comment,
    suffix_of,
    truncate,
)

IMAGE_SUFFIXES = (
    ".exr", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".tga", ".hdr",
    ".rat", ".pic", ".psd", ".bmp", ".gif", ".dds",
)

HDA_SUFFIXES = (".hda", ".otl", ".hdanc", ".otlnc", ".hdalc", ".otllc")

# 확장자 -> 읽을 SOP 타입. 여기 없는 것은 File SOP 이 확장자를 보고 처리한다.
READER_SOPS = {
    ".abc": "alembic",
    ".usd": "usdimport",
    ".usda": "usdimport",
    ".usdc": "usdimport",
    ".usdz": "usdimport",
}

# SOP 타입 -> 파일 경로 파라미터 이름.
READER_FILE_PARM = {"alembic": "fileName", "usdimport": "filepath1", "file": "file"}

MAX_LISTED = 40


# --------------------------------------------------------------------------
# probe_file
# --------------------------------------------------------------------------


def _classify(target: Path) -> str:
    suffix = suffix_of(target)
    if suffix in USD_SUFFIXES:
        return "usd"
    if suffix == ".abc":
        return "alembic"
    if suffix in SCENE_SUFFIXES:
        return "scene"
    if suffix in HDA_SUFFIXES:
        return "hda"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in NATIVE_FORMATS or suffix in (".fbx", ".gltf", ".glb"):
        return "geometry"
    return "unknown"


def _probe_usd(target: Path, detail: bool) -> dict[str, Any]:
    try:
        from pxr import Usd, UsdGeom
    except ImportError as exc:  # pragma: no cover - 번들에 항상 있다
        return {"opened": False, "error": f"pxr 를 읽지 못했습니다: {exc}"}

    try:
        stage = Usd.Stage.Open(str(target))
    except Exception as exc:
        return {"opened": False, "error": f"USD 로 열리지 않습니다: {str(exc).strip()[:400]}"}
    if stage is None:
        return {"opened": False, "error": "USD 로 열리지 않습니다(스테이지가 None)."}

    type_counts: dict[str, int] = {}
    paths: list[str] = []
    for prim in stage.Traverse():
        type_counts[str(prim.GetTypeName() or "(untyped)")] = (
            type_counts.get(str(prim.GetTypeName() or "(untyped)"), 0) + 1
        )
        paths.append(prim.GetPath().pathString)

    default_prim = stage.GetDefaultPrim()
    info: dict[str, Any] = {
        "opened": True,
        "prim_count": len(paths),
        "prim_types": dict(sorted(type_counts.items())),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "default_prim": default_prim.GetPath().pathString if default_prim else None,
        "start_time": stage.GetStartTimeCode(),
        "end_time": stage.GetEndTimeCode(),
        "sublayers": list(stage.GetRootLayer().subLayerPaths),
    }
    shown, total = truncate(paths, MAX_LISTED)
    info["prims"] = shown
    info["prims_truncated"] = max(0, total - len(shown))
    if detail:
        # 참조가 실제로 풀렸는지 본다. 깨진 참조는 프림이 조용히 비는 식으로
        # 드러나므로, 해석된 에셋 경로를 그대로 보여 준다.
        info["resolved_assets"] = [
            str(layer.realPath) for layer in stage.GetUsedLayers()[:MAX_LISTED]
        ]
    return info


def _probe_alembic(target: Path, detail: bool) -> dict[str, Any]:
    from .interchange import parse_abcinfo  # 파싱 규칙을 한 곳에만 둔다

    args = ["-o", "-b", str(target)]
    if detail:
        args = ["-o", "-b", "-g", "-f", str(target)]
    info = paths.run_hfs_tool("abcinfo", args)
    if not info.get("available"):
        return {"opened": False, "error": info.get("reason")}
    if not info.get("ok"):
        return {"opened": False, "error": f"abcinfo 실패: {info.get('stderr', '')[:300]}"}
    parsed = parse_abcinfo(info.get("stdout", ""))
    result: dict[str, Any] = {"opened": True, **parsed}
    if detail:
        result["abcinfo"] = info.get("stdout", "")[:4000]
    return result


def _probe_geometry(target: Path) -> dict[str, Any]:
    geo = hou.Geometry()
    try:
        geo.loadFromFile(str(target))
    except hou.Error as exc:
        return {"opened": False, "error": f"Houdini 로 읽지 못했습니다: {str(exc)[:300]}"}
    summary = geometry_summary(geo)
    summary["opened"] = True
    summary["groups"] = {
        "point": [g.name() for g in geo.pointGroups()][:MAX_LISTED],
        "prim": [g.name() for g in geo.primGroups()][:MAX_LISTED],
    }
    return summary


def _probe_hda(target: Path) -> dict[str, Any]:
    try:
        definitions = hou.hda.definitionsInFile(str(target))
    except hou.OperationFailed as exc:
        return {"opened": False, "error": f"HDA 로 읽지 못했습니다: {str(exc)[:300]}"}
    return {
        "opened": True,
        "definition_count": len(definitions),
        "definitions": [
            {
                "type": d.nodeTypeName(),
                "category": d.nodeTypeCategory().name(),
                "library": d.libraryFilePath(),
            }
            for d in definitions[:MAX_LISTED]
        ],
        "note": "HDA 의 내부 구조·파라미터는 houdini_mcp_hda 의 툴이 다룹니다.",
    }


@tool()
def probe_file(file_path: str, detail: bool = False) -> dict[str, Any]:
    """파일을 **실제로 열어** 안에 무엇이 들었는지 돌려준다.

    확장자로 추측하지 않는다. 포맷마다 맞는 리더를 쓴다.

    - USD: `pxr` 로 스테이지를 열어 프림 수·종류, up axis, default prim,
      시간 범위, 서브레이어
    - Alembic: `$HFS/bin/abcinfo` 로 오브젝트 계층과 타입
      (파이썬 바인딩이 번들에 없다)
    - 지오메트리(.bgeo/.geo/.obj/.ply/.stl/.vdb 등): `hou.Geometry` 로 읽어
      점·프림·어트리뷰트·그룹
    - HDA: 안에 든 정의 목록
    - 이미지: 여기서는 종류만 알려 준다. 해상도·채널·컬러스페이스는
      `texture_info`(houdini_mcp_mat)가 읽는다
    - 씬(.hip): 열지 않고 크기만. 내용을 보려면 import_scene 을 쓴다

    $F4 나 <UDIM> 이 든 경로를 주면 실제로 몇 장 있는지 세고 첫 파일을 연다.

    임포트하기 전에 이걸 부르면, 비어 있거나 잘못된 파일을 씬에 들이는 왕복이
    없어진다.

    Args:
        file_path: 열어 볼 파일 경로. $HIP 같은 Houdini 변수를 써도 된다.
        detail: True 면 더 깊게 본다(USD 는 해석된 레이어 목록, Alembic 은
            어트리뷰트와 페이스셋까지). 느려진다.
    """
    raw = file_path
    files, is_sequence = paths.resolve_files(raw)
    result: dict[str, Any] = {
        "requested": raw,
        "resolved": paths.to_path(raw).as_posix(),
        "sequence": is_sequence,
    }
    if is_sequence:
        shown, total = truncate((str(f) for f in files), MAX_LISTED)
        result["file_count"] = total
        result["files"] = shown

    if not files:
        result["exists"] = False
        result["error"] = (
            f"그런 파일이 없습니다: {result['resolved']}. "
            f"list_dependencies 로 씬이 참조하는 경로를 확인하거나, 경로의 "
            f"Houdini 변수($HIP, $JOB)가 제대로 풀리는지 보세요."
        )
        return result

    target = files[0]
    kind = _classify(target)
    result.update({"exists": True, "kind": kind, "suffix": suffix_of(target), **paths.file_stat(target)})
    if is_sequence:
        result["probed"] = target.as_posix()

    if kind == "usd":
        result["content"] = _probe_usd(target, detail)
    elif kind == "alembic":
        result["content"] = _probe_alembic(target, detail)
    elif kind == "geometry":
        result["content"] = _probe_geometry(target)
    elif kind == "hda":
        result["content"] = _probe_hda(target)
    elif kind == "image":
        result["content"] = {
            "opened": False,
            "note": (
                "이미지 내용은 texture_info(houdini_mcp_mat)가 OpenImageIO 로 읽습니다. "
                "해상도·채널·비트뎁스·컬러스페이스가 필요하면 그쪽을 부르세요."
            ),
        }
    elif kind == "scene":
        result["content"] = {
            "opened": False,
            "note": (
                "씬 파일은 열어야 내용을 알 수 있습니다. 현재 씬에 합치려면 "
                "import_scene, 통째로 열려면 load_scene(houdini_mcp_base)을 쓰세요."
            ),
        }
    else:
        result["content"] = {
            "opened": False,
            "note": (
                f"{suffix_of(target)!r} 는 이 툴이 아는 포맷이 아닙니다. "
                f"크기와 수정 시각만 확인했습니다."
            ),
        }
    return result


# --------------------------------------------------------------------------
# import_geometry
# --------------------------------------------------------------------------


@tool()
@undoable("Import geometry file")
def import_geometry(
    parent: str,
    file_path: str,
    comment: str,
    name: str | None = None,
) -> dict[str, Any]:
    """지오메트리 파일을 읽는 SOP 을 만들고, 쿡해서 무엇이 들어왔는지 돌려준다.

    확장자에 맞는 리더를 고른다 — `.abc` 는 Alembic SOP, `.usd` 는 USD Import
    SOP, 나머지는 File SOP. 기존 구현들은 무조건 File SOP 을 만들어서, Alembic
    을 읽으면 옵션(로드 모드·오브젝트 필터)에 손댈 수 없었다.

    만들고 끝내지 않고 쿡해서 점·프림·어트리뷰트를 돌려준다. 파일이 비어 있거나
    경로가 틀렸으면 그 자리에서 드러난다.

    parent 가 /obj 처럼 오브젝트 네트워크면 지오메트리 컨테이너를 먼저 만든다.
    SOP 네트워크를 주면 그 안에 바로 만든다.

    노드 이름은 역할이 드러나게 짓는다 — `file1` 이 아니라 `scanned_wall_cache`.

    Args:
        parent: 노드를 만들 네트워크 경로. 예: /obj 또는 /obj/castle
        file_path: 읽을 파일 경로. $HIP 같은 Houdini 변수를 써도 된다.
        comment: 이 노드가 왜 있는지 영어로. 씬을 여는 사람이 읽는다.
        name: 노드 이름. 생략하면 Houdini 가 짓는다. 역할이 드러나게 지으세요.
    """
    require_comment(comment)
    parent_node = require_node(parent)

    files, is_sequence = paths.resolve_files(file_path)
    if not files and not is_sequence:
        raise ValueError(
            f"그런 파일이 없습니다: {paths.to_path(file_path).as_posix()}. "
            f"probe_file 로 경로가 제대로 풀리는지 먼저 확인하세요."
        )

    suffix = suffix_of(files[0] if files else paths.to_path(file_path))
    sop_type = READER_SOPS.get(suffix, "file")

    category = parent_node.childTypeCategory()
    container = None
    if category == hou.objNodeTypeCategory():
        container = parent_node.createNode("geo", node_name=name)
        set_comment(container, comment)
        host = container
    elif category == hou.sopNodeTypeCategory():
        host = parent_node
    else:
        raise ValueError(
            f"{parent} 안에는 SOP 을 만들 수 없습니다"
            f"(자식 카테고리: {category.name() if category else '없음'}). "
            f"/obj 나 지오메트리 오브젝트 안(예: /obj/castle)을 주세요."
        )

    try:
        reader = host.createNode(sop_type, node_name=None if container else name)
    except hou.OperationFailed as exc:
        if container is not None:
            container.destroy()
        raise ValueError(
            f"{host.path()} 안에 {sop_type!r} 노드를 만들지 못했습니다: {exc}"
        ) from exc

    reader.parm(READER_FILE_PARM[sop_type]).set(paths.to_parm(file_path))
    set_comment(reader, comment)
    reader.setDisplayFlag(True)
    reader.setRenderFlag(True)
    try:
        reader.moveToGoodPosition()
    except hou.Error:
        # 배치는 결과에 영향이 없다. 실패해도 툴을 실패시키지 않는다.
        pass

    result: dict[str, Any] = {
        "path": reader.path(),
        "name": reader.name(),
        "type": reader.type().name(),
        "comment": reader.comment(),
        "container": container.path() if container is not None else None,
        "file": file_path,
        "resolved": files[0].as_posix() if files else None,
        "sequence": is_sequence,
        "file_count": len(files) if is_sequence else None,
    }

    try:
        reader.cook(force=True)
    except hou.Error as exc:
        result["cooked"] = False
        result["errors"] = list(reader.errors()) or [str(exc)]
        return result

    geo = reader.geometry()
    result["cooked"] = True
    result["errors"] = list(reader.errors())
    result["warnings"] = list(reader.warnings())
    if geo is not None:
        result["geometry"] = geometry_summary(geo)
        if geo.pointCount() == 0 and geo.primCount() == 0:
            result["note"] = (
                "읽기는 했는데 지오메트리가 비어 있습니다. probe_file 로 파일 안에 "
                "무엇이 들었는지 확인하세요."
            )
    return result


# --------------------------------------------------------------------------
# import_scene
# --------------------------------------------------------------------------


@tool()
@undoable("Merge scene file")
def import_scene(
    file_path: str,
    node_pattern: str = "*",
    overwrite_on_conflict: bool = False,
) -> dict[str, Any]:
    """다른 .hip 의 노드를 현재 씬에 합친다. 무엇이 들어왔는지 세어 준다.

    `load_scene`(houdini_mcp_base)은 현재 씬을 **버리고** 연다. 이 툴은 현재 씬을
    지키면서 노드만 들여온다 — 에셋을 모아 하나의 씬으로 조립할 때 쓴다.

    이름이 겹칠 때 말없이 덮어쓰지 않는다. 덮어쓰려면 overwrite_on_conflict 를
    켜야 한다. 켜지 않으면 Houdini 가 이름을 바꿔서 들인다.

    합치기 전후의 노드 수를 세어 실제로 무엇이 늘었는지 돌려준다.

    Args:
        file_path: 합칠 .hip / .hipnc / .hiplc 경로.
        node_pattern: 이 패턴에 맞는 노드만 들인다. 기본은 전부.
        overwrite_on_conflict: 같은 경로의 노드를 덮어쓴다. 되돌리기 어려우므로
            명시적으로 요구한다.
    """
    # hou.hipFile 은 `$HIP` 원문을 받지 않는다(실측).
    target = paths.to_path(file_path)
    if not target.is_file():
        raise ValueError(
            f"그런 파일이 없습니다: {target}. 경로와 확장자(.hip/.hipnc/.hiplc)를 확인하세요."
        )

    before = _network_census()
    warnings: str | None = None
    try:
        hou.hipFile.merge(
            str(target),
            node_pattern=node_pattern,
            overwrite_on_conflict=overwrite_on_conflict,
        )
    except hou.LoadWarning as warning:
        # 경고는 치명적이지 않다. 대개 없는 에셋 참조다. 그대로 알려 주고 계속한다.
        warnings = str(warning)[:1500]
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{target} 를 합치지 못했습니다: {str(exc)[:300]} "
            f"probe_file 로 파일이 읽히는지 먼저 확인하세요."
        ) from exc

    after = _network_census()
    added = {
        network: after[network] - before.get(network, 0)
        for network in after
        if after[network] != before.get(network, 0)
    }
    return {
        "file": target.as_posix(),
        "node_pattern": node_pattern,
        "added": added,
        "total_added": sum(added.values()),
        "warnings": warnings,
        "has_unsaved_changes": hou.hipFile.hasUnsavedChanges(),
    }


def _network_census() -> dict[str, int]:
    """주요 네트워크의 직계 자식 수. 합치기 전후를 비교하는 데 쓴다."""
    census: dict[str, int] = {}
    for path in ("/obj", "/out", "/mat", "/stage", "/ch", "/shop", "/tasks"):
        node = hou.node(path)
        if node is not None:
            census[path] = len(node.children())
    return census
