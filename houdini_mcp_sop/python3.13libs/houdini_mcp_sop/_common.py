"""팩 전체가 쓰는 헬퍼. 툴은 여기 없다.

세 가지를 모아 뒀다.

1. **노드 해석과 스냅샷** — SOP 경로를 받아 지오메트리를 꺼내고, 포인트·프림 수와
   바운딩 박스를 찍는다.
2. **조립과 리포트** — 입력 SOP 옆에 노드를 만들어 잇고, 쿡해서 전후를 비교한
   결과를 만든다. 이 팩의 조작 툴은 전부 이 경로를 탄다.
3. **벌크 어트리뷰트 읽기** — `*AsString` 접근자로 바이트를 받아 numpy 로 꽂는다.
   파이썬 점 루프를 돌지 않는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import hou
import numpy

Vec3 = Sequence[float]

# 벌크 접근자 이름표. owner 이름 -> (원소 수 메서드, float 바이트, int 바이트,
# 문자열 튜플, 어트리뷰트 검색)
_BULK = {
    "point": (
        "pointCount",
        "pointFloatAttribValuesAsString",
        "pointIntAttribValuesAsString",
        "pointStringAttribValues",
        "findPointAttrib",
    ),
    "prim": (
        "primCount",
        "primFloatAttribValuesAsString",
        "primIntAttribValuesAsString",
        "primStringAttribValues",
        "findPrimAttrib",
    ),
    "vertex": (
        "vertexCount",
        "vertexFloatAttribValuesAsString",
        "vertexIntAttribValuesAsString",
        "vertexStringAttribValues",
        "findVertexAttrib",
    ),
}

OWNERS = tuple(_BULK) + ("detail",)


# --------------------------------------------------------------------------
# 노드 해석과 스냅샷
# --------------------------------------------------------------------------


def require_sop(path: str) -> hou.SopNode:
    """SOP 노드를 얻는다. 아니면 무엇을 주면 되는지 알려 주고 실패한다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 부모 네트워크 안을 먼저 확인하세요."
        )
    if not isinstance(node, hou.SopNode):
        raise ValueError(
            f"{path} 는 SOP 이 아니라 {node.type().category().name()} 노드입니다. "
            f"SOP 경로를 주세요. 예: /obj/castle/wall_body"
        )
    return node


def geometry_of(node: hou.SopNode) -> hou.Geometry:
    """SOP 을 쿡해서 지오메트리를 꺼낸다. 쿡 실패는 노드 에러를 그대로 전한다."""
    try:
        node.cook()
    except hou.Error as exc:
        raise ValueError(_cook_failure(node, exc)) from exc

    geo = node.geometry()
    if geo is None:
        raise ValueError(
            f"{node.path()} 의 지오메트리를 읽지 못했습니다. "
            f"{_errors_text(node) or '입력이 연결돼 있는지 확인하세요.'}"
        )
    return geo


def geometry_at(path: str) -> tuple[hou.SopNode, hou.Geometry]:
    """경로 하나로 노드와 지오메트리를 함께 얻는다."""
    node = require_sop(path)
    return node, geometry_of(node)


def _cook_failure(node: hou.SopNode, exc: Exception) -> str:
    detail = _errors_text(node) or str(exc)
    return (
        f"{node.path()} ({node.type().name()}) 쿡에 실패했습니다: {detail} "
        f"파라미터와 입력 연결을 고친 뒤 다시 부르세요."
    )


def _errors_text(node: hou.SopNode) -> str:
    try:
        return " ".join(node.errors())
    except hou.Error:
        return ""


def bbox_dict(bbox: hou.BoundingBox) -> dict[str, list[float]]:
    """바운딩 박스를 JSON 으로 낼 수 있는 모양으로."""
    if bbox.isValid():
        minvec, maxvec = bbox.minvec(), bbox.maxvec()
        size, center = bbox.sizevec(), bbox.center()
        return {
            "min": [minvec[0], minvec[1], minvec[2]],
            "max": [maxvec[0], maxvec[1], maxvec[2]],
            "size": [size[0], size[1], size[2]],
            "center": [center[0], center[1], center[2]],
        }
    return {"min": [], "max": [], "size": [], "center": []}


def snapshot(geo: hou.Geometry) -> dict[str, Any]:
    """전후 비교에 쓸 요약. 개수는 벌크 카운터로 얻어 점 루프를 피한다."""
    return {
        "points": geo.pointCount(),
        "prims": geo.primCount(),
        "vertices": geo.vertexCount(),
        "prim_types": prim_type_counts(geo),
        "bbox": bbox_dict(geo.boundingBox()),
    }


def prim_type_counts(geo: hou.Geometry) -> dict[str, int]:
    """프림 종류별 개수. hou.primType 을 훑어 countPrimType 으로 센다.

    `for prim in geo.prims()` 로 세면 프림 10만 개에 파이썬 루프가 돈다.
    countPrimType 은 C++ 쪽에서 센다.
    """
    counts: dict[str, int] = {}
    for name in dir(hou.primType):
        if name.startswith("_") or name == "thisown":
            continue
        value = getattr(hou.primType, name)
        try:
            n = geo.countPrimType(value)
        except (hou.Error, TypeError):
            continue
        if n:
            counts[name] = n
    return counts


def open_edge_count(geo: hou.Geometry) -> int:
    """열린(공유되지 않은) 에지 개수. 0 이면 닫힌 메시다.

    씬에 노드를 만들지 않고 SOP verb 로 계산한다. groupcreate verb 를 독립
    지오메트리에 돌리므로 사용자의 네트워크가 더러워지지 않는다.
    """
    verb = hou.sopNodeTypeCategory().nodeVerb("groupcreate")
    verb.setParms(
        {
            "groupname": "open_edges",
            "grouptype": 2,  # edges
            "groupbase": 0,
            "groupedges": 1,
            "unshared": 1,
        }
    )
    out = hou.Geometry()
    verb.execute(out, [geo])
    group = out.findEdgeGroup("open_edges")
    return group.edgeCount() if group is not None else 0


# --------------------------------------------------------------------------
# 조립과 리포트
# --------------------------------------------------------------------------


def build(
    source: hou.SopNode,
    node_type: str,
    comment: str,
    name: str | None = None,
    parms: dict[str, Any] | None = None,
    extra_inputs: Sequence[hou.SopNode] = (),
) -> hou.SopNode:
    """입력 SOP 옆에 노드를 만들어 잇는다.

    코멘트를 달고 네트워크 뷰에 보이게 하며, 디스플레이/렌더 플래그를 새 노드로
    옮긴다. 새 노드가 체인의 끝이 되기 때문이다.
    """
    require_comment(comment)

    parent = source.parent()
    try:
        node = parent.createNode(node_type, node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent.path()} 안에 {node_type!r} 노드를 만들지 못했습니다. "
            f"node_type_info 로 그 네트워크에서 쓸 수 있는 타입인지 확인하세요. ({exc})"
        ) from exc

    node.setFirstInput(source)
    for index, extra in enumerate(extra_inputs, start=1):
        node.setInput(index, extra)

    set_comment(node, comment)
    if parms:
        set_parms(node, parms)

    try:
        node.moveToGoodPosition()
    except hou.Error:
        # 배치는 결과에 영향이 없다. 실패해도 툴을 실패시키지 않는다.
        pass
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return node


def require_comment(comment: str) -> None:
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 노드가 무엇을 위한 것인지 영어로 적어 주세요. "
            'Bevel wall top edges, 0.05 offset 처럼 구체적으로.'
        )


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def set_parms(node: hou.Node, parms: dict[str, Any]) -> None:
    """값이 None 인 것은 건너뛴다. 벡터는 parmTuple 로 건다."""
    for name, value in parms.items():
        if value is None:
            continue
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
            continue
        tuple_parm = node.parmTuple(name)
        if tuple_parm is None:
            raise ValueError(
                f"{node.type().name()} 에 파라미터 {name!r} 가 없습니다. "
                f"list_parms 로 이 노드의 파라미터 이름을 확인하세요."
            )
        tuple_parm.set(tuple(value))


def set_menu(node: hou.Node, parm_name: str, token: str) -> None:
    """메뉴 파라미터를 토큰으로 건다. 잘못된 값이면 쓸 수 있는 값을 알려 준다.

    메뉴를 가진 파라미터가 전부 토큰을 받는 것은 아니다. `hou.MenuParmTemplate`
    은 받지만 메뉴가 달린 `hou.IntParmTemplate`(Normal SOP 의 method 가 그렇다)은
    숫자만 받는다. 그래서 실패하면 메뉴 인덱스로 다시 건다.
    """
    parm = node.parm(parm_name)
    if parm is None:
        raise ValueError(f"{node.type().name()} 에 파라미터 {parm_name!r} 가 없습니다.")
    items = parm.parmTemplate().menuItems()
    usable = [item for item in items if item != "_separator_"]
    if token not in usable:
        raise ValueError(
            f"{parm_name} 에 {token!r} 은 쓸 수 없습니다. "
            f"쓸 수 있는 값: {', '.join(usable)}"
        )
    try:
        parm.set(token)
    except TypeError:
        parm.set(items.index(token))


def same_network(first: hou.Node, second: hou.Node) -> bool:
    """두 노드가 같은 네트워크에 있는지. 경로로 비교한다.

    HOM 은 같은 노드에도 매번 새 래퍼 객체를 준다. `is` 나 `==` 로 부모를
    비교하면 항상 다르다고 나온다.
    """
    return first.parent().path() == second.parent().path()


def report(
    node: hou.SopNode, before: dict[str, Any], extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """만든 노드를 쿡해서 전후를 비교한 결과를 만든다.

    조작 툴이 `{"ok": true}` 대신 돌려주는 것이 이것이다. 모델이 결과를 보고
    다음을 정할 수 있어야 한다.
    """
    geo = geometry_of(node)
    after = snapshot(geo)
    result: dict[str, Any] = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "before": before,
        "after": after,
        "delta": {
            key: after[key] - before[key] for key in ("points", "prims", "vertices")
        },
        "warnings": list(node.warnings()),
    }
    if extra:
        result.update(extra)
    return result


# --------------------------------------------------------------------------
# 벌크 어트리뷰트 읽기
# --------------------------------------------------------------------------


def find_attrib(geo: hou.Geometry, owner: str, name: str) -> hou.Attrib:
    """어트리뷰트를 찾는다. 없으면 그 owner 에 무엇이 있는지 알려 준다."""
    if owner == "detail":
        attrib = geo.findGlobalAttrib(name)
        existing = [a.name() for a in geo.globalAttribs()]
    else:
        if owner not in _BULK:
            raise ValueError(
                f"owner 는 {', '.join(OWNERS)} 중 하나여야 합니다: {owner!r}"
            )
        attrib = getattr(geo, _BULK[owner][4])(name)
        existing = [a.name() for a in _owner_attribs(geo, owner)]
    if attrib is None:
        raise ValueError(
            f"{owner} 어트리뷰트 {name!r} 가 없습니다. "
            f"이 지오메트리의 {owner} 어트리뷰트: {', '.join(existing) or '(없음)'}"
        )
    return attrib


def _owner_attribs(geo: hou.Geometry, owner: str) -> Iterable[hou.Attrib]:
    return {
        "point": geo.pointAttribs,
        "prim": geo.primAttribs,
        "vertex": geo.vertexAttribs,
    }[owner]()


def element_count(geo: hou.Geometry, owner: str) -> int:
    return int(getattr(geo, _BULK[owner][0])())


def attrib_array(geo: hou.Geometry, owner: str, name: str) -> numpy.ndarray:
    """수치 어트리뷰트를 numpy 배열로. 문자열 어트리뷰트는 여기로 오지 않는다.

    `*AsString` 으로 바이트를 통째로 받아 `numpy.frombuffer` 로 꽂는다.
    `pointFloatAttribValues` 보다 빠르고, 파이썬 튜플을 거치지 않는다.
    """
    attrib = find_attrib(geo, owner, name)
    data_type = attrib.dataType()
    float_getter = getattr(geo, _BULK[owner][1])
    int_getter = getattr(geo, _BULK[owner][2])

    if data_type == hou.attribData.Float:
        raw = float_getter(name, hou.numericData.Float32)
        array = numpy.frombuffer(raw, dtype=numpy.float32)
    elif data_type == hou.attribData.Int:
        raw = int_getter(name, hou.numericData.Int32)
        array = numpy.frombuffer(raw, dtype=numpy.int32)
    else:
        raise ValueError(
            f"{name!r} 는 {str(data_type).rsplit('.', 1)[-1]} 어트리뷰트라 통계를 낼 수 "
            f"없습니다. 수치(Float/Int) 어트리뷰트를 주세요."
        )

    size = attrib.size()
    return array.reshape(-1, size) if size > 1 else array.reshape(-1, 1)


def summarize(array: numpy.ndarray, bins: int = 16) -> dict[str, Any]:
    """성분별 통계와 히스토그램. 원본을 그대로 돌려주지 않는다.

    성분이 여럿이면 크기(L2 노름)에도 통계를 내고 히스토그램은 크기로 낸다.
    벡터를 성분별 히스토그램 3개로 보내면 읽히지 않는다.
    """
    count, size = array.shape
    if count == 0:
        return {"count": 0, "size": size, "components": [], "histogram": None}

    data = array.astype(numpy.float64, copy=False)
    components = [_component_stats(data[:, i], i) for i in range(size)]

    result: dict[str, Any] = {
        "count": int(count),
        "size": int(size),
        "components": components,
    }

    source = numpy.linalg.norm(data, axis=1) if size > 1 else data[:, 0]
    if size > 1:
        result["magnitude"] = _component_stats(source, None)
    result["histogram"] = _histogram(source, bins)
    return result


def _component_stats(values: numpy.ndarray, index: int | None) -> dict[str, Any]:
    quantiles = numpy.quantile(values, [0.05, 0.25, 0.5, 0.75, 0.95])
    stats: dict[str, Any] = {
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std()),
        "quantiles": {
            "p05": float(quantiles[0]),
            "p25": float(quantiles[1]),
            "p50": float(quantiles[2]),
            "p75": float(quantiles[3]),
            "p95": float(quantiles[4]),
        },
    }
    if index is not None:
        stats["index"] = index
    return stats


def _histogram(values: numpy.ndarray, bins: int) -> dict[str, Any]:
    low, high = float(values.min()), float(values.max())
    if low == high:
        return {"edges": [low, high], "counts": [int(values.size)], "constant": True}
    counts, edges = numpy.histogram(values, bins=bins, range=(low, high))
    return {
        "edges": [float(e) for e in edges],
        "counts": [int(c) for c in counts],
        "constant": False,
    }


def vec3(value: Vec3 | None, default: tuple[float, float, float]) -> tuple[float, ...]:
    """길이 3 시퀀스를 확인한다. 길이가 틀리면 무엇을 줘야 하는지 알려 준다."""
    if value is None:
        return default
    if len(value) != 3:
        raise ValueError(
            f"값 3개(x, y, z)가 필요합니다. 받은 것: {list(value)} ({len(value)}개)"
        )
    return tuple(float(v) for v in value)
