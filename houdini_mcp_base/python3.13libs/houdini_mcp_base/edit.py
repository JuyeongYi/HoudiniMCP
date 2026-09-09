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

from houdini_mcp import tool

# 파라미터로 받을 수 있는 값. 벡터 파라미터는 tx/ty/tz 처럼 성분 이름으로 건다.
ParmValue = float | int | str | bool


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


@tool()
def create_node(
    parent: str,
    node_type: str,
    name: str | None = None,
    parms: dict[str, ParmValue] | None = None,
) -> dict[str, Any]:
    """네트워크 안에 노드를 만든다. 만들면서 파라미터도 함께 걸 수 있다.

    Args:
        parent: 부모 네트워크 경로. 예: /obj, /obj/geo1
        node_type: 노드 타입 이름. 예: geo, box, merge, copytopoints
        name: 노드 이름. 생략하면 Houdini 가 정한다.
        parms: 만들자마자 걸 파라미터. 예: {"sizex": 2.0, "ty": 1.5}
    """
    parent_node = _require(parent)
    with hou.undos.group(f"MCP: create {node_type}"):
        try:
            node = parent_node.createNode(node_type, node_name=name)
        except hou.OperationFailed as exc:
            raise ValueError(
                f"{parent} 안에 {node_type!r} 노드를 만들지 못했습니다. "
                f"그 네트워크에서 쓸 수 있는 타입인지 확인하세요. ({exc})"
            ) from exc
        if parms:
            _apply_parms(node, parms)

    return {"path": node.path(), "name": node.name(), "type": node.type().name()}


@tool()
def delete_node(path: str) -> dict[str, str]:
    """노드를 지운다.

    Args:
        path: 지울 노드 경로.
    """
    node = _require(path)
    deleted = node.path()
    with hou.undos.group(f"MCP: delete {node.name()}"):
        node.destroy()
    return {"deleted": deleted}


@tool()
def rename_node(path: str, name: str) -> dict[str, str]:
    """노드 이름을 바꾼다.

    Args:
        path: 노드 경로.
        name: 새 이름.
    """
    node = _require(path)
    with hou.undos.group(f"MCP: rename {node.name()}"):
        node.setName(name, unique_name=True)
    return {"path": node.path(), "name": node.name()}


@tool()
def set_parms(path: str, parms: dict[str, ParmValue]) -> dict[str, Any]:
    """노드 파라미터를 건다.

    벡터 파라미터는 성분 이름으로 건다. 예를 들어 위치는 t 가 아니라
    tx / ty / tz 로 준다.

    Args:
        path: 노드 경로.
        parms: 이름과 값. 예: {"sizex": 2.0, "ty": 1.5, "group": "0-3"}
    """
    node = _require(path)
    with hou.undos.group(f"MCP: set parms on {node.name()}"):
        applied = _apply_parms(node, parms)
    return {"path": node.path(), "applied": applied}


@tool()
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
    with hou.undos.group(f"MCP: connect {source_node.name()} -> {target_node.name()}"):
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
def disconnect_input(path: str, input_index: int = 0) -> dict[str, Any]:
    """노드의 입력 하나를 끊는다.

    Args:
        path: 노드 경로.
        input_index: 끊을 입력 번호.
    """
    node = _require(path)
    with hou.undos.group(f"MCP: disconnect {node.name()}"):
        node.setInput(input_index, None)
    return {"path": node.path(), "input_index": input_index}


@tool()
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
    with hou.undos.group(f"MCP: flags on {node.name()}"):
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
def layout_children(path: str) -> dict[str, Any]:
    """네트워크 안 노드들을 보기 좋게 정렬한다.

    툴로 노드를 여럿 만들면 자리가 겹치므로, 만든 뒤 한 번 불러 주면 좋다.

    Args:
        path: 네트워크 경로.
    """
    node = _require(path)
    with hou.undos.group(f"MCP: layout {node.name()}"):
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
