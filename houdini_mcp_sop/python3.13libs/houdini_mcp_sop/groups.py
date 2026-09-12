"""그룹을 만들고 들여다보는 툴.

그룹은 만들고 나서 **몇 개가 걸렸는지**가 전부다. 0개가 걸린 그룹은 뒤 공정을
조용히 망가뜨린다. 그래서 create_group 은 반드시 멤버 수를 돌려준다.

멤버 목록은 요약해서 돌려준다. 점 10만 개짜리 그룹의 번호를 그대로 보내면
모델 컨텍스트만 태운다. 연속된 번호는 범위로 접어서 보낸다.
"""

from __future__ import annotations

from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from ._common import build, geometry_at, report, set_menu, snapshot, vec3

MAX_RANGES = 100
"""멤버 목록을 접어서 돌려줄 범위 개수 상한."""

_GROUP_TYPES = {
    "point": ("point", "pointGroups", "findPointGroup"),
    "prim": ("primitive", "primGroups", "findPrimGroup"),
    "edge": ("edge", "edgeGroups", "findEdgeGroup"),
    "vertex": ("vertex", "vertexGroups", "findVertexGroup"),
}


@tool()
@undoable("Create group")
def create_group(
    path: str,
    comment: str,
    group_name: str,
    group_type: str = "point",
    pattern: str = "",
    bounding_box: Sequence[float] | None = None,
    normal_direction: Sequence[float] | None = None,
    normal_angle: float = 180.0,
    keep_by_normals: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    """그룹을 만들고 **실제로 몇 개가 걸렸는지** 돌려준다(GroupCreate SOP).

    세 가지 방식을 조합할 수 있다.

    - pattern: 번호 범위나 표현식. 예: "0-5", "@Cd.r>0.5"
    - bounding_box: 박스 안에 든 것만. (cx,cy,cz,sx,sy,sz) 6개.
    - normal_direction: 이 방향을 normal_angle 안쪽으로 향하는 면만.
      위를 보는 면을 고를 때 (0,1,0) 에 각도 45 같은 식으로 쓴다.

    Args:
        path: 입력 SOP 경로.
        comment: 이 그룹이 무엇을 위한 것인지. 필수. 영어로.
            예: "Top faces of wall, for merlon placement"
        group_name: 만들 그룹 이름. 역할이 드러나게, 영어로. 예: wall_top_faces
        group_type: point / prim / edge / vertex.
        pattern: 번호 범위나 표현식. 비우고 bounding_box 나 normal_direction 만
            쓸 수도 있다.
        bounding_box: (중심x, 중심y, 중심z, 크기x, 크기y, 크기z) 6개.
        normal_direction: 기준 방향 (x,y,z).
        normal_angle: normal_direction 에서 몇 도까지 받아줄지.
        keep_by_normals: normal_direction 을 쓸지. normal_direction 을 주면
            자동으로 켜진다.
        name: 노드 이름. 예: group_wall_top
    """
    if group_type not in _GROUP_TYPES:
        raise ValueError(
            f"group_type {group_type!r} 는 모릅니다. "
            f"쓸 수 있는 값: {', '.join(_GROUP_TYPES)}"
        )
    if not group_name or not group_name.strip():
        raise ValueError("group_name 이 비어 있습니다. 역할이 드러나는 이름을 주세요.")

    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "groupcreate", comment, name)
    node.parm("groupname").set(group_name)
    set_menu(node, "grouptype", _GROUP_TYPES[group_type][0])
    node.parm("groupbase").set(1 if pattern else 0)
    node.parm("basegroup").set(pattern)

    if bounding_box is not None:
        if len(bounding_box) != 6:
            raise ValueError(
                f"bounding_box 는 값 6개(중심 x,y,z + 크기 x,y,z)가 필요합니다. "
                f"받은 것: {list(bounding_box)}"
            )
        cx, cy, cz, sx, sy, sz = (float(v) for v in bounding_box)
        node.parm("groupbounding").set(1)
        node.parm("boundtype").set(0)
        node.parmTuple("t").set((cx, cy, cz))
        node.parmTuple("size").set((sx, sy, sz))

    if normal_direction is not None or keep_by_normals:
        dx, dy, dz = vec3(normal_direction, (0.0, 1.0, 0.0))
        node.parm("groupnormal").set(1)
        node.parmTuple("dir").set((dx, dy, dz))
        node.parm("angle").set(float(normal_angle))

    result = report(node, before)
    counts = _group_counts(node.geometry(), group_type)
    result["group"] = {
        "name": group_name,
        "type": group_type,
        "count": counts.get(group_name, 0),
    }
    if not counts.get(group_name, 0):
        result.setdefault("notes", []).append(
            f"그룹 {group_name!r} 에 아무것도 걸리지 않았습니다. pattern/bounding_box/"
            f"normal_direction 을 넓혀 보세요. list_attributes 로 표현식에 쓴 "
            f"어트리뷰트가 실제로 있는지도 확인하세요."
        )
    return result


@tool()
def group_members(
    path: str, group_name: str, group_type: str = "point", max_ranges: int = 50
) -> dict[str, Any]:
    """그룹에 무엇이 들었는지 돌려준다. 큰 그룹은 범위로 접어서 준다.

    연속된 번호는 "12-340" 처럼 접는다. 번호를 하나씩 나열하면 응답만 무거워지고
    읽히지 않는다.

    Args:
        path: SOP 노드 경로.
        group_name: 그룹 이름.
        group_type: point / prim / edge / vertex.
        max_ranges: 돌려줄 범위 개수 상한. 최대 100.
    """
    if group_type not in _GROUP_TYPES:
        raise ValueError(
            f"group_type {group_type!r} 는 모릅니다. "
            f"쓸 수 있는 값: {', '.join(_GROUP_TYPES)}"
        )
    if not 1 <= max_ranges <= MAX_RANGES:
        raise ValueError(f"max_ranges 는 1 이상 {MAX_RANGES} 이하여야 합니다: {max_ranges}")

    _, geo = geometry_at(path)
    _, list_attr, find_attr = _GROUP_TYPES[group_type]
    group = getattr(geo, find_attr)(group_name)
    if group is None:
        available = [g.name() for g in getattr(geo, list_attr)()]
        raise ValueError(
            f"{path} 에 {group_type} 그룹 {group_name!r} 가 없습니다. "
            f"있는 그룹: {', '.join(available) or '(없음)'}"
        )

    if group_type == "edge":
        edges = group.edges()
        sample = [
            f"p{e.points()[0].number()}-{e.points()[1].number()}" for e in edges[:max_ranges]
        ]
        return {
            "path": path,
            "group": group_name,
            "type": group_type,
            "count": group.edgeCount(),
            "edges": sample,
            "truncated": len(edges) > len(sample),
        }

    numbers = [element.number() for element in _elements(group, group_type)]
    ranges = _fold(numbers, max_ranges)
    return {
        "path": path,
        "group": group_name,
        "type": group_type,
        "count": len(numbers),
        "ranges": ranges,
        "truncated": _range_count(numbers) > len(ranges),
    }


def _elements(group: Any, group_type: str) -> Sequence[Any]:
    if group_type == "point":
        return group.points()
    if group_type == "prim":
        return group.prims()
    return group.vertices()


def _group_counts(geo: hou.Geometry, group_type: str) -> dict[str, int]:
    """만든 직후 그룹 멤버 수. 개수는 C++ 카운터로 얻는다."""
    _, list_attr, _ = _GROUP_TYPES[group_type]
    counts: dict[str, int] = {}
    for group in getattr(geo, list_attr)():
        if group_type == "point":
            counts[group.name()] = group.pointCount()
        elif group_type == "prim":
            counts[group.name()] = len(group.prims())
        elif group_type == "edge":
            counts[group.name()] = group.edgeCount()
        else:
            counts[group.name()] = len(group.vertices())
    return counts


def _fold(numbers: Sequence[int], limit: int) -> list[str]:
    """연속된 번호를 "a-b" 로 접는다."""
    out: list[str] = []
    start = previous = None
    for number in numbers:
        if start is None:
            start = previous = number
            continue
        if number == previous + 1:
            previous = number
            continue
        out.append(_span(start, previous))
        if len(out) >= limit:
            return out
        start = previous = number
    if start is not None and len(out) < limit:
        out.append(_span(start, previous))
    return out


def _range_count(numbers: Sequence[int]) -> int:
    """접었을 때 나올 범위 개수. 잘렸는지 판정하는 데만 쓴다."""
    if not numbers:
        return 0
    count = 1
    for index in range(1, len(numbers)):
        if numbers[index] != numbers[index - 1] + 1:
            count += 1
    return count


def _span(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"
