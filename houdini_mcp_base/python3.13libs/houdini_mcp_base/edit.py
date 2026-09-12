"""네트워크 종류와 무관하게 쓰는 노드 생성·조작·연결 툴.

OBJ / SOP / DOP / COP 어디서나 같은 방식으로 동작한다. 특정 컨텍스트에만
의미가 있는 툴은 그 컨텍스트 전용 팩(houdini_mcp_sop 등)에 둔다.

씬을 바꾸는 툴이다. Houdini 의 Undo 로 되돌릴 수 있도록 각 툴을
hou.undos.group() 으로 감싼다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

# 파라미터로 받을 수 있는 값. 벡터 파라미터는 tx/ty/tz 처럼 성분 이름으로 건다.
ParmValue = float | int | str | bool


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


@tool()
@undoable("Create node")
def create_node(
    parent: str,
    node_type: str,
    comment: str,
    name: str | None = None,
    parms: dict[str, ParmValue] | None = None,
) -> dict[str, Any]:
    """네트워크 안에 노드를 만든다. 만들면서 파라미터도 함께 걸 수 있다.

    comment 는 생략할 수 없다. 나중에 이 씬을 여는 사람(사람이든 모델이든)이
    노드가 왜 있는지 알 수 있어야 하기 때문이다. 코멘트는 네트워크 뷰에도
    표시된다.

    name 은 무엇을 하는 노드인지 드러나게 짓는다. box1, geo2 같은 기본 이름은
    나중에 그래프를 읽을 수 없게 만든다. 좋은 예: wall_body, merlon_points,
    copy_merlons.

    노드 이름과 코멘트는 씬 파일에 저장되고 Houdini UI 에 그대로 뜨므로 영어로
    쓴다.

    Args:
        parent: 부모 네트워크 경로. 예: /obj, /obj/geo1
        node_type: 노드 타입 이름. 예: geo, box, merge, copytopoints
        comment: 이 노드가 무엇을 위한 것인지. 필수. 씬 파일에 저장되고 다른
            도구에서도 읽히므로 영어로 쓴다. 예: "Wall body, 20 x 4 x 1.2"
        name: 노드 이름. 역할이 드러나게 짓는다. 생략하면 Houdini 가 정한다.
        parms: 만들자마자 걸 파라미터. 예: {"sizex": 2.0, "ty": 1.5}
    """
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 노드가 무엇을 위한 것인지 적어 주세요."
        )

    parent_node = _require(parent)
    try:
        node = parent_node.createNode(node_type, node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent} 안에 {node_type!r} 노드를 만들지 못했습니다. "
            f"그 네트워크에서 쓸 수 있는 타입인지 확인하세요. ({exc})"
        ) from exc
    _set_comment(node, comment)
    if parms:
        _apply_parms(node, parms)

    return {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
    }


@tool()
@undoable("Set comment")
def set_comment(path: str, comment: str) -> dict[str, str]:
    """노드 코멘트를 바꾼다.

    노드의 역할이 달라졌으면 코멘트도 따라 고친다.

    Args:
        path: 노드 경로.
        comment: 새 코멘트. 씬에 저장되므로 영어로 쓴다.
    """
    if not comment or not comment.strip():
        raise ValueError("comment 가 비어 있습니다.")
    node = _require(path)
    _set_comment(node, comment)
    return {"path": node.path(), "comment": node.comment()}


def _set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


@tool()
@undoable("Delete node")
def delete_node(path: str) -> dict[str, str]:
    """노드를 지운다.

    Args:
        path: 지울 노드 경로.
    """
    node = _require(path)
    deleted = node.path()
    node.destroy()
    return {"deleted": deleted}


@tool()
@undoable("Rename node")
def rename_node(path: str, name: str) -> dict[str, str]:
    """노드 이름을 바꾼다.

    무엇을 하는 노드인지 드러나게 짓는다. box1, geo2 같은 기본 이름은 나중에
    그래프를 읽을 수 없게 만든다.

    Args:
        path: 노드 경로.
        name: 새 이름. 역할이 드러나게, 영어로.
    """
    node = _require(path)
    node.setName(name, unique_name=True)
    return {"path": node.path(), "name": node.name()}


@tool()
@undoable("Set parameters")
def set_parms(path: str, parms: dict[str, ParmValue]) -> dict[str, Any]:
    """노드 파라미터를 건다.

    벡터 파라미터는 성분 이름으로 건다. 예를 들어 위치는 t 가 아니라
    tx / ty / tz 로 준다.

    Args:
        path: 노드 경로.
        parms: 이름과 값. 예: {"sizex": 2.0, "ty": 1.5, "group": "0-3"}
    """
    node = _require(path)
    applied = _apply_parms(node, parms)
    return {"path": node.path(), "applied": applied}


@tool()
@undoable("Connect nodes")
def connect_nodes(
    source: str, target: str, input_index: int = 0, output_index: int = 0
) -> dict[str, Any]:
    """source 의 출력을 target 의 입력에 잇는다.

    Args:
        source: 출력 쪽 노드 경로.
        target: 입력 쪽 노드 경로.
        input_index: target 의 몇 번째 입력에 꽂을지.
        output_index: source 의 몇 번째 출력에서 뽑을지.
    """
    source_node = _require(source)
    target_node = _require(target)
    try:
        target_node.setInput(input_index, source_node, output_index)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{source} 를 {target} 의 입력 {input_index} 에 잇지 못했습니다. ({exc})"
        ) from exc
    return {
        "source": source_node.path(),
        "target": target_node.path(),
        "input_index": input_index,
    }


@tool()
@undoable("Disconnect input")
def disconnect_input(path: str, input_index: int = 0) -> dict[str, Any]:
    """노드의 입력 하나를 끊는다.

    주의: merge 처럼 입력 개수가 가변인 노드는 하나를 끊으면 **뒤 입력이 앞으로
    당겨진다.** 여러 개를 끊을 때 작은 번호부터 끊으면 엉뚱한 입력이 사라진다.
    반드시 **큰 번호부터** 끊고, 끝나면 node_info 로 확인한다.

    Args:
        path: 노드 경로.
        input_index: 끊을 입력 번호.
    """
    node = _require(path)
    node.setInput(input_index, None)
    return {"path": node.path(), "input_index": input_index}


@tool()
@undoable("Set flags")
def set_flags(
    path: str,
    display: bool | None = None,
    render: bool | None = None,
    bypass: bool | None = None,
) -> dict[str, bool]:
    """노드 플래그를 건다. 준 것만 바뀐다.

    플래그는 컨텍스트마다 있는 것이 다르다. 그 노드에 없는 플래그를 주면
    무엇이 없는지 알려주고 실패한다.

    Args:
        path: 노드 경로.
        display: 뷰포트 표시 플래그.
        render: 렌더 플래그.
        bypass: 바이패스 플래그.
    """
    node = _require(path)
    wanted = {"display": display, "render": render, "bypass": bypass}
    setters = {
        "display": "setDisplayFlag",
        "render": "setRenderFlag",
        "bypass": "bypass",
    }

    changed: dict[str, bool] = {}
    for key, value in wanted.items():
        if value is None:
            continue
        method = getattr(node, setters[key], None)
        if method is None:
            raise ValueError(f"{path} 에는 {key} 플래그가 없습니다.")
        method(value)
        changed[key] = value
    return changed


@tool()
@undoable("Layout children")
def layout_children(path: str) -> dict[str, Any]:
    """네트워크 안 노드들을 보기 좋게 정렬한다.

    툴로 노드를 여럿 만들면 자리가 겹치므로, 만든 뒤 한 번 불러 주면 좋다.

    Args:
        path: 네트워크 경로.
    """
    node = _require(path)
    node.layoutChildren()
    return {"path": node.path(), "child_count": len(node.children())}


def _apply_parms(node: hou.Node, parms: dict[str, ParmValue]) -> list[str]:
    """파라미터를 걸고, 실제로 건 이름들을 돌려준다."""
    applied: list[str] = []
    for name, value in parms.items():
        parm = node.parm(name)
        if parm is None:
            # 벡터를 통째로 주려 한 경우를 짚어 준다.
            tuple_parm = node.parmTuple(name)
            if tuple_parm is not None:
                components = ", ".join(p.name() for p in tuple_parm)
                raise ValueError(
                    f"{name!r} 은 벡터 파라미터입니다. 성분 이름으로 거세요: {components}"
                )
            raise ValueError(f"{node.path()} 에 그런 파라미터가 없습니다: {name}")
        parm.set(value)
        applied.append(name)
    return applied


@tool()
@undoable("Copy node")
def copy_node(path: str, parent: str | None = None, name: str | None = None) -> dict[str, Any]:
    """노드를 복제한다. 파라미터와 내부 네트워크까지 함께 복사된다.

    Args:
        path: 복사할 노드 경로.
        parent: 붙여 넣을 네트워크. 생략하면 원본과 같은 부모.
        name: 새 이름. 생략하면 Houdini 가 정한다.
    """
    source = _require(path)
    target = _require(parent) if parent else source.parent()
    if target is None:
        raise ValueError(f"{path} 의 부모를 찾지 못했습니다. parent 를 지정하세요.")

    copies = target.copyItems([source])
    if not copies:
        raise ValueError(f"{path} 를 복사하지 못했습니다.")
    copy = copies[0]
    if name:
        copy.setName(name, unique_name=True)
    return {"source": source.path(), "path": copy.path(), "name": copy.name()}


@tool()
@undoable("Reorder inputs")
def reorder_inputs(path: str, order: list[int]) -> dict[str, Any]:
    """노드의 입력 순서를 바꾼다.

    merge 처럼 입력 순서가 결과에 영향을 주는 노드에서 쓴다. order 는 새 순서로
    나열한 현재 입력 번호다. 예를 들어 [1, 0, 2] 는 앞의 두 입력을 맞바꾼다.

    Args:
        path: 노드 경로.
        order: 새 순서. 현재 입력 번호를 원하는 순서대로.
    """
    node = _require(path)
    current = list(node.inputs())
    if sorted(order) != list(range(len(current))):
        raise ValueError(
            f"order 는 0..{len(current) - 1} 을 한 번씩 써야 합니다. 받은 값: {order}"
        )

    rearranged = [current[i] for i in order]
    # 전부 끊고 새 순서로 다시 꽂는다. merge 처럼 입력이 가변인 노드는 중간을
    # 끊으면 뒤가 당겨지므로, 부분 교체가 아니라 통째로 다시 배선해야 한다.
    for index in range(len(current)):
        node.setInput(index, None)
    for index, source in enumerate(rearranged):
        if source is not None:
            node.setInput(index, source)
    return {
        "path": node.path(),
        "inputs": [n.path() if n else None for n in node.inputs()],
    }


@tool()
@undoable("Set node appearance")
def set_node_appearance(
    path: str,
    color: list[float] | None = None,
    position: list[float] | None = None,
    shape: str | None = None,
) -> dict[str, Any]:
    """네트워크 뷰에서의 노드 색·위치·모양을 정한다.

    그래프를 사람이 읽기 쉽게 정리할 때 쓴다. 결과 지오메트리에는 영향이 없다.

    Args:
        path: 노드 경로.
        color: RGB 0~1 세 값. 예: [0.9, 0.3, 0.3]
        position: 네트워크 뷰 좌표 두 값. 예: [3.0, -2.0]
        shape: 노드 모양 이름. 예: circle, oval, box
    """
    node = _require(path)
    changed: dict[str, Any] = {}

    if color is not None:
        if len(color) != 3 or not all(0.0 <= c <= 1.0 for c in color):
            raise ValueError(f"color 는 0~1 사이 RGB 세 값이어야 합니다: {color}")
        node.setColor(hou.Color(tuple(color)))
        changed["color"] = list(color)

    if position is not None:
        if len(position) != 2:
            raise ValueError(f"position 은 두 값이어야 합니다: {position}")
        node.setPosition(hou.Vector2(tuple(position)))
        changed["position"] = list(position)

    if shape is not None:
        try:
            node.setUserData("nodeshape", shape)
        except hou.OperationFailed as exc:
            raise ValueError(f"모양을 바꾸지 못했습니다: {shape} ({exc})") from exc
        changed["shape"] = shape

    if not changed:
        raise ValueError("color, position, shape 중 적어도 하나는 줘야 합니다.")
    return {"path": node.path(), **changed}


@tool()
def get_selection() -> dict[str, Any]:
    """지금 사용자가 네트워크 뷰에서 고른 노드들.

    "이거 고쳐 줘" 처럼 대상이 생략된 요청을 받을 때 무엇을 가리키는지 확인한다.
    """
    selected = hou.selectedNodes()
    return {
        "count": len(selected),
        "nodes": [
            {"path": n.path(), "type": n.type().name(), "comment": n.comment()}
            for n in selected
        ],
    }


@tool()
@undoable("Select by pattern")
def select_by_pattern(
    pattern: str = "*",
    root: str = "/obj",
    node_type: str | None = None,
    clear_existing: bool = True,
) -> dict[str, Any]:
    """패턴이나 타입으로 골라서 한꺼번에 선택한다.

    `set_selection` 은 경로를 하나씩 받는다. 그 앞에 `find_nodes` 를 부르는 일이
    반복되므로 둘을 합쳤다. 작업 대상을 사용자에게 짚어 보여줄 때 쓴다.

    무엇이 골라질지 미리 보고 싶으면 `find_nodes` 를 먼저 부른다 - 이 툴은 바로
    선택까지 바꾼다.

    Args:
        pattern: 노드 이름 패턴. `*` 는 한 단계, `**` 는 재귀.
            예: "*wall*", "**/*merlon*"
        root: 검색을 시작할 네트워크 경로.
        node_type: 타입으로 한 번 더 거른다. 예: box, copytopoints
        clear_existing: 기존 선택을 지우고 새로 고른다.
    """
    matched = _require(root).glob(pattern)
    if node_type:
        # 버전 접미사(box::2.0)가 붙은 타입도 같은 것으로 본다.
        matched = [n for n in matched if n.type().name().split("::", 1)[0] == node_type]

    if clear_existing:
        hou.clearAllSelected()
    for node in matched:
        node.setSelected(True)

    return {
        "pattern": pattern,
        "root": root,
        "node_type": node_type,
        "count": len(matched),
        "selected": [
            {"path": n.path(), "type": n.type().name(), "comment": n.comment()}
            for n in matched
        ],
    }


@tool()
@undoable("Set selection")
def set_selection(paths: list[str], clear_existing: bool = True) -> dict[str, Any]:
    """네트워크 뷰의 선택을 바꾼다.

    작업한 노드를 사용자에게 짚어 보여줄 때 쓴다.

    Args:
        paths: 고를 노드 경로들.
        clear_existing: 기존 선택을 지우고 새로 고른다.
    """
    if clear_existing:
        hou.clearAllSelected()
    chosen = []
    for path in paths:
        node = _require(path)
        node.setSelected(True)
        chosen.append(node.path())
    return {"selected": chosen, "count": len(chosen)}
