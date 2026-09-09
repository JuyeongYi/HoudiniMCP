"""노드 트리와 의존 관계를 한 번에 읽어 컨텍스트로 만드는 툴들.

`network_graph`(info 모듈)는 직접 연결(wire)만 본다. 하지만 Houdini 씬의 의존
관계는 그것만이 아니다. 실측해 보면 이렇다.

| 참조 방식 | inputConnections | inputAncestors(ref=True) | 이 모듈 |
|---|---|---|---|
| 직접 연결 | 잡힘 | 잡힘 | 잡힘 |
| Object Merge (`objpath1`) | 안 잡힘 | **안 잡힘** | 잡힘 |
| 파라미터 식 `ch("...")` | 안 잡힘 | **안 잡힘** | 잡힘 |

그래서 두 경로를 직접 훑는다.

  - 노드 참조 파라미터: `stringType() == NodeReference` 인 파라미터를
    `evalAsNodes()` 로 푼다. Object Merge, spare input, Fetch 등이 여기 걸린다.
  - 파라미터 식: 식 문자열에서 경로처럼 생긴 것을 뽑아 노드/파라미터로 푼다.

역방향(누가 나를 참조하나)을 알려 주는 API 는 없다(`dependents`, `references`,
`parmsReferencingThis` 모두 없음). 씬을 훑는 수밖에 없어서 범위를 받는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import re
from typing import Any, Iterator

import hou

from houdini_mcp import tool

MAX_NODES = 400
"""한 번에 훑을 노드 수 상한. 큰 씬을 통째로 뱉으면 읽히지 않는다."""

_PATH_IN_EXPRESSION = re.compile(r"""["']([^"']*/[^"']*)["']""")
"""식 문자열 안에서 경로처럼 생긴 따옴표 구간."""


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _is_node_reference(parm: hou.Parm) -> bool:
    """노드 경로를 담는 문자열 파라미터인지."""
    template = parm.parmTemplate()
    string_type = getattr(template, "stringType", None)
    if string_type is None:
        return False
    try:
        return string_type() == hou.stringParmType.NodeReference
    except hou.OperationFailed:
        return False


def _resolve(candidate: str) -> str | None:
    """경로 문자열을 노드 경로로 푼다. 파라미터 경로면 그 노드를 돌려준다."""
    parm = hou.parm(candidate)
    if parm is not None:
        return parm.node().path()
    node = hou.node(candidate)
    return node.path() if node is not None else None


def _references(node: hou.Node) -> Iterator[dict[str, Any]]:
    """이 노드가 참조하는 것들을 종류별로 낸다."""
    for connection in node.inputConnections():
        yield {
            "kind": "input",
            "target": connection.inputNode().path(),
            "input_index": connection.inputIndex(),
            "output_index": connection.outputIndex(),
        }

    for parm in node.parms():
        if _is_node_reference(parm):
            raw = parm.evalAsString()
            if not raw:
                continue
            try:
                targets = parm.evalAsNodes()
            except hou.OperationFailed:
                targets = []
            if targets:
                for target in targets:
                    yield {
                        "kind": "parm",
                        "parm": parm.name(),
                        "target": target.path(),
                        "raw": raw,
                    }
            else:
                # 가리키는 대상이 없는 경우도 알려 준다. 끊어진 참조다.
                yield {"kind": "parm", "parm": parm.name(), "target": None, "raw": raw}

        try:
            expression = parm.expression()
        except hou.OperationFailed:
            continue
        seen: set[str] = set()
        for candidate in _PATH_IN_EXPRESSION.findall(expression):
            resolved = _resolve(candidate)
            if resolved is None or resolved in seen:
                continue
            seen.add(resolved)
            yield {
                "kind": "expression",
                "parm": parm.name(),
                "target": resolved,
                "expression": expression,
            }


def _walk(root: hou.Node, depth: int) -> Iterator[tuple[hou.Node, int]]:
    """root 아래 노드를 깊이 제한을 두고 훑는다."""
    stack: list[tuple[hou.Node, int]] = [(child, 1) for child in root.children()]
    count = 0
    while stack:
        node, level = stack.pop(0)
        yield node, level
        count += 1
        if count >= MAX_NODES:
            return
        if level < depth:
            stack.extend((child, level + 1) for child in node.children())


@tool()
def node_references(path: str) -> dict[str, Any]:
    """이 노드가 무엇에 의존하는지 한 번에 본다.

    직접 연결뿐 아니라 Object Merge 같은 노드 참조 파라미터와 파라미터 식까지
    포함한다. 노드가 왜 그 결과를 내는지 추적할 때 쓴다.

    Args:
        path: 노드 경로.
    """
    node = _require(path)
    refs = list(_references(node))
    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "references": refs,
        "counts": {
            kind: sum(1 for r in refs if r["kind"] == kind)
            for kind in ("input", "parm", "expression")
        },
    }


@tool()
def scene_context(path: str = "/obj", depth: int = 2) -> dict[str, Any]:
    """네트워크를 노드와 의존 관계까지 한 번에 훑어 컨텍스트로 만든다.

    씬이 어떻게 짜여 있는지 파악할 때 쓴다. list_children 을 여러 번 부르는 것보다
    낫고, network_graph 와 달리 간접 참조(Object Merge, 파라미터 식)도 포함한다.

    Args:
        path: 시작 네트워크 경로.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
    """
    root = _require(path)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    truncated = False

    for node, level in _walk(root, depth):
        entry: dict[str, Any] = {
            "path": node.path(),
            "name": node.name(),
            "type": node.type().name(),
            "comment": node.comment(),
            "depth": level,
            "children": len(node.children()),
        }
        # 어느 것이 결과인지 알 수 있게 표시 플래그를 함께 준다.
        for flag, getter in (("display", "isDisplayFlagSet"), ("render", "isRenderFlagSet")):
            method = getattr(node, getter, None)
            if method is None:
                continue
            try:
                if method():
                    entry[flag] = True
            except hou.OperationFailed:
                pass
        nodes.append(entry)

        for ref in _references(node):
            edges.append({"from": ref.get("target"), "to": node.path(), **ref})

    if len(nodes) >= MAX_NODES:
        truncated = True

    result: dict[str, Any] = {
        "root": root.path(),
        "node_count": len(nodes),
        "nodes": nodes,
        "edges": edges,
    }
    if truncated:
        result["truncated"] = (
            f"노드가 {MAX_NODES}개를 넘어 잘렸습니다. depth 를 줄이거나 하위 경로를 "
            f"지정해서 다시 부르세요."
        )
    return result


@tool()
def find_referencing_nodes(path: str, root: str = "/obj", depth: int = 3) -> dict[str, Any]:
    """누가 이 노드를 참조하는지 찾는다.

    Houdini 에는 역방향을 알려 주는 API 가 없어서 범위를 훑는다. 넓게 잡으면
    느리므로 root 로 좁히는 것이 좋다.

    Args:
        path: 참조당하는 노드 경로.
        root: 훑을 범위.
        depth: 몇 단계까지 들어갈지.
    """
    target = _require(path)
    target_path = target.path()
    scope = _require(root)

    found: list[dict[str, Any]] = []
    for node, _level in _walk(scope, depth):
        if node.path() == target_path:
            continue
        for ref in _references(node):
            if ref.get("target") == target_path:
                found.append({"path": node.path(), "comment": node.comment(), **ref})

    return {"target": target_path, "referenced_by": found, "count": len(found)}
