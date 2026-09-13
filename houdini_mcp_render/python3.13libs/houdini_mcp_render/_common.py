"""렌더 팩이 공유하는 Houdini 헬퍼. 여기에는 툴이 없다.

경로 전개와 `$HFS/bin` 조회는 houdini_mcp_base.paths 를 쓴다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path

import hou

MAX_TEXT = 1200
"""로그 한 줄이 응답을 잡아먹지 않도록 자르는 길이."""


def require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def require_lop(path: str) -> hou.LopNode:
    """LOP 노드를 얻는다. 아니면 어디를 봐야 하는지 알려 준다."""
    node = require_node(path)
    if not isinstance(node, hou.LopNode):
        raise ValueError(
            f"{path} 는 LOP 노드가 아닙니다 (category={node.type().category().name()}). "
            f"/stage 아래의 LOP 경로를 주세요. 예: /stage/karmarendersettings1"
        )
    return node


def lop_stage(node: hou.LopNode):
    """LOP 노드가 만들어 내는 USD 스테이지.

    쿡을 강제한다. 쿡하지 않은 LOP 는 스테이지가 비어 있어서, 라이트가 없다는
    잘못된 진단을 내게 된다.
    """
    try:
        node.cook(force=False)
    except hou.OperationFailed as exc:
        raise RuntimeError(
            f"{node.path()} 를 쿡하지 못했습니다: {str(exc).splitlines()[0][:MAX_TEXT]}. "
            f"node_errors 로 원인을 보세요."
        ) from exc
    stage = node.stage()
    if stage is None:
        raise RuntimeError(
            f"{node.path()} 의 스테이지를 읽지 못했습니다. 노드가 쿡되는지 "
            f"cook_node 로 먼저 확인하세요."
        )
    return stage


def writable_dir(path: Path) -> tuple[bool, str]:
    """출력 경로의 디렉토리에 쓸 수 있는지. (가능한가, 이유) 를 돌려준다."""
    parent = path.parent
    if parent.exists():
        if not parent.is_dir():
            return False, f"{parent} 가 디렉토리가 아닙니다."
        return True, "이미 있습니다."
    # husk 는 --make-output-path 로 만들어 준다. 만들 수 있는 자리인지만 본다.
    for ancestor in parent.parents:
        if ancestor.exists():
            return True, f"{ancestor} 아래에 새로 만들어집니다."
    return False, f"{parent} 를 만들 수 있는 상위 디렉토리가 없습니다."


def clip(text: str, limit: int = MAX_TEXT) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
