"""노드 하나를 한 번에 설명하는 툴.

노드 하나를 이해하려면 지금까지 다섯 번을 물어야 했다 - `node_info` 로 타입과
연결을, `get_parms` 로 바뀐 값을, `node_type_help` 로 이게 무슨 노드인지,
`node_errors` 로 왜 안 나오는지, `geometry_stats` 로 결과가 얼마나 나왔는지.
왕복이 늘수록 모델이 다른 것을 놓친다.

`explain_node` 는 그 다섯을 한 번에 모아 준다. **새 정보를 만들지 않는다** -
기존 툴들이 읽는 것과 같은 것을 읽되 한 번의 호출로 합친다. 특정 항목만 자세히
봐야 하면 그때 전용 툴을 부른다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

from .context import _references
from .diagnose import _messages

MAX_PARMS = 60
"""보여줄 비기본값 파라미터 수 상한. 이보다 많으면 list_parms 로 넘긴다."""

MAX_HELP = 700
"""타입 도움말을 몇 자까지 실을지. 노드가 무엇인지 알 정도면 된다."""


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. list_children 이나 find_nodes 로 "
            f"경로를 먼저 확인하세요."
        )
    return node


def _purpose(node: hou.Node, max_help: int) -> dict[str, Any]:
    """이게 무슨 노드인지. 타입 라벨과 내장 도움말 앞부분."""
    node_type = node.type()
    out: dict[str, Any] = {"label": node_type.description()}
    if node_type.deprecated():
        out["deprecated"] = True
    try:
        text = (node_type.embeddedHelp() or "").strip()
    except hou.OperationFailed:
        text = ""
    if text:
        out["help"] = text[:max_help]
        if len(text) > max_help:
            out["help_truncated"] = True
            out["help_more"] = "node_type_help 로 전체를 볼 수 있습니다."
    else:
        # 컴파일된 빌트인은 내장 도움말이 비어 있는 경우가 많다(실측). 그럴 때는
        # 문서 URL 이라도 준다 - 없다고만 하면 다음에 할 일이 없다.
        try:
            url = node_type.defaultHelpUrl() or ""
        except hou.OperationFailed:
            url = ""
        if url:
            out["help_url"] = url
    return out


def _changed_parms(node: hou.Node) -> dict[str, Any]:
    """기본값에서 벗어난 파라미터만.

    노드마다 파라미터가 수백 개다. 전부 주면 읽히지 않고, 안 주면 이 노드가
    무엇을 하는지 알 수 없다. 손댄 것이 곧 이 노드가 하는 일이다.
    """
    changed: list[dict[str, Any]] = []
    for parm in node.parms():
        expression = None
        try:
            expression = parm.expression()
        except hou.OperationFailed:
            pass
        # 식이 걸려 있으면 값이 기본값과 같아도 손댄 것이다.
        if parm.isAtDefault() and not expression:
            continue
        entry: dict[str, Any] = {
            "name": parm.name(),
            "label": parm.parmTemplate().label(),
            "value": parm.eval(),
        }
        if expression:
            entry["expression"] = expression
        if parm.isLocked():
            entry["locked"] = True
        keys = len(parm.keyframes())
        if keys:
            entry["keyframes"] = keys
        changed.append(entry)

    out: dict[str, Any] = {"count": len(changed), "parms": changed[:MAX_PARMS]}
    if len(changed) > MAX_PARMS:
        out["truncated"] = (
            f"{len(changed)}개 중 {MAX_PARMS}개만 보입니다. "
            f"list_parms(changed_only=True) 로 나머지를 보세요."
        )
    return out


def _connections(node: hou.Node) -> dict[str, Any]:
    """입출력 연결. 입력 이름표가 있으면 몇 번이 무엇인지 함께 준다."""
    try:
        labels = list(node.inputLabels())
    except hou.OperationFailed:
        labels = []

    inputs: list[dict[str, Any]] = []
    for index, source in enumerate(node.inputs()):
        entry: dict[str, Any] = {
            "index": index,
            "from": source.path() if source else None,
        }
        if index < len(labels) and labels[index]:
            entry["label"] = labels[index]
        if source is not None:
            entry["type"] = source.type().name()
            entry["comment"] = source.comment()
        inputs.append(entry)

    outputs = []
    for connection in node.outputConnections():
        target = connection.outputItem()
        outputs.append(
            {
                "to": target.path(),
                "to_input": connection.inputIndex(),
                "comment": target.comment(),
            }
        )
    return {"inputs": inputs, "outputs": outputs}


def _cook(node: hou.Node) -> dict[str, Any]:
    """쿡 상태. 실측값만 담는다 - 없는 것은 넣지 않는다.

    주의: 걸린 시간은 `cookTime()` 이 아니라 `lastCookTime()` 이다.
    `cookTime` 은 이 버전의 HOM 에 없다(실측 확인).
    """
    out: dict[str, Any] = {}
    for key, attr in (
        ("count", "cookCount"),
        ("last_seconds", "lastCookTime"),
        ("needs_cook", "needsToCook"),
        ("time_dependent", "isTimeDependent"),
    ):
        method = getattr(node, attr, None)
        if method is None:
            continue
        try:
            out[key] = method()
        except hou.OperationFailed:
            pass
    return out


def _flags(node: hou.Node) -> dict[str, bool]:
    """켜져 있는 플래그만. 전부 False 인 목록은 읽는 데 방해가 된다."""
    out: dict[str, bool] = {}
    for name, getter in (
        ("display", "isDisplayFlagSet"),
        ("render", "isRenderFlagSet"),
        ("bypass", "isBypassed"),
        ("template", "isTemplateFlagSet"),
        ("hard_locked", "isHardLocked"),
        ("soft_locked", "isSoftLocked"),
    ):
        method = getattr(node, getter, None)
        if method is None:
            continue
        try:
            if method():
                out[name] = True
        except hou.OperationFailed:
            pass
    return out


def _geometry(node: hou.Node) -> dict[str, Any] | None:
    """결과 지오메트리 통계. 지오메트리가 없는 노드면 None."""
    getter = getattr(node, "geometry", None)
    if getter is None:
        return None
    try:
        geo = getter()
    except hou.OperationFailed as exc:
        # 쿡이 실패하면 지오메트리를 못 읽는다. 그 사실 자체가 정보다.
        return {"unavailable": str(exc).splitlines()[0][:300]}
    if geo is None:
        return None

    size = geo.boundingBox().sizevec()
    groups = [g.name() for g in geo.primGroups()] + [g.name() for g in geo.pointGroups()]
    return {
        "points": len(geo.points()),
        "prims": len(geo.prims()),
        "point_attribs": [a.name() for a in geo.pointAttribs()],
        "prim_attribs": [a.name() for a in geo.primAttribs()],
        "detail_attribs": [a.name() for a in geo.globalAttribs()],
        "groups": groups,
        "bbox_size": [size[0], size[1], size[2]],
    }


@tool()
def explain_node(path: str, max_help_chars: int = MAX_HELP) -> dict[str, Any]:
    """노드 하나를 종합해서 설명한다. 노드를 이해할 때 이걸 먼저 부른다.

    한 번에 다음을 모두 준다.

      - 무슨 노드인가: 타입, 라벨, 내장 도움말
      - 왜 있는가: 코멘트
      - 무엇을 하는가: **기본값에서 벗어난 파라미터만** (손댄 것이 곧 하는 일)
      - 무엇에 이어져 있는가: 입출력 연결과 간접 참조(Object Merge, 파라미터 식)
      - 잘 되고 있는가: 에러·경고, 쿡 횟수와 걸린 시간
      - 결과가 얼마나 나오는가: 포인트·프리미티브 수, 어트리뷰트, 바운딩 박스

    더 자세히 봐야 하면 그때 전용 툴을 부른다 - 파라미터 전체는 `list_parms`,
    도움말 전체는 `node_type_help`, 어트리뷰트 값은 `attribute_values`.

    씬을 바꾸지 않는다. 다만 지오메트리를 읽으면서 아직 쿡되지 않은 노드가 쿡될
    수 있다.

    Args:
        path: 노드 경로. 예: /obj/castle/wall_body
        max_help_chars: 타입 도움말을 몇 자까지 실을지.
    """
    node = _require(path)
    parent = node.parent()

    result: dict[str, Any] = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "category": node.type().category().name(),
        "comment": node.comment(),
        "parent": parent.path() if parent is not None else None,
        "purpose": _purpose(node, max(1, max_help_chars)),
        "changed_parms": _changed_parms(node),
        "connections": _connections(node),
    }

    if not node.comment().strip():
        result["comment_missing"] = (
            "코멘트가 없어 이 노드가 왜 있는지 알 수 없습니다. "
            "set_comment 로 남겨 두세요."
        )

    # 입력 연결 말고 파라미터·식으로 거는 참조. 왜 그 결과가 나오는지 여기 있다.
    indirect = [ref for ref in _references(node) if ref["kind"] != "input"]
    if indirect:
        result["indirect_references"] = indirect

    flags = _flags(node)
    if flags:
        result["flags"] = flags

    children = node.children()
    if children:
        result["children"] = {
            "count": len(children),
            "display": next(
                (
                    child.path()
                    for child in children
                    if getattr(child, "isDisplayFlagSet", lambda: False)()
                ),
                None,
            ),
        }

    messages = _messages(node)
    result["problems"] = messages or None

    cook = _cook(node)
    if cook:
        result["cook"] = cook

    geometry = _geometry(node)
    if geometry is not None:
        result["geometry"] = geometry

    return result
