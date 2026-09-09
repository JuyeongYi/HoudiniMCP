"""파라미터를 들여다보는 툴들.

노드에 어떤 파라미터가 있는지, 지금 값이 무엇인지, 어떤 값을 넣을 수 있는지를
알아야 set_parms 를 제대로 쓸 수 있다. 노드마다 파라미터가 수백 개라
node_info(include_parameters=True) 로 이름만 훑는 것으로는 부족하다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool

MAX_MENU_ITEMS = 40
"""메뉴 항목을 몇 개까지 보여줄지. 노드 타입 목록처럼 수백 개인 것도 있다."""


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _describe(parm: hou.Parm, detailed: bool = False) -> dict[str, Any]:
    """파라미터 하나를 요약한다."""
    template = parm.parmTemplate()
    entry: dict[str, Any] = {
        "name": parm.name(),
        "label": template.label(),
        "type": str(template.type()).rsplit(".", 1)[-1],
        "value": parm.eval(),
        "at_default": parm.isAtDefault(),
    }

    tuple_parm = parm.tuple()
    if tuple_parm is not None and len(tuple_parm) > 1:
        # 벡터 성분이면 set_parms 에 어떤 이름을 줘야 하는지 알려 준다.
        entry["component_of"] = tuple_parm.name()
        entry["components"] = [p.name() for p in tuple_parm]

    if parm.isDisabled():
        entry["disabled"] = True
    expression = _expression(parm)
    if expression is not None:
        entry["expression"] = expression

    if detailed:
        entry.update(_details(template))
    return entry


def _expression(parm: hou.Parm) -> str | None:
    """식이 걸려 있으면 그 식. 아니면 None."""
    try:
        return parm.expression()
    except hou.OperationFailed:
        return None


def _details(template: hou.ParmTemplate) -> dict[str, Any]:
    """파라미터 템플릿에서 값 범위와 메뉴를 뽑는다."""
    out: dict[str, Any] = {}

    default = getattr(template, "defaultValue", None)
    if default is not None:
        try:
            out["default"] = default()
        except hou.OperationFailed:
            pass

    for key, getter in (("min", "minValue"), ("max", "maxValue")):
        method = getattr(template, getter, None)
        if method is None:
            continue
        try:
            out[key] = method()
        except hou.OperationFailed:
            pass

    items = getattr(template, "menuItems", None)
    if items is not None:
        try:
            values = list(items())
        except hou.OperationFailed:
            values = []
        if values:
            labels = list(getattr(template, "menuLabels", lambda: [])())
            out["menu"] = [
                {"value": v, "label": labels[i] if i < len(labels) else v}
                for i, v in enumerate(values[:MAX_MENU_ITEMS])
            ]
            if len(values) > MAX_MENU_ITEMS:
                out["menu_truncated"] = len(values)

    help_text = getattr(template, "help", None)
    if help_text is not None:
        try:
            text = help_text()
        except hou.OperationFailed:
            text = ""
        if text:
            out["help"] = text
    return out


@tool()
def list_parms(
    path: str, pattern: str = "*", changed_only: bool = False
) -> dict[str, Any]:
    """노드의 파라미터를 이름·라벨·타입·현재 값과 함께 나열한다.

    노드마다 파라미터가 수백 개라, 기본적으로 패턴으로 걸러 쓰는 것을 권한다.

    Args:
        path: 노드 경로.
        pattern: 이름 패턴. 예: "size*", "t?", "*color*"
        changed_only: True 면 기본값과 다른 것만.
    """
    node = _require(path)
    matched = [
        parm
        for parm in node.globParms(pattern)
        if not (changed_only and parm.isAtDefault())
    ]
    return {
        "path": node.path(),
        "type": node.type().name(),
        "count": len(matched),
        "parms": [_describe(parm) for parm in matched],
    }


@tool()
def parm_info(path: str, name: str) -> dict[str, Any]:
    """파라미터 하나를 자세히 본다. 기본값, 범위, 메뉴 항목, 도움말.

    어떤 값을 넣을 수 있는지 모를 때 이걸 먼저 본다.

    Args:
        path: 노드 경로.
        name: 파라미터 이름. 예: sizex, type
    """
    node = _require(path)
    parm = node.parm(name)
    if parm is None:
        tuple_parm = node.parmTuple(name)
        if tuple_parm is not None:
            components = ", ".join(p.name() for p in tuple_parm)
            raise ValueError(
                f"{name!r} 은 벡터 파라미터입니다. 성분 이름으로 보세요: {components}"
            )
        raise ValueError(f"{path} 에 그런 파라미터가 없습니다: {name}")
    return _describe(parm, detailed=True)
