"""지오메트리를 처음부터 만드는 툴.

입력이 없는 생성 노드라 `_common.build` 를 쓰지 않고 직접 만든다. 만든 뒤
쿡해서 결과 통계를 돌려주는 것은 같다 — 원뿔이 뒤집혔는지, 점이 몇 개 나왔는지
모델이 다시 묻지 않아도 되어야 한다.

노드 이름은 역할이 드러나게 짓는다. box1, geo2 같은 기본 이름을 쓰지 않는다.
"""

from __future__ import annotations

from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from ._common import (
    geometry_of,
    report,
    require_comment,
    require_sop,
    same_network,
    set_comment,
    set_menu,
    set_parms,
    snapshot,
    vec3,
)

# 셰이프 이름 -> (노드 타입, 크기 파라미터 이름들, 분할 파라미터 이름들)
# 크기 파라미터가 노드마다 다르다. box 는 sizex/sizey/sizez, sphere 는
# radx/rady/radz, tube 는 rad1/rad2/height 다. 하나로 묶어 두면 모델이
# 노드마다 다른 이름을 외우지 않아도 된다.
_SHAPES: dict[str, dict[str, Any]] = {
    "box": {"type": "box", "size": ("sizex", "sizey", "sizez"), "divs": ("divsx", "divsy", "divsz")},
    "sphere": {"type": "sphere", "size": ("radx", "rady", "radz"), "divs": ("rows", "cols")},
    "tube": {"type": "tube", "size": ("rad1", "rad2", "height"), "divs": ("rows", "cols")},
    "grid": {"type": "grid", "size": ("sizex", "sizey"), "divs": ("rows", "cols")},
    "torus": {"type": "torus", "size": ("radx", "rady"), "divs": ("rows", "cols")},
    "circle": {"type": "circle", "size": ("radx", "rady"), "divs": ("divs",)},
    "platonic": {"type": "platonic", "size": ("radius",), "divs": ()},
}

# platonic 의 type 메뉴는 숫자 토큰('0'..'6')이라 이름으로 못 건다. 이름을 받아
# 토큰으로 바꿔 준다.
_PLATONIC = {
    "tetrahedron": "0",
    "cube": "1",
    "octahedron": "2",
    "icosahedron": "3",
    "dodecahedron": "4",
    "soccerball": "5",
    "teapot": "6",
}

_CURVE_TYPES = {"poly": None, "nurbs": "nurbCurve", "bezier": "bezCurve"}


def _require_network(parent: str) -> hou.Node:
    node = hou.node(parent)
    if node is None:
        raise ValueError(
            f"그런 네트워크가 없습니다: {parent}. "
            f"SOP 을 담을 부모를 주세요. 예: /obj/castle"
        )
    if node.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError(
            f"{parent} 안에는 SOP 을 만들 수 없습니다 "
            f"(자식 카테고리: {node.childTypeCategory().name()}). "
            f"Geometry 오브젝트(/obj 아래 geo 노드) 경로를 주세요."
        )
    return node


def _finish(node: hou.SopNode, comment: str) -> dict[str, Any]:
    """만든 생성 노드를 마무리하고 결과 통계를 붙인다."""
    set_comment(node, comment)
    try:
        node.moveToGoodPosition()
    except hou.Error:
        pass
    node.setDisplayFlag(True)
    node.setRenderFlag(True)

    geo = geometry_of(node)
    return {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "result": snapshot(geo),
        "warnings": list(node.warnings()),
    }


@tool()
@undoable("Create primitive")
def create_primitive(
    parent: str,
    shape: str,
    comment: str,
    name: str | None = None,
    size: Sequence[float] | None = None,
    center: Sequence[float] | None = None,
    rotate: Sequence[float] | None = None,
    divisions: Sequence[int] | None = None,
    prim_type: str = "poly",
    platonic_solid: str = "cube",
) -> dict[str, Any]:
    """기본 도형 SOP 을 만들고 쿡해서 결과 통계를 돌려준다.

    노드 타입마다 크기 파라미터 이름이 다르다(box 는 sizex, sphere 는 radx,
    tube 는 rad1/rad2/height). 여기서는 size 하나로 받아 셰이프에 맞게 건다.

    기본값이 Primitive 타입인 노드(sphere, tube, circle)도 prim_type="poly" 로
    맞춰 준다. Primitive 구면은 점이 1개뿐이라 뒤 공정에서 거의 쓸 수 없다.

    Args:
        parent: SOP 을 담을 네트워크. 예: /obj/castle
        shape: box / sphere / tube / grid / torus / circle / platonic
        comment: 이 노드가 무엇을 위한 것인지. 필수. 씬에 저장되므로 영어로.
            예: "Wall body, 20 x 4 x 1.2"
        name: 노드 이름. 역할이 드러나게. 예: wall_body, tower_shaft
        size: 셰이프별 크기 3개. box=(x,y,z), sphere=(rx,ry,rz),
            tube=(rad_bottom, rad_top, height), grid=(x,y), torus=(major,minor),
            circle=(rx,ry), platonic=(radius,). 생략하면 노드 기본값.
        center: 중심 위치 (x,y,z). 생략하면 원점.
        rotate: 회전 (rx,ry,rz) 도 단위. 생략하면 회전 없음.
        divisions: 분할 수. box=(x,y,z), 나머지=(rows,cols), circle=(divs,).
        prim_type: poly / polysoup / mesh / nurbs / bezier / prim / points.
            셰이프가 지원하지 않는 값이면 쓸 수 있는 값을 알려 준다.
        platonic_solid: shape="platonic" 일 때만. tetrahedron / cube /
            octahedron / icosahedron / dodecahedron / soccerball / teapot.
    """
    require_comment(comment)
    if shape not in _SHAPES:
        raise ValueError(
            f"shape {shape!r} 는 모릅니다. 쓸 수 있는 값: {', '.join(_SHAPES)}"
        )

    spec = _SHAPES[shape]
    network = _require_network(parent)
    node = network.createNode(spec["type"], node_name=name)

    if shape == "platonic":
        if platonic_solid not in _PLATONIC:
            node.destroy()
            raise ValueError(
                f"platonic_solid {platonic_solid!r} 는 모릅니다. "
                f"쓸 수 있는 값: {', '.join(_PLATONIC)}"
            )
        node.parm("type").set(_PLATONIC[platonic_solid])
    elif node.parm("type") is not None:
        set_menu(node, "type", prim_type)

    if size is not None:
        names = spec["size"]
        if len(size) != len(names):
            node.destroy()
            raise ValueError(
                f"{shape} 의 size 는 값 {len(names)}개가 필요합니다 "
                f"({', '.join(names)}). 받은 것: {list(size)}"
            )
        set_parms(node, dict(zip(names, (float(v) for v in size))))

    if divisions is not None:
        names = spec["divs"]
        if not names:
            node.destroy()
            raise ValueError(f"{shape} 는 divisions 를 받지 않습니다.")
        if len(divisions) != len(names):
            node.destroy()
            raise ValueError(
                f"{shape} 의 divisions 는 값 {len(names)}개가 필요합니다 "
                f"({', '.join(names)}). 받은 것: {list(divisions)}"
            )
        set_parms(node, dict(zip(names, (int(v) for v in divisions))))

    if center is not None:
        tx, ty, tz = vec3(center, (0.0, 0.0, 0.0))
        # platonic 은 t 성분 이름이 t1/t2/t3 다.
        keys = ("t1", "t2", "t3") if shape == "platonic" else ("tx", "ty", "tz")
        set_parms(node, dict(zip(keys, (tx, ty, tz))))
    if rotate is not None:
        rx, ry, rz = vec3(rotate, (0.0, 0.0, 0.0))
        set_parms(node, {"rx": rx, "ry": ry, "rz": rz})

    return _finish(node, comment)


@tool()
@undoable("Create curve")
def create_curve(
    parent: str,
    points: Sequence[Sequence[float]],
    comment: str,
    name: str | None = None,
    closed: bool = False,
    curve_type: str = "poly",
) -> dict[str, Any]:
    """점 목록으로 곡선을 만든다.

    Houdini 22 의 Curve SOP 은 좌표를 파라미터가 아니라 뷰어에서 그린
    지오메트리로 들고 있어(coords 파라미터가 없어졌다) 스크립트로 채울 수 없다.
    대신 Add SOP 으로 점을 찍고 폴리곤 하나로 잇는다. 이쪽이 파라미터로 남아
    나중에 사람이 편집할 수 있다.

    NURBS/Bezier 는 Add SOP 뒤에 Convert SOP 을 붙여 만든다.

    Args:
        parent: SOP 을 담을 네트워크. 예: /obj/castle
        points: 점 좌표 목록. 예: [[0,0,0], [1,2,0], [3,0,0]]
        comment: 이 커브가 무엇인지. 필수. 영어로.
        name: 노드 이름. 역할이 드러나게. 예: tower_profile, path_spine
        closed: 시작점과 끝점을 이을지.
        curve_type: poly / nurbs / bezier.
    """
    require_comment(comment)
    if curve_type not in _CURVE_TYPES:
        raise ValueError(
            f"curve_type {curve_type!r} 는 모릅니다. "
            f"쓸 수 있는 값: {', '.join(_CURVE_TYPES)}"
        )
    if len(points) < 2:
        raise ValueError(f"점이 2개 이상 필요합니다. 받은 것: {len(points)}개")
    for index, point in enumerate(points):
        if len(point) != 3:
            raise ValueError(
                f"{index}번째 점에 값이 {len(point)}개입니다. (x, y, z) 3개를 주세요."
            )

    network = _require_network(parent)
    node = network.createNode("add", node_name=name)
    node.parm("points").set(len(points))
    for index, point in enumerate(points):
        node.parmTuple(f"pt{index}").set(tuple(float(v) for v in point))
    node.parm("prims").set(1)
    node.parm("prim0").set(f"0-{len(points) - 1}")
    node.parm("closed0").set(int(bool(closed)))

    to_type = _CURVE_TYPES[curve_type]
    if to_type is None:
        return _finish(node, comment)

    # Add SOP 은 폴리곤만 만든다. NURBS/Bezier 는 Convert 를 붙인다.
    node.setName(f"{node.name()}_points", unique_name=True)
    set_comment(node, f"{comment} (control points)")
    convert = network.createNode("convert", node_name=name)
    convert.setFirstInput(node)
    convert.parm("totype").set(to_type)
    return _finish(convert, comment)


@tool()
@undoable("Copy to points")
def copy_to_points(
    source: str,
    target: str,
    comment: str,
    name: str | None = None,
    target_group: str = "",
    pack: bool = False,
    pivot: str = "centroid",
    use_target_orientation: bool = True,
) -> dict[str, Any]:
    """소스 지오메트리를 타깃의 각 점에 복사한다.

    복사 전에 타깃 점 수를 확인해서, 결과가 왜 그 크기인지 바로 알 수 있게
    돌려준다. 점 10만 개에 상자를 복사하면 프림이 60만 개가 된다 — 실행 전에
    숫자를 보고 판단하라는 뜻이다.

    Args:
        source: 복사할 지오메트리 SOP 경로.
        target: 복사 위치가 될 점을 가진 SOP 경로.
        comment: 무엇을 왜 복사하는지. 필수. 영어로.
        name: 노드 이름. 예: copy_merlons
        target_group: 타깃 점 중 일부만 쓸 때 그룹/패턴. 예: "@type==1"
        pack: True 면 복사본을 패킹한다. 개수가 많으면 메모리가 크게 준다.
        pivot: origin / centroid. 소스의 어디를 점에 맞출지.
        use_target_orientation: 타깃 점의 N/up/orient 어트리뷰트로 회전할지.
    """
    source_node, source_geo = _geometry_pair(source, "source")
    target_node, target_geo = _geometry_pair(target, "target")
    if not same_network(source_node, target_node):
        raise ValueError(
            f"source 와 target 이 서로 다른 네트워크에 있습니다: "
            f"{source_node.parent().path()} vs {target_node.parent().path()}. "
            f"같은 네트워크 안의 SOP 두 개를 주세요."
        )

    # before/delta 는 소스 기준이다. 타깃 점 수는 inputs 에 따로 담는다 —
    # 결과 크기가 왜 그만큼인지(소스 x 타깃 점 수) 바로 읽히게 하려는 것이다.
    before = snapshot(source_geo)
    inputs = {
        "source": {
            "path": source_node.path(),
            "points": source_geo.pointCount(),
            "prims": source_geo.primCount(),
        },
        "target": {
            "path": target_node.path(),
            "points": target_geo.pointCount(),
        },
    }

    require_comment(comment)
    node = source_node.parent().createNode("copytopoints::2.0", node_name=name)
    node.setFirstInput(source_node)
    node.setInput(1, target_node)
    set_comment(node, comment)
    node.parm("targetgroup").set(target_group)
    node.parm("pack").set(int(bool(pack)))
    node.parm("useimplicitn").set(int(bool(use_target_orientation)))
    set_menu(node, "pivot", pivot)
    try:
        node.moveToGoodPosition()
    except hou.Error:
        pass
    node.setDisplayFlag(True)
    node.setRenderFlag(True)
    return report(node, before, extra={"inputs": inputs})


def _geometry_pair(path: str, label: str) -> tuple[hou.SopNode, Any]:
    try:
        node = require_sop(path)
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc
    return node, geometry_of(node)
