"""씬과 노드 그래프의 정보를 읽는 툴들.

읽기 전용이다. 씬을 바꾸는 것은 houdini_mcp_node 가 담당한다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool


def _require(path: str) -> hou.Node:
    """경로로 노드를 찾는다. 없으면 무엇이 잘못됐는지 알려주고 실패한다."""
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _brief(node: hou.Node) -> dict[str, Any]:
    """노드 하나를 짧게 요약한다. 목록에 쓴다.

    코멘트는 항상 함께 준다. 노드가 왜 있는지가 이름과 타입만으로는 드러나지
    않기 때문이다.
    """
    return {
        "name": node.name(),
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
    }


@tool()
def houdini_version() -> str:
    """실행 중인 Houdini 버전 문자열."""
    return hou.applicationVersionString()


@tool()
def scene_info() -> dict[str, Any]:
    """현재 씬의 경로, 저장 여부, FPS, 프레임 범위."""
    frame_range = hou.playbar.frameRange()
    return {
        "path": hou.hipFile.path(),
        "name": hou.hipFile.basename(),
        "has_unsaved_changes": hou.hipFile.hasUnsavedChanges(),
        "fps": hou.fps(),
        "frame_start": frame_range[0],
        "frame_end": frame_range[1],
        "current_frame": hou.frame(),
    }


@tool()
def list_children(path: str = "/obj") -> list[dict[str, str]]:
    """주어진 네트워크 아래 자식 노드들을 나열한다.

    Args:
        path: 부모 노드 경로. 기본값은 /obj.
    """
    return [_brief(child) for child in _require(path).children()]


@tool()
def node_info(path: str, include_parameters: bool = False) -> dict[str, Any]:
    """노드 하나의 타입, 부모, 자식 수, 플래그, 연결 상태.

    Args:
        path: 노드 경로. 예: /obj/geo1
        include_parameters: True 면 파라미터 이름 목록도 함께 준다.
            노드에 따라 수백 개가 되므로 기본값은 False 다.
    """
    node = _require(path)
    parent = node.parent()

    info: dict[str, Any] = {
        "name": node.name(),
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "category": node.type().category().name(),
        "parent": parent.path() if parent is not None else None,
        "child_count": len(node.children()),
        "inputs": [n.path() if n else None for n in node.inputs()],
        "outputs": [n.path() for n in node.outputs()],
    }

    flags = node_flags(path)
    if flags:
        info["flags"] = flags
    if include_parameters:
        info["parameters"] = [parm.name() for parm in node.parms()]
    return info


@tool()
def node_flags(path: str) -> dict[str, bool]:
    """노드의 display/render/bypass/lock 플래그.

    플래그는 노드 종류마다 있는 것이 다르다. 없는 것은 결과에서 빠진다.

    Args:
        path: 노드 경로.
    """
    node = _require(path)
    flags: dict[str, bool] = {}
    # 플래그는 컨텍스트마다 유무가 달라서, 있는 것만 담는다.
    for name, getter in (
        ("display", "isDisplayFlagSet"),
        ("render", "isRenderFlagSet"),
        ("bypass", "isBypassed"),
        ("lock", "isHardLocked"),
        ("template", "isTemplateFlagSet"),
    ):
        method = getattr(node, getter, None)
        if method is None:
            continue
        try:
            flags[name] = bool(method())
        except hou.OperationFailed:
            continue
    return flags


@tool()
def find_nodes(pattern: str, root: str = "/obj") -> list[dict[str, str]]:
    """패턴으로 노드를 찾는다.

    Houdini 의 노드 패턴 문법을 그대로 쓴다. `*` 는 한 단계, `**` 는 재귀다.

    Args:
        pattern: 예) "*geo*", "**/*box*"
        root: 검색을 시작할 네트워크 경로.
    """
    return [_brief(node) for node in _require(root).glob(pattern)]


@tool()
def network_graph(path: str = "/obj", depth: int = 1) -> dict[str, Any]:
    """네트워크의 노드와 연결을 한 번에 훑는다.

    노드 목록과 그 사이의 연결(wire)을 함께 주므로, 그래프 구조를 파악할 때
    list_children 을 여러 번 부르는 것보다 낫다.

    Args:
        path: 네트워크 경로.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지. 1 이면 바로 아래만.
    """
    root = _require(path)

    nodes: list[dict[str, Any]] = []
    wires: list[dict[str, Any]] = []

    def walk(parent: hou.Node, level: int) -> None:
        for child in parent.children():
            entry = _brief(child)
            entry["parent"] = parent.path()
            nodes.append(entry)

            for connection in child.inputConnections():
                wires.append(
                    {
                        "from": connection.inputNode().path(),
                        "from_output": connection.outputIndex(),
                        "to": child.path(),
                        "to_input": connection.inputIndex(),
                    }
                )

            if level < depth and child.children():
                walk(child, level + 1)

    walk(root, 1)
    return {"root": root.path(), "nodes": nodes, "wires": wires}


@tool()
def get_parms(path: str, names: list[str] | None = None) -> dict[str, Any]:
    """노드 파라미터 값과 그 노드의 코멘트를 읽는다.

    Args:
        path: 노드 경로.
        names: 읽을 파라미터 이름들. 생략하면 기본값과 다른 것만 돌려준다
            (노드마다 파라미터가 수백 개라 전부 주면 쓸모가 없다).
    """
    node = _require(path)

    if names:
        values: dict[str, Any] = {}
        for name in names:
            parm = node.parm(name)
            if parm is None:
                raise ValueError(f"{path} 에 그런 파라미터가 없습니다: {name}")
            values[name] = parm.eval()
    else:
        values = {
            parm.name(): parm.eval()
            for parm in node.parms()
            if not parm.isAtDefault()
        }

    # 값만 보면 이 노드가 무엇을 위한 것인지 알 수 없다. 코멘트를 함께 준다.
    return {"path": node.path(), "comment": node.comment(), "values": values}
