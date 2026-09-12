"""무엇이 잘못됐는지 알아내는 툴들.

노드를 만들고 연결했는데 결과가 안 나올 때, 지금까지는 뷰포트를 보고 짐작하는
수밖에 없었다. 에러는 노드에 붙어 있으므로 읽으면 된다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import time
from typing import Any, Iterator

import hou

from houdini_mcp import tool, undoable

MAX_NODES = 500
MAX_TEXT = 1200


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _walk(root: hou.Node, depth: int) -> Iterator[tuple[hou.Node, int]]:
    stack: list[tuple[hou.Node, int]] = [(c, 1) for c in root.children()]
    seen = 0
    while stack:
        node, level = stack.pop(0)
        yield node, level
        seen += 1
        if seen >= MAX_NODES:
            return
        if level < depth:
            stack.extend((c, level + 1) for c in node.children())


def _messages(node: hou.Node) -> dict[str, Any]:
    """노드에 붙은 에러·경고. 쿡하지 않은 노드는 비어 있을 수 있다."""
    out: dict[str, Any] = {}
    for kind, getter in (("errors", "errors"), ("warnings", "warnings")):
        method = getattr(node, getter, None)
        if method is None:
            continue
        try:
            items = [t.strip() for t in method() if t and t.strip()]
        except hou.OperationFailed:
            items = []
        if items:
            out[kind] = [t[:MAX_TEXT] for t in items[:5]]
    return out


@tool()
def node_errors(path: str) -> dict[str, Any]:
    """노드 하나의 에러와 경고를 읽는다.

    쿡하지 않은 노드는 메시지가 비어 있을 수 있다. 그럴 때는 cook_node 를 먼저
    부른다.

    Args:
        path: 노드 경로.
    """
    node = _require(path)
    result: dict[str, Any] = {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "cooked": bool(getattr(node, "isTimeDependent", lambda: False)()) or None,
    }
    result.update(_messages(node))
    if "errors" not in result and "warnings" not in result:
        result["clean"] = True
    return result


@tool()
def find_error_nodes(root: str = "/obj", depth: int = 3) -> dict[str, Any]:
    """범위 안에서 에러나 경고가 붙은 노드를 찾는다.

    씬이 이상한데 어디가 문제인지 모를 때 먼저 부른다.

    Args:
        root: 훑기 시작할 경로.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
    """
    scope = _require(root)
    found = []
    scanned = 0
    for node, _level in _walk(scope, depth):
        scanned += 1
        messages = _messages(node)
        if messages:
            found.append({
                "path": node.path(),
                "type": node.type().name(),
                "comment": node.comment(),
                **messages,
            })
    return {
        "root": scope.path(),
        "scanned": scanned,
        "problem_count": len(found),
        "nodes": found,
        "truncated": scanned >= MAX_NODES,
    }


@tool()
def cook_node(path: str, force: bool = False) -> dict[str, Any]:
    """노드를 쿡해서 실제로 계산되는지 확인한다.

    에러는 쿡해야 드러나는 경우가 많다. 무거운 노드면 오래 걸릴 수 있다.

    Args:
        path: 노드 경로.
        force: 이미 쿡된 노드도 다시 쿡한다.
    """
    node = _require(path)
    started = time.time()
    failed = None
    try:
        node.cook(force=force)
    except hou.OperationFailed as exc:
        failed = str(exc).splitlines()[0][:MAX_TEXT]

    result: dict[str, Any] = {
        "path": node.path(),
        "seconds": round(time.time() - started, 3),
    }
    if failed:
        result["cook_failed"] = failed
    result.update(_messages(node))

    getter = getattr(node, "geometry", None)
    if getter is not None:
        try:
            geo = getter()
        except hou.OperationFailed:
            geo = None
        if geo is not None:
            result["points"] = len(geo.points())
            result["prims"] = len(geo.prims())
    return result


@tool()
def cook_status(path: str) -> dict[str, Any]:
    """노드가 쿡됐는지, 얼마나 걸렸는지, 시간에 의존하는지.

    Args:
        path: 노드 경로.
    """
    node = _require(path)
    out: dict[str, Any] = {"path": node.path(), "type": node.type().name()}
    for key, attr in (
        ("cook_count", "cookCount"),
        ("cook_time", "cookTime"),
        ("time_dependent", "isTimeDependent"),
        ("bypassed", "isBypassed"),
        ("locked", "isHardLocked"),
    ):
        method = getattr(node, attr, None)
        if method is None:
            continue
        try:
            out[key] = method()
        except hou.OperationFailed:
            pass
    out.update(_messages(node))
    return out


@tool()
@undoable("Delete unused nodes")
def delete_unused(parent: str, keep: list[str] | None = None) -> dict[str, Any]:
    """출력으로 이어지지 않는 노드를 지운다.

    시행착오로 만든 노드가 네트워크에 남아 있을 때 정리용이다. display 나 render
    플래그가 걸린 노드와 그 조상은 남긴다.

    Args:
        parent: 정리할 네트워크 경로.
        keep: 무조건 남길 노드 이름들.
    """
    network = _require(parent)
    protected: set[str] = set(keep or [])

    # 플래그가 걸린 노드와 그 조상은 결과에 기여하므로 남긴다.
    anchors = []
    for child in network.children():
        for attr in ("isDisplayFlagSet", "isRenderFlagSet"):
            method = getattr(child, attr, None)
            if method is not None:
                try:
                    if method():
                        anchors.append(child)
                        break
                except hou.OperationFailed:
                    pass

    alive: set[str] = set()
    for anchor in anchors:
        alive.add(anchor.name())
        try:
            for ancestor in anchor.inputAncestors():
                alive.add(ancestor.name())
        except hou.OperationFailed:
            pass

    removed = []
    for child in list(network.children()):
        name = child.name()
        if name in alive or name in protected:
            continue
        removed.append(name)
        child.destroy()

    return {
        "parent": network.path(),
        "kept": sorted(alive | protected),
        "removed": removed,
        "removed_count": len(removed),
    }
