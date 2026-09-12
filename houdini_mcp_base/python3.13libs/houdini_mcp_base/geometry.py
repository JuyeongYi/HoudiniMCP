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


PRIM_TYPES = tuple(
    (name, getattr(hou.primType, name))
    for name in dir(hou.primType)
    if not name.startswith("_") and name != "thisown"
)
"""hou.primType 의 멤버 전부. countPrimType 이 받지 않는 것은 호출 때 걸러진다."""

_COUNTS = {
    "point": "pointCount",
    "prim": "primCount",
    "vertex": "vertexCount",
}

_BULK = {
    (hou.attribData.Float, "point"): "pointFloatAttribValues",
    (hou.attribData.Int, "point"): "pointIntAttribValues",
    (hou.attribData.String, "point"): "pointStringAttribValues",
    (hou.attribData.Float, "prim"): "primFloatAttribValues",
    (hou.attribData.Int, "prim"): "primIntAttribValues",
    (hou.attribData.String, "prim"): "primStringAttribValues",
    (hou.attribData.Float, "vertex"): "vertexFloatAttribValues",
    (hou.attribData.Int, "vertex"): "vertexIntAttribValues",
    (hou.attribData.String, "vertex"): "vertexStringAttribValues",
}


def _attribs_of(geo: hou.Geometry, owner: str):
    """에러 메시지에서 "있는 것" 을 보여 주려고 쓴다."""
    return {
        "point": geo.pointAttribs,
        "prim": geo.primAttribs,
        "vertex": geo.vertexAttribs,
        "detail": geo.globalAttribs,
    }[owner]()


def _element_count(geo: hou.Geometry, owner: str) -> int:
    """요소 수. points() 를 만들지 않고 센다 - 점 10만 개에서 차이가 크다."""
    return getattr(geo, _COUNTS[owner])()


def _prim_type_counts(geo: hou.Geometry) -> dict[str, int]:
    """프리미티브 종류별 개수.

    countPrimType 은 C++ 에서 세므로 프리미티브 수와 무관하게 일정하다.
    파이썬으로 prims() 를 돌면 프림 수에 비례한다(실측: 6,144 프림에서
    11.7ms 대 0.3ms).
    """
    counts: dict[str, int] = {}
    for name, value in PRIM_TYPES:
        try:
            total = geo.countPrimType(value)
        except TypeError:
            # Unknown 처럼 셀 수 없는 멤버가 섞여 있다.
            continue
        if total:
            counts[name] = total
    return counts


def _bulk_values(
    geo: hou.Geometry, owner: str, attrib: hou.Attrib, start: int, count: int
) -> tuple[int, list[Any]]:
    """어트리뷰트 값을 벌크로 읽어 (전체 개수, 잘라낸 값들) 을 돌려준다.

    요소 하나씩 attribValue 를 부르지 않는다. 평평한 배열을 한 번에 받아
    성분 수(size)로 묶는다.
    """
    getter = _BULK.get((attrib.dataType(), owner))
    if getter is None:
        raise ValueError(
            f"{owner} 어트리뷰트 {attrib.name()!r} 는 {attrib.dataType()} 타입이라 "
            f"벌크로 읽을 수 없습니다. run_python 으로 직접 읽으세요."
        )

    flat = getattr(geo, getter)(attrib.name())
    size = attrib.size()
    total = _element_count(geo, owner)
    chunk = flat[start * size : (start + count) * size]
    if size == 1:
        return total, list(chunk)
    return total, [list(chunk[i : i + size]) for i in range(0, len(chunk), size)]


@tool()
def geometry_stats(path: str) -> dict[str, Any]:
    """SOP 의 포인트·프리미티브·버텍스 수와 바운딩 박스.

    만든 것이 의도한 크기·개수인지 확인할 때 쓴다.

    Args:
        path: SOP 노드 경로. 예: /obj/castle/castle_wall
    """
    geo = _geometry(path)
    return {
        "path": path,
        "points": geo.pointCount(),
        "prims": geo.primCount(),
        "vertices": geo.vertexCount(),
        "prim_types": _prim_type_counts(geo),
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
    total = geo.pointCount()
    if start < 0 or (total and start >= total):
        raise ValueError(f"start 가 범위를 벗어났습니다: {start} (포인트 {total}개)")

    # points() 로 Point 객체를 전부 만들지 않는다. P 만 평평하게 받아 자른다.
    flat = geo.pointFloatAttribValues("P")
    chunk = flat[start * 3 : (start + count) * 3]
    return {
        "path": path,
        "total": total,
        "start": start,
        "points": [
            {"number": start + i, "P": list(chunk[i * 3 : i * 3 + 3])}
            for i in range(len(chunk) // 3)
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
        owner: point / prim / vertex / detail 중 하나. UV 는 보통 vertex 다.
        count: 읽을 개수. 최대 200. detail 은 하나뿐이라 무시된다.
        start: 몇 번째부터 읽을지.
    """
    if count < 1 or count > MAX_SAMPLE:
        raise ValueError(f"count 는 1 이상 {MAX_SAMPLE} 이하여야 합니다: {count}")

    geo = _geometry(path)
    finders = {
        "point": geo.findPointAttrib,
        "prim": geo.findPrimAttrib,
        "vertex": geo.findVertexAttrib,
        "detail": geo.findGlobalAttrib,
    }
    if owner not in finders:
        raise ValueError(f"owner 는 {', '.join(finders)} 중 하나여야 합니다: {owner!r}")

    attrib = finders[owner](name)
    if attrib is None:
        have = [a.name() for a in _attribs_of(geo, owner)]
        raise ValueError(
            f"{path} 에 {owner} 어트리뷰트 {name!r} 가 없습니다. "
            f"있는 것: {', '.join(have) if have else '없음'}"
        )

    if owner == "detail":
        return {"path": path, "name": name, "owner": owner, "value": geo.attribValue(name)}

    if start < 0:
        raise ValueError(f"start 는 0 이상이어야 합니다: {start}")

    total, values = _bulk_values(geo, owner, attrib, start, count)
    return {
        "path": path,
        "name": name,
        "owner": owner,
        "size": attrib.size(),
        "total": total,
        "start": start,
        "values": values,
    }
