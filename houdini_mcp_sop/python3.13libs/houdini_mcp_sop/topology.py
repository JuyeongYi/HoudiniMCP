"""토폴로지를 바꾸는 툴 — 변환·삼각화·리메시·감면·트랜스폼·삭제.

polyedit 와 같은 규약이다. 전후 통계를 비교해 돌려준다. 감면처럼 "얼마나
줄었나"가 곧 결과인 작업은 비교가 없으면 툴이 무의미하다.
"""

from __future__ import annotations

from typing import Any, Sequence

from houdini_mcp import tool, undoable

from ._common import build, geometry_at, report, set_menu, snapshot, vec3

_REDUCE_TARGETS = {
    "poly_percent": "percentage",
    "pt_percent": "percentage",
    "poly_count": "finalcount",
    "pt_count": "finalcount",
}


@tool()
@undoable("Convert geometry")
def convert_geometry(
    path: str,
    comment: str,
    to_type: str,
    from_type: str = "all",
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """프리미티브 타입을 바꾼다(Convert SOP).

    Primitive 구면·튜브를 폴리곤으로 풀거나, 폴리곤을 VDB/볼륨으로 바꿀 때 쓴다.
    바뀐 뒤 프림 종류별 개수를 돌려주므로 실제로 변환됐는지 바로 보인다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 바꾸는지. 필수. 영어로.
        to_type: poly / polySoup / mesh / nurbCurve / nurbSurf / bezCurve /
            bezSurf / volume / vdb 등. 잘못 주면 쓸 수 있는 값을 알려 준다.
        from_type: 바꿀 대상 타입. all 이면 전부.
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: convert_sphere_to_poly
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "convert", comment, name, parms={"group": group})
    set_menu(node, "fromtype", from_type)
    set_menu(node, "totype", to_type)

    result = report(node, before)
    if result["after"]["prim_types"] == before["prim_types"]:
        result.setdefault("notes", []).append(
            f"프림 종류가 그대로입니다. Convert SOP 이 {from_type} -> {to_type} 변환을 "
            f"하지 못한 것입니다. 폴리곤을 VDB/볼륨으로 만들려면 Convert 가 아니라 "
            f"vdbfrompolygons 나 isooffset 노드를 create_node 로 만드세요."
        )
    return result


@tool()
@undoable("Triangulate")
def triangulate(
    path: str,
    comment: str,
    max_sides: int = 3,
    avoid_slivers: bool = True,
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """폴리곤을 삼각형(또는 지정한 변 수 이하)으로 쪼갠다(Divide SOP).

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 삼각화하는지. 필수. 영어로.
        max_sides: 폴리곤 한 개의 최대 변 수. 3 이면 완전 삼각화.
        avoid_slivers: 가늘고 긴 삼각형이 나오지 않게 할지.
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: triangulate_for_export
    """
    if max_sides < 3:
        raise ValueError(f"max_sides 는 3 이상이어야 합니다: {max_sides}")

    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(
        source,
        "divide",
        comment,
        name,
        parms={
            "group": group,
            "convex": 1,
            # usemaxsides 를 끄면 Divide 는 "볼록하게"만 하고 사각형을 그대로 둔다.
            # 삼각형까지 쪼개려면 켜야 한다(실측: 끄면 6면체가 6프림 그대로).
            "usemaxsides": 1,
            "numsides": int(max_sides),
            "avoidsmallangles": int(bool(avoid_slivers)),
        },
    )
    return report(node, before)


@tool()
@undoable("Remesh")
def remesh_geometry(
    path: str,
    comment: str,
    target_size: float = 0.1,
    iterations: int = 3,
    smoothing: float = 0.2,
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """삼각형 크기를 고르게 다시 짠다(Remesh SOP).

    입력의 평균 에지 길이를 함께 돌려주므로, target_size 를 얼마로 줄지
    다음 호출에서 근거를 갖고 정할 수 있다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 리메시하는지. 필수. 영어로.
        target_size: 목표 에지 길이. 작을수록 촘촘하고 무겁다.
        iterations: 반복 횟수. 클수록 고르지만 느리다.
        smoothing: 스무딩 정도 0~1. 크면 형태가 뭉개진다.
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: remesh_rock_surface
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)
    input_edge = float(geo.averageEdgeLength()) if geo.primCount() else 0.0

    node = build(
        source,
        "remesh",
        comment,
        name,
        parms={
            "group": group,
            "targetsize": float(target_size),
            "iterations": int(iterations),
            "smoothing": float(smoothing),
        },
    )
    result = report(node, before)
    result["average_edge_length"] = {
        "before": input_edge,
        "after": float(node.geometry().averageEdgeLength())
        if result["after"]["prims"]
        else 0.0,
        "target": float(target_size),
    }
    return result


@tool()
@undoable("Reduce polygons")
def reduce_polygons(
    path: str,
    comment: str,
    target: float,
    mode: str = "poly_percent",
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """폴리곤 수를 줄인다(PolyReduce SOP).

    실제로 얼마나 줄었는지(요청 대비 결과)를 돌려준다. PolyReduce 는 요청한
    수치에 정확히 맞추지 못할 때가 있으므로 결과를 봐야 한다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 줄이는지. 필수. 영어로.
        target: mode 가 percent 계열이면 퍼센트(0~100), count 계열이면 개수.
        mode: poly_percent / pt_percent / poly_count / pt_count.
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: reduce_rock_lod1
    """
    if mode not in _REDUCE_TARGETS:
        raise ValueError(
            f"mode {mode!r} 는 모릅니다. 쓸 수 있는 값: {', '.join(_REDUCE_TARGETS)}"
        )

    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "polyreduce::2.0", comment, name, parms={"group": group})
    set_menu(node, "target", mode)
    parm_name = _REDUCE_TARGETS[mode]
    node.parm(parm_name).set(float(target) if parm_name == "percentage" else int(target))

    result = report(node, before)
    measured = "prims" if mode.startswith("poly") else "points"
    achieved = result["after"][measured]
    requested = (
        before[measured] * float(target) / 100.0 if "percent" in mode else float(target)
    )
    result["reduction"] = {
        "mode": mode,
        "requested": requested,
        "achieved": achieved,
        "ratio": (achieved / before[measured]) if before[measured] else 0.0,
    }
    return result


@tool()
@undoable("Transform geometry")
def transform_geometry(
    path: str,
    comment: str,
    translate: Sequence[float] | None = None,
    rotate: Sequence[float] | None = None,
    scale: Sequence[float] | None = None,
    pivot: Sequence[float] | None = None,
    group: str = "",
    group_type: str = "guess",
    name: str | None = None,
) -> dict[str, Any]:
    """지오메트리(또는 그 일부)를 옮기고 돌리고 키운다(Transform SOP).

    오브젝트 레벨 트랜스폼과 다르다. 여기서 거는 것은 점 좌표 자체다.
    바운딩 박스가 전후로 어떻게 변했는지 돌려주므로 방향이 맞는지 바로 보인다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 옮기는지. 필수. 영어로.
        translate: 이동 (x,y,z).
        rotate: 회전 (rx,ry,rz) 도 단위.
        scale: 배율 (sx,sy,sz).
        pivot: 회전·배율의 기준점 (x,y,z).
        group: 대상 패턴. 비우면 전부.
        group_type: guess / points / prims / edges / breakpoints.
        name: 노드 이름. 예: place_tower_northwest
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    tx, ty, tz = vec3(translate, (0.0, 0.0, 0.0))
    rx, ry, rz = vec3(rotate, (0.0, 0.0, 0.0))
    sx, sy, sz = vec3(scale, (1.0, 1.0, 1.0))
    px, py, pz = vec3(pivot, (0.0, 0.0, 0.0))

    node = build(
        source,
        "xform",
        comment,
        name,
        parms={
            "group": group,
            "tx": tx, "ty": ty, "tz": tz,
            "rx": rx, "ry": ry, "rz": rz,
            "sx": sx, "sy": sy, "sz": sz,
            "px": px, "py": py, "pz": pz,
        },
    )
    set_menu(node, "grouptype", group_type)
    return report(node, before)


@tool()
@undoable("Delete geometry")
def delete_geometry(
    path: str,
    comment: str,
    group: str,
    group_type: str = "guess",
    keep_selected: bool = False,
    delete_unused_points: bool = True,
    name: str | None = None,
) -> dict[str, Any]:
    """그룹이나 패턴에 걸린 것을 지운다(Blast SOP).

    keep_selected=True 면 반대로 걸린 것만 남긴다. 지운 뒤 몇 개가 남았는지
    돌려주므로 패턴이 의도대로 잡혔는지 바로 보인다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 지우는지. 필수. 영어로.
        group: 지울 대상 그룹 이름 또는 패턴. 예: "@name=debris*", "0-5"
        group_type: guess / points / prims / edges / breakpoints.
        keep_selected: True 면 걸린 것만 남기고 나머지를 지운다.
        delete_unused_points: 프림을 지운 뒤 남은 외톨이 점도 지울지.
        name: 노드 이름. 예: remove_inner_faces
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(
        source,
        "blast",
        comment,
        name,
        parms={
            "group": group,
            "negate": int(bool(keep_selected)),
            "removegrp": int(bool(delete_unused_points)),
        },
    )
    set_menu(node, "grouptype", group_type)
    return report(node, before)
