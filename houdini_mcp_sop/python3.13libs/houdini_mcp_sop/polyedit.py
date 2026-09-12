"""폴리곤을 고치는 툴 — 베벨·익스트루드·브리지·미러·리볼브·스킨·불리언.

전부 같은 모양이다. 입력 지오메트리를 찍고(before), 노드를 만들어 잇고, 쿡해서
결과를 찍어(after) 둘을 비교해 돌려준다. 모델이 "먹었는지"를 다시 묻지 않아도
되게 하려는 것이다.

22.0 에서 실제로 만들어지는 노드 타입은 이름과 다르다. bevel 은 없고
polybevel::3.0 이, boolean 은 boolean::2.0 이, lathe 는 revolve::2.0 이 뜬다.
파라미터 이름도 버전에 묶여 있으므로 여기서 한 번 고정해 둔다.
"""

from __future__ import annotations

from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from ._common import (
    build,
    geometry_at,
    geometry_of,
    open_edge_count,
    report,
    require_sop,
    same_network,
    set_menu,
    snapshot,
    vec3,
)

_EDGE_GROUP_HINT = (
    "에지 그룹은 점 번호 쌍으로 씁니다: 'p0-1 p1-2' 또는 전체는 '*'. "
    "프림 번호 범위('0-11')는 에지 그룹이 아닙니다. "
    "list_groups 로 이미 있는 에지 그룹을 확인하거나 create_group 으로 먼저 만드세요."
)


@tool()
@undoable("Bevel")
def bevel(
    path: str,
    comment: str,
    offset: float = 0.05,
    group: str = "*",
    group_type: str = "edges",
    divisions: int = 1,
    shape: str = "round",
    name: str | None = None,
) -> dict[str, Any]:
    """에지나 점을 깎는다(PolyBevel). 전후 포인트·프림 수를 비교해 돌려준다.

    group_type="edges" 일 때 group 은 에지 패턴이다. 프림 번호 범위를 주면
    쿡이 실패한다. 전체 에지는 "*" 다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 깎는지. 필수. 영어로.
            예: "Soften wall top edges, 0.05"
        offset: 깎는 폭. 지오메트리 크기 대비 너무 크면 폴리곤이 뒤집힌다.
        group: 대상 패턴. 에지는 "*" 또는 "p0-1 p1-2", 점/프림은 번호 범위.
        group_type: edges / points / prims / guess.
        divisions: 필렛 분할 수. 1 이면 챔퍼처럼 각지고, 키우면 둥글어진다.
        shape: round / chamfer / crease / solid / none.
        name: 노드 이름. 역할이 드러나게. 예: bevel_wall_top
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "polybevel", comment, name)
    set_menu(node, "grouptype", group_type)
    set_menu(node, "filletshape", shape)
    node.parm("group").set(group)
    node.parm("offset").set(float(offset))
    node.parm("divisions").set(int(divisions))

    try:
        return report(node, before)
    except ValueError as exc:
        if group_type == "edges" and "group" in str(exc):
            raise ValueError(f"{exc} {_EDGE_GROUP_HINT}") from exc
        raise


@tool()
@undoable("Extrude faces")
def extrude_faces(
    path: str,
    comment: str,
    distance: float = 0.1,
    inset: float = 0.0,
    group: str = "",
    divisions: int = 1,
    split_type: str = "elements",
    output_front: bool = True,
    output_side: bool = True,
    output_back: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    """면을 밀어낸다(PolyExtrude). 인셋만 하려면 distance=0, inset>0 을 준다.

    인셋 전용 노드는 22.0 에 없다. PolyExtrude 의 inset 파라미터가 그 일을
    하므로 툴을 따로 두지 않았다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 밀어내는지. 필수. 영어로.
            예: "Extrude merlon tops 0.4 up"
        distance: 밀어내는 거리. 음수면 안쪽으로 판다.
        inset: 밀어낸 면을 안쪽으로 줄이는 양. 양수면 좁아진다.
        group: 대상 프림 패턴. 비우면 전부.
        divisions: 옆면 분할 수.
        split_type: elements(면 하나씩) / components(붙은 덩어리째).
        output_front: 밀어낸 앞면을 남길지.
        output_side: 옆면을 만들지.
        output_back: 원래 자리의 뒷면을 남길지. 속을 파낼 때 켠다.
        name: 노드 이름. 예: extrude_merlon_tops
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "polyextrude", comment, name)
    set_menu(node, "splittype", split_type)
    node.parm("group").set(group)
    node.parm("dist").set(float(distance))
    node.parm("inset").set(float(inset))
    node.parm("divs").set(int(divisions))
    node.parm("outputfront").set(int(bool(output_front)))
    node.parm("outputside").set(int(bool(output_side)))
    node.parm("outputback").set(int(bool(output_back)))
    return report(node, before)


@tool()
@undoable("Bridge edges")
def bridge_edges(
    path: str,
    comment: str,
    source_group: str,
    destination_group: str,
    divisions: int = 1,
    keep_input: bool = True,
    name: str | None = None,
) -> dict[str, Any]:
    """두 에지 루프 사이에 면을 만든다(PolyBridge).

    Args:
        path: 입력 SOP 경로. 양쪽 루프가 모두 이 지오메트리에 있어야 한다.
        comment: 무엇을 잇는지. 필수. 영어로.
        source_group: 시작 루프의 에지/프림 그룹 이름 또는 패턴.
        destination_group: 끝 루프의 에지/프림 그룹 이름 또는 패턴.
        divisions: 잇는 구간의 분할 수.
        keep_input: 원래 지오메트리를 함께 남길지.
        name: 노드 이름. 예: bridge_tower_to_wall
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    node = build(source, "polybridge", comment, name)
    node.parm("srcgroup").set(source_group)
    node.parm("dstgroup").set(destination_group)
    node.parm("srcdivs").set(int(divisions))
    node.parm("dstdivs").set(int(divisions))
    node.parm("keepinputgeo").set(int(bool(keep_input)))

    try:
        return report(node, before)
    except ValueError as exc:
        raise ValueError(f"{exc} {_EDGE_GROUP_HINT}") from exc


@tool()
@undoable("Mirror")
def mirror_geometry(
    path: str,
    comment: str,
    direction: Sequence[float] | None = None,
    origin: Sequence[float] | None = None,
    keep_original: bool = True,
    consolidate: bool = True,
    group: str = "",
    name: str | None = None,
) -> dict[str, Any]:
    """평면을 기준으로 지오메트리를 반사한다.

    Args:
        path: 입력 SOP 경로.
        comment: 무엇을 왜 미러하는지. 필수. 영어로.
        direction: 반사 평면의 법선 (x,y,z). 기본 (1,0,0) — YZ 평면 대칭.
        origin: 반사 평면이 지나는 점 (x,y,z). 기본 원점.
        keep_original: 원본을 함께 남길지. False 면 반사본만 남는다.
        consolidate: 평면 위에서 겹친 점을 붙일지. 대칭 모델링의 이음매를 없앤다.
        group: 대상 프림 패턴. 비우면 전부.
        name: 노드 이름. 예: mirror_wall_east
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)

    dx, dy, dz = vec3(direction, (1.0, 0.0, 0.0))
    ox, oy, oz = vec3(origin, (0.0, 0.0, 0.0))

    node = build(
        source,
        "mirror",
        comment,
        name,
        parms={
            "group": group,
            "dirx": dx,
            "diry": dy,
            "dirz": dz,
            "originx": ox,
            "originy": oy,
            "originz": oz,
            "keepOriginal": int(bool(keep_original)),
            "consolidatepts": int(bool(consolidate)),
        },
    )
    return report(node, before)


@tool()
@undoable("Revolve profile")
def revolve_profile(
    path: str,
    comment: str,
    axis: Sequence[float] | None = None,
    origin: Sequence[float] | None = None,
    divisions: int = 16,
    begin_angle: float = 0.0,
    end_angle: float = 360.0,
    cap: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    """프로파일 커브를 축 둘레로 돌려 회전체를 만든다(선반/lathe).

    lathe 라는 노드는 22.0 에 없다. Revolve SOP 이 그 일을 한다.

    Args:
        path: 프로파일 커브를 내보내는 SOP 경로.
        comment: 무엇을 만드는지. 필수. 영어로.
            예: "Revolve tower profile into cone roof"
        axis: 회전축 방향 (x,y,z). 기본 (0,1,0) — Y축.
        origin: 축이 지나는 점 (x,y,z). 기본 원점.
        divisions: 둘레 분할 수. 클수록 매끄럽다.
        begin_angle: 시작 각도(도). 부분 회전체를 만들 때.
        end_angle: 끝 각도(도). 360 이면 한 바퀴.
        cap: 부분 회전체의 끝을 막을지.
        name: 노드 이름. 예: revolve_tower_roof
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)
    if geo.pointCount() < 2:
        raise ValueError(
            f"{path} 의 포인트가 {geo.pointCount()}개뿐이라 회전시킬 프로파일이 "
            f"없습니다. create_curve 로 프로파일 커브를 먼저 만드세요."
        )

    ax, ay, az = vec3(axis, (0.0, 1.0, 0.0))
    ox, oy, oz = vec3(origin, (0.0, 0.0, 0.0))
    full = abs(end_angle - begin_angle) >= 360.0

    node = build(
        source,
        "revolve",
        comment,
        name,
        parms={
            "dirx": ax,
            "diry": ay,
            "dirz": az,
            "originx": ox,
            "originy": oy,
            "originz": oz,
            "divs": int(divisions),
            "beginangle": float(begin_angle),
            "endangle": float(end_angle),
            "cap": int(bool(cap)),
        },
    )
    set_menu(node, "type", "closed" if full else "openarc")
    return report(node, before)


@tool()
@undoable("Skin sections")
def skin_sections(
    path: str,
    comment: str,
    close_along_sections: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    """단면 커브들 사이에 면을 씌운다(Skin/loft).

    입력의 프림이 2개 이상이어야 한다. 단면이 하나뿐이면 그 자리에서 알려 준다.

    Args:
        path: 단면 커브들을 내보내는 SOP 경로. 프림 순서대로 이어진다.
        comment: 무엇을 씌우는지. 필수. 영어로.
        close_along_sections: 마지막 단면과 첫 단면을 이을지.
        name: 노드 이름. 예: skin_roof_sections
    """
    source, geo = geometry_at(path)
    before = snapshot(geo)
    if geo.primCount() < 2:
        raise ValueError(
            f"{path} 의 프림이 {geo.primCount()}개뿐입니다. Skin 은 단면 커브가 "
            f"2개 이상 필요합니다. merge 로 여러 커브를 합친 결과를 주세요."
        )

    node = build(
        source,
        "skin",
        comment,
        name,
        parms={"closev": int(bool(close_along_sections))},
    )
    return report(node, before)


@tool()
@undoable("Boolean")
def boolean_op(
    path_a: str,
    path_b: str,
    comment: str,
    operation: str = "union",
    subtract_order: str = "aminusb",
    a_is_solid: bool = True,
    b_is_solid: bool = True,
    name: str | None = None,
) -> dict[str, Any]:
    """두 메시로 불리언 연산을 한다(Boolean SOP).

    쿡하기 전에 양쪽이 닫힌 메시인지 확인해서 돌려준다. 열린 메시에
    solid 연산을 걸면 결과가 조용히 이상해지는데, 기존 구현들은 그걸 알려주지
    않는다. 열려 있으면 여기서 열린 에지 개수를 리포트에 함께 담는다.

    Args:
        path_a: A 입력 SOP 경로.
        path_b: B 입력 SOP 경로.
        comment: 무엇을 왜 자르는지. 필수. 영어로.
            예: "Cut window openings out of wall body"
        operation: union / intersect / subtract / shatter / seam.
        subtract_order: operation="subtract" 일 때 aminusb / bminusa / both.
        a_is_solid: A 를 속이 찬 입체로 볼지. False 면 표면으로 본다.
        b_is_solid: B 를 속이 찬 입체로 볼지.
        name: 노드 이름. 예: cut_windows
    """
    node_a, geo_a = _side(path_a, "path_a")
    node_b, geo_b = _side(path_b, "path_b")
    if not same_network(node_a, node_b):
        raise ValueError(
            f"path_a 와 path_b 가 서로 다른 네트워크에 있습니다: "
            f"{node_a.parent().path()} vs {node_b.parent().path()}. "
            f"같은 네트워크 안의 SOP 두 개를 주세요."
        )

    open_a, open_b = open_edge_count(geo_a), open_edge_count(geo_b)
    # before/delta 는 A 기준이다. B 쪽 숫자는 inputs 에 따로 담는다.
    before = snapshot(geo_a)
    inputs = {
        "a": dict(snapshot(geo_a), path=node_a.path(), open_edges=open_a),
        "b": dict(snapshot(geo_b), path=node_b.path(), open_edges=open_b),
    }

    node = build(node_a, "boolean", comment, name, extra_inputs=(node_b,))
    set_menu(node, "booleanop", operation)
    if operation == "subtract":
        set_menu(node, "subtractchoices", subtract_order)
    set_menu(node, "asurface", "solid" if a_is_solid else "surface")
    set_menu(node, "bsurface", "solid" if b_is_solid else "surface")

    result = report(node, before, extra={"inputs": inputs})
    notes = []
    if a_is_solid and open_a:
        notes.append(
            f"A({node_a.path()}) 에 열린 에지가 {open_a}개 있어 닫힌 입체가 아닙니다. "
            f"a_is_solid=False 로 표면 연산을 하거나 구멍을 먼저 메우세요."
        )
    if b_is_solid and open_b:
        notes.append(
            f"B({node_b.path()}) 에 열린 에지가 {open_b}개 있어 닫힌 입체가 아닙니다. "
            f"b_is_solid=False 로 표면 연산을 하거나 구멍을 먼저 메우세요."
        )
    if notes:
        result["notes"] = notes
    return result


def _side(path: str, label: str) -> tuple[hou.SopNode, hou.Geometry]:
    try:
        node = require_sop(path)
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc
    return node, geometry_of(node)
