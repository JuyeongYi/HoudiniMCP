"""씬을 들여다보고 노드를 다루는 기본 툴들.

툴 패키지가 어떻게 생겨야 하는지 보여주는 예시다. 서버를 import 하지 않고
레지스트리만 건드린다는 점이 핵심이다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool


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
    """주어진 경로 아래 자식 노드들을 나열한다.

    Args:
        path: 부모 노드 경로. 기본값은 /obj.
    """
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return [
        {"name": child.name(), "path": child.path(), "type": child.type().name()}
        for child in node.children()
    ]


@tool()
def node_info(path: str) -> dict[str, Any]:
    """노드 하나의 타입, 부모, 자식 수, 파라미터 이름을 돌려준다.

    Args:
        path: 노드 경로. 예: /obj/geo1
    """
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    parent = node.parent()
    return {
        "name": node.name(),
        "path": node.path(),
        "type": node.type().name(),
        "category": node.type().category().name(),
        "parent": parent.path() if parent is not None else None,
        "child_count": len(node.children()),
        "parameters": [parm.name() for parm in node.parms()],
    }


@tool()
def create_node(parent: str, node_type: str, name: str | None = None) -> dict[str, str]:
    """부모 아래에 노드를 만든다.

    씬을 바꾸는 툴이다. 되돌리려면 Houdini 에서 Undo 해야 한다.

    Args:
        parent: 부모 노드 경로. 예: /obj
        node_type: 만들 노드 타입 이름. 예: geo, box
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    parent_node = hou.node(parent)
    if parent_node is None:
        raise ValueError(f"그런 부모 노드가 없습니다: {parent}")
    created = parent_node.createNode(node_type, node_name=name)
    return {"path": created.path(), "name": created.name()}


@tool(affinity="any")
def tool_catalog() -> list[dict[str, str]]:
    """등록된 모든 툴의 이름과 설명.

    레지스트리만 읽으므로 hou 를 건드리지 않는다. affinity="any" 인 예시다.
    """
    from houdini_mcp import get_registry

    return [
        {
            "name": spec.name,
            "description": spec.description,
            "affinity": spec.affinity,
            "package": spec.package,
        }
        for spec in get_registry().all()
    ]
