"""지오메트리를 들여다보는 툴들.

만든 결과가 수치로 맞는지 확인할 때 쓴다. 눈으로 보는 것은 viewport 모듈의
viewport_snapshot 이 맡는다.

SOP 전용이 아니다. `geometry()` 를 가진 노드면 무엇이든 받으므로 DOP 등
다른 컨텍스트에서도 쓸 수 있다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

MAX_SAMPLE = 200
"""한 번에 돌려줄 포인트 수 상한. 더 많으면 응답만 무거워지고 읽히지 않는다."""


def _geometry(path: str) -> hou.Geometry:
    """SOP 노드의 지오메트리를 얻는다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")

    getter = getattr(node, "geometry", None)
    if getter is None:
        raise ValueError(
            f"{path} 에는 지오메트리가 없습니다. SOP 경로를 주세요. "
            f"(이 노드는 {node.type().category().name()} 입니다)"
        )
    geo = getter()
    if geo is None:
        raise ValueError(
            f"{path} 의 지오메트리를 읽지 못했습니다. 노드가 쿡되지 않았을 수 있습니다."
        )
    return geo


def _bbox_dict(bbox: hou.BoundingBox) -> dict[str, list[float]]:
    minvec, maxvec = bbox.minvec(), bbox.maxvec()
    size = bbox.sizevec()
    center = bbox.center()
    return {
        "min": [minvec[0], minvec[1], minvec[2]],
        "max": [maxvec[0], maxvec[1], maxvec[2]],
        "size": [size[0], size[1], size[2]],
        "center": [center[0], center[1], center[2]],
    }


@tool()
def geometry_stats(path: str) -> dict[str, Any]:
    """SOP 의 포인트·프리미티브·버텍스 수와 바운딩 박스.

    만든 것이 의도한 크기·개수인지 확인할 때 쓴다.

    Args:
        path: SOP 노드 경로. 예: /obj/castle/castle_wall
    """
    geo = _geometry(path)

    prim_types: dict[str, int] = {}
    for prim in geo.prims():
        name = prim.type().name()
        prim_types[name] = prim_types.get(name, 0) + 1

    return {
        "path": path,
        "points": len(geo.points()),
        "prims": len(geo.prims()),
        "vertices": sum(len(prim.vertices()) for prim in geo.prims()),
        "prim_types": prim_types,
        "bbox": _bbox_dict(geo.boundingBox()),
    }


@tool()
def list_attributes(path: str) -> dict[str, list[dict[str, Any]]]:
    """지오메트리의 어트리뷰트를 종류별로 나열한다.

    Args:
        path: SOP 노드 경로.
    """
    geo = _geometry(path)

    def describe(attribs) -> list[dict[str, Any]]:
        out = []
        for attrib in attribs:
            entry: dict[str, Any] = {
                "name": attrib.name(),
                "type": str(attrib.dataType()).rsplit(".", 1)[-1],
                "size": attrib.size(),
            }
            qualifier = attrib.qualifier()
            if qualifier:
                entry["qualifier"] = qualifier
            out.append(entry)
        return out

    return {
        "point": describe(geo.pointAttribs()),
        "prim": describe(geo.primAttribs()),
        "vertex": describe(geo.vertexAttribs()),
        "detail": describe(geo.globalAttribs()),
    }


@tool()
def list_groups(path: str) -> dict[str, list[dict[str, Any]]]:
    """지오메트리의 그룹을 종류별로 나열한다.

    Args:
        path: SOP 노드 경로.
    """
    geo = _geometry(path)
    return {
        "point": [{"name": g.name(), "count": len(g.points())} for g in geo.pointGroups()],
        "prim": [{"name": g.name(), "count": len(g.prims())} for g in geo.primGroups()],
        "edge": [{"name": g.name()} for g in geo.edgeGroups()],
    }


@tool()
def sample_points(path: str, count: int = 10, start: int = 0) -> dict[str, Any]:
    """포인트 좌표를 몇 개 뽑아 본다.

    통계만으로는 알 수 없는 배치를 확인할 때 쓴다.

    Args:
        path: SOP 노드 경로.
        count: 뽑을 개수. 최대 200.
        start: 몇 번째 포인트부터 뽑을지.
    """
    if count < 1:
        raise ValueError(f"count 는 1 이상이어야 합니다: {count}")
    if count > MAX_SAMPLE:
        raise ValueError(f"count 는 {MAX_SAMPLE} 이하여야 합니다: {count}")

    geo = _geometry(path)
    points = geo.points()
    total = len(points)
    if start < 0 or (total and start >= total):
        raise ValueError(f"start 가 범위를 벗어났습니다: {start} (포인트 {total}개)")

    chosen = points[start : start + count]
    return {
        "path": path,
        "total": total,
        "start": start,
        "points": [
            {"number": p.number(), "P": [p.position()[0], p.position()[1], p.position()[2]]}
            for p in chosen
        ],
    }


@tool()
def attribute_values(
    path: str, name: str, owner: str = "point", count: int = 10, start: int = 0
) -> dict[str, Any]:
    """어트리뷰트 값을 몇 개 읽어 본다.

    Args:
        path: SOP 노드 경로.
        name: 어트리뷰트 이름. 예: P, Cd, name
        owner: point / prim / vertex / detail 중 하나.
        count: 읽을 개수. 최대 200. detail 은 하나뿐이라 무시된다.
        start: 몇 번째부터 읽을지.
    """
    if count < 1 or count > MAX_SAMPLE:
        raise ValueError(f"count 는 1 이상 {MAX_SAMPLE} 이하여야 합니다: {count}")

    geo = _geometry(path)
    owners = {
        "point": (geo.points, geo.findPointAttrib),
        "prim": (geo.prims, geo.findPrimAttrib),
        "vertex": (None, geo.findVertexAttrib),
        "detail": (None, geo.findGlobalAttrib),
    }
    if owner not in owners:
        raise ValueError(f"owner 는 {', '.join(owners)} 중 하나여야 합니다: {owner!r}")

    elements_fn, find = owners[owner]
    if find(name) is None:
        raise ValueError(f"{path} 에 {owner} 어트리뷰트 {name!r} 가 없습니다.")

    if owner == "detail":
        return {"path": path, "name": name, "owner": owner, "value": geo.attribValue(name)}
    if elements_fn is None:
        raise ValueError("vertex 어트리뷰트 읽기는 아직 지원하지 않습니다.")

    elements = elements_fn()
    chosen = elements[start : start + count]
    return {
        "path": path,
        "name": name,
        "owner": owner,
        "total": len(elements),
        "start": start,
        "values": [element.attribValue(name) for element in chosen],
    }
