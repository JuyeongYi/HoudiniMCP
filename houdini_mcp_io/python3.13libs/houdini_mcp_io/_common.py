"""팩 전체가 쓰는 헬퍼. 툴은 여기 없다.

경로 전개·시퀀스 글롭·`$HFS/bin` 실행은 houdini_mcp_base.paths 가 맡는다. 처음
이 팩에서 만든 것이 그쪽으로 올라갔다. 여기에는 세 가지가 남았다.

1. **포맷 표** — 어느 확장자를 어느 경로로 써야 하는지. `saveToFile` 이
   조용히 거짓말하는 확장자를 여기서 막는다.
2. **검증** — 지오메트리 요약과 대조. 내보낸 파일을 다시 읽어 비교한다.
3. **노드 공통** — 노드 해석, 코멘트, 임시 노드, 프레임 목록.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import hou

from houdini_mcp_base.paths import MAX_SEQUENCE_FILES

# --------------------------------------------------------------------------
# 포맷 표
# --------------------------------------------------------------------------

NATIVE_FORMATS = (".bgeo.sc", ".bgeo", ".geo", ".obj", ".ply", ".stl", ".vdb")
"""`hou.Geometry.saveToFile()` 이 **실제로** 그 포맷으로 쓰는 확장자.

실측(Houdini 22.0.368): 이 목록 밖의 `.usd` / `.abc` / `.fbx` / `.gltf` / `.glb`
를 주면 saveToFile 은 실패하지 않고 ASCII `.geo`(PGEOMETRY V5) 를 쓴다. 확장자만
바꿔 놓은 가짜 파일이 생기고, Houdini 로 다시 읽으면 내용을 스니핑해서 읽히므로
왕복 검사로도 안 잡힌다. 그래서 확장자 화이트리스트로 막는다.
"""

LOSSY_FORMATS = (".obj", ".ply", ".stl", ".vdb")
"""왕복하면 수가 달라지는 것이 정상인 포맷.

- `.stl` 은 삼각화한다(박스 프림 6 -> 12).
- `.obj` / `.ply` 는 어트리뷰트 대부분을 잃는다.
- `.vdb` 는 볼륨만 담는다. 폴리곤을 주면 빈 파일이 나온다.

이런 차이를 실패로 보고하면 거짓 경보가 된다. 대신 `lossy` 로 표시하고 델타를
그대로 보여 준다.
"""

DELEGATED_FORMATS = {
    ".usd": "export_usd",
    ".usda": "export_usd",
    ".usdc": "export_usd",
    ".usdz": "export_usd",
    ".abc": "export_alembic",
    ".fbx": "export_fbx",
}
"""확장자마다 전용 툴이 따로 있는 것. write_geometry 가 여기로 안내한다."""

USD_SUFFIXES = (".usd", ".usda", ".usdc", ".usdz")
SCENE_SUFFIXES = (".hip", ".hipnc", ".hiplc", ".hipdef")


def suffix_of(path: Path) -> str:
    """확장자를 소문자로. `.bgeo.sc` 처럼 두 겹인 것을 한 덩어리로 본다."""
    name = path.name.lower()
    if name.endswith(".bgeo.sc"):
        return ".bgeo.sc"
    return path.suffix.lower()


# --------------------------------------------------------------------------
# 노드 해석
# --------------------------------------------------------------------------


def require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 부모 네트워크 안을 먼저 확인하세요."
        )
    return node


def require_sop(path: str) -> hou.SopNode:
    node = require_node(path)
    if not isinstance(node, hou.SopNode):
        raise ValueError(
            f"{path} 는 SOP 이 아니라 {node.type().category().name()} 노드입니다. "
            f"내보낼 지오메트리가 있는 SOP 경로를 주세요. 예: /obj/castle/wall_body"
        )
    return node


def cooked_geometry(node: hou.SopNode) -> hou.Geometry:
    """SOP 을 쿡해서 지오메트리를 꺼낸다. 쿡 실패는 노드 에러를 그대로 전한다."""
    try:
        node.cook()
    except hou.Error as exc:
        errors = " ".join(node.errors()) or str(exc)
        raise ValueError(
            f"{node.path()} ({node.type().name()}) 쿡에 실패해 내보낼 수 없습니다: "
            f"{errors} 파라미터와 입력 연결을 고친 뒤 다시 부르세요."
        ) from exc

    geo = node.geometry()
    if geo is None:
        raise ValueError(
            f"{node.path()} 에 지오메트리가 없습니다. "
            f"입력이 연결돼 있는지, 이 SOP 이 지오메트리를 내는지 확인하세요."
        )
    return geo


# --------------------------------------------------------------------------
# 라이선스
# --------------------------------------------------------------------------


def license_name() -> str:
    return str(hou.licenseCategory()).rsplit(".", 1)[-1]


def require_commercial(feature: str, tool_hint: str) -> None:
    """Apprentice 에서 막히는 익스포트를 미리 걸러낸다.

    실측: Apprentice 로 Alembic ROP 을 돌리면 "Alembic export is only supported
    in Houdini Core and Houdini FX versions", FBX ROP 은 "FBX export is not
    supported in Houdini Apprentice" 로 실패한다. 노드를 만들어 놓고 실패하느니
    먼저 알려 준다.
    """
    name = license_name()
    if name.startswith("Apprentice"):
        raise ValueError(
            f"{name} 라이선스는 {feature} 내보내기를 지원하지 않습니다. "
            f"{tool_hint} 를 쓰거나, Core/FX/Indie 라이선스로 여세요."
        )


# --------------------------------------------------------------------------
# 지오메트리 요약과 대조
# --------------------------------------------------------------------------


def bbox_dict(bbox: hou.BoundingBox) -> dict[str, list[float]]:
    if not bbox.isValid():
        return {"min": [], "max": [], "size": [], "center": []}
    lo, hi, size, center = bbox.minvec(), bbox.maxvec(), bbox.sizevec(), bbox.center()
    return {
        "min": [lo[0], lo[1], lo[2]],
        "max": [hi[0], hi[1], hi[2]],
        "size": [size[0], size[1], size[2]],
        "center": [center[0], center[1], center[2]],
    }


def geometry_summary(geo: hou.Geometry) -> dict[str, Any]:
    """내보내기 전후를 대조할 요약. 개수는 벌크 카운터로 얻어 점 루프를 피한다."""
    return {
        "points": geo.pointCount(),
        "prims": geo.primCount(),
        "vertices": geo.vertexCount(),
        "point_attribs": sorted(a.name() for a in geo.pointAttribs()),
        "prim_attribs": sorted(a.name() for a in geo.primAttribs()),
        "vertex_attribs": sorted(a.name() for a in geo.vertexAttribs()),
        "detail_attribs": sorted(a.name() for a in geo.globalAttribs()),
        "bbox": bbox_dict(geo.boundingBox()),
    }


COUNT_KEYS = ("points", "prims", "vertices")
ATTRIB_KEYS = ("point_attribs", "prim_attribs", "vertex_attribs", "detail_attribs")


def compare_summaries(
    expected: dict[str, Any], actual: dict[str, Any]
) -> list[dict[str, Any]]:
    """내보내려던 것과 다시 읽은 것의 차이. 빈 목록이면 완전히 같다."""
    issues: list[dict[str, Any]] = []
    for key in COUNT_KEYS:
        if expected[key] != actual[key]:
            issues.append(
                {"field": key, "expected": expected[key], "actual": actual[key]}
            )
    for key in ATTRIB_KEYS:
        lost = sorted(set(expected[key]) - set(actual[key]))
        if lost:
            issues.append({"field": key, "lost": lost})
    return issues


def verify_native_file(target: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """쓴 파일을 Houdini 로 다시 읽어 대조한다.

    파일이 생겼다는 것만으로는 아무것도 보장되지 않는다. 실제로 열어서 점·프림
    수와 어트리뷰트가 살아 있는지 본다.
    """
    result: dict[str, Any] = {"reread": False, "verified": False}
    if not target.is_file():
        result["error"] = "파일이 생기지 않았습니다."
        return result

    check = hou.Geometry()
    try:
        check.loadFromFile(str(target))
    except hou.Error as exc:
        result["error"] = f"다시 읽지 못했습니다: {exc}"
        return result

    actual = geometry_summary(check)
    lossy = suffix_of(target) in LOSSY_FORMATS
    issues = compare_summaries(expected, actual)
    empty = actual["points"] == 0 and actual["prims"] == 0

    result.update(
        {
            "reread": True,
            "lossy": lossy,
            "empty": empty,
            "actual": {key: actual[key] for key in COUNT_KEYS},
            "mismatches": issues,
            # 무손실 포맷은 완전 일치라야 통과다. 손실 포맷은 삼각화·어트리뷰트
            # 유실이 정상이라 델타를 참고로만 본다. 어느 쪽이든 **빈 파일은 통과가
            # 아니다** — 원본이 비어 있어서 그랬더라도, 아무것도 없는 파일을
            # 내보낸 것은 알려 줘야 한다.
            "verified": (not empty) and ((not issues) if not lossy else True),
        }
    )
    if empty:
        result["note"] = (
            "쓴 파일에 점도 프리미티브도 없습니다. 원본 SOP 이 비어 있는지, "
            "포맷이 이 지오메트리를 담을 수 있는지 확인하세요"
            "(.vdb 는 볼륨만, .stl 은 폴리곤만 담습니다)."
        )
    elif lossy and issues:
        result["note"] = (
            f"{suffix_of(target)} 는 왕복하면 수가 달라지는 것이 정상입니다"
            f"(.stl 은 삼각화, .obj/.ply 는 어트리뷰트 유실, .vdb 는 볼륨만). "
            f"mismatches 는 참고용입니다."
        )
    return result


# --------------------------------------------------------------------------
# 노드 생성 공통
# --------------------------------------------------------------------------


def require_comment(comment: str) -> None:
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 노드가 무엇을 위한 것인지 영어로 적어 주세요. "
            "Import scanned wall geometry from bgeo cache 처럼 구체적으로."
        )


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에도 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def temp_node(parent: hou.Node, node_type: str, purpose: str) -> hou.Node:
    """검증·내보내기용 임시 노드. 부른 쪽이 반드시 destroy 한다."""
    try:
        return parent.createNode(node_type)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent.path()} 안에 {node_type!r} 노드를 만들지 못해 {purpose} 를 "
            f"할 수 없습니다. ({exc})"
        ) from exc


def frame_list(frame_range: Sequence[float] | None) -> list[float] | None:
    """[start, end] 또는 [start, end, step] 을 프레임 목록으로."""
    if frame_range is None:
        return None
    values = [float(v) for v in frame_range]
    if len(values) == 2:
        values.append(1.0)
    if len(values) != 3:
        raise ValueError(
            f"frame_range 는 [start, end] 또는 [start, end, step] 이어야 합니다: "
            f"{list(frame_range)}"
        )
    start, end, step = values
    if step <= 0:
        raise ValueError(f"step 은 0 보다 커야 합니다: {step}")
    if end < start:
        raise ValueError(f"end 가 start 보다 작습니다: {start} ~ {end}")

    frames: list[float] = []
    current = start
    while current <= end + 1e-6 and len(frames) <= MAX_SEQUENCE_FILES:
        frames.append(round(current, 6))
        current += step
    return frames


def truncate(items: Iterable[Any], limit: int) -> tuple[list[Any], int]:
    """목록을 잘라 (보여줄 것, 전체 수) 로. 모델 컨텍스트를 태우지 않기 위해서."""
    collected = list(items)
    return collected[:limit], len(collected)
