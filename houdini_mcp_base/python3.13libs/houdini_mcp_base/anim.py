"""파라미터에 식과 키프레임을 거는 툴들.

set_parms 는 값만 건다. 값 대신 식을 걸거나 시간에 따라 변하게 하려면 다른
경로가 필요하다. 컨텍스트를 가리지 않으므로 base 에 둔다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

LANGUAGES = {"hscript": hou.exprLanguage.Hscript, "python": hou.exprLanguage.Python}

# 보간 이름 -> Houdini 채널 식. 값 키에 이 식을 걸어 보간 방식을 정한다.
INTERP_EXPR = {
    "constant": "constant",
    "linear": "linear",
    "cubic": "cubic",
    "bezier": "bezier",
    "ease": "ease",
    "easein": "easein",
    "easeout": "easeout",
    "spline": "spline",
}
INTERPOLATIONS = tuple(INTERP_EXPR)


def _require_parm(path: str, name: str) -> hou.Parm:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    parm = node.parm(name)
    if parm is not None:
        return parm
    tuple_parm = node.parmTuple(name)
    if tuple_parm is not None:
        components = ", ".join(p.name() for p in tuple_parm)
        raise ValueError(
            f"{name!r} 은 벡터 파라미터입니다. 성분 이름으로 거세요: {components}"
        )
    raise ValueError(f"{path} 에 그런 파라미터가 없습니다: {name}")


@tool()
def get_expression(path: str, name: str) -> dict[str, Any]:
    """파라미터에 걸린 식을 읽는다.

    값만 보면 그 값이 고정인지 계산된 것인지 알 수 없다.

    Args:
        path: 노드 경로.
        name: 파라미터 이름.
    """
    parm = _require_parm(path, name)
    result: dict[str, Any] = {
        "path": path,
        "name": name,
        "value": parm.eval(),
        "keyframes": len(parm.keyframes()),
    }
    try:
        result["expression"] = parm.expression()
        result["language"] = str(parm.expressionLanguage()).rsplit(".", 1)[-1].lower()
    except hou.OperationFailed:
        result["expression"] = None
    return result


@tool()
@undoable("Set expression")
def set_expression(
    path: str, name: str, expression: str, language: str = "hscript"
) -> dict[str, Any]:
    """파라미터에 식을 건다.

    다른 노드 값을 참조하거나 프레임에 따라 변하게 할 때 쓴다.
    예: `ch("../box1/sizex")`, `$F * 0.1`

    Args:
        path: 노드 경로.
        name: 파라미터 이름.
        expression: 식 문자열.
        language: hscript 또는 python.
    """
    if language not in LANGUAGES:
        raise ValueError(f"language 는 {', '.join(LANGUAGES)} 중 하나여야 합니다: {language!r}")
    parm = _require_parm(path, name)
    try:
        parm.setExpression(expression, language=LANGUAGES[language])
    except hou.OperationFailed as exc:
        raise ValueError(f"식을 걸지 못했습니다: {expression!r} ({exc})") from exc
    return {"path": path, "name": name, "expression": expression, "value": parm.eval()}


@tool()
@undoable("Clear expression")
def clear_expression(path: str, name: str, keep_value: bool = True) -> dict[str, Any]:
    """파라미터의 식을 떼고 보통 값으로 되돌린다.

    Args:
        path: 노드 경로.
        name: 파라미터 이름.
        keep_value: 식이 마지막으로 낸 값을 그대로 남긴다.
    """
    parm = _require_parm(path, name)
    value = parm.eval()
    try:
        parm.deleteAllKeyframes()
    except hou.OperationFailed:
        pass
    if keep_value:
        parm.set(value)
    return {"path": path, "name": name, "value": parm.eval()}


@tool()
@undoable("Set keyframe")
def set_keyframe(
    path: str,
    name: str,
    frame: float,
    value: float | None = None,
    expression: str | None = None,
    interpolation: str = "cubic",
) -> dict[str, Any]:
    """파라미터에 키프레임을 찍는다.

    value 나 expression 중 하나를 준다. 둘 다 생략하면 그 프레임의 현재 값을
    그대로 키로 굳힌다.

    Args:
        path: 노드 경로.
        name: 파라미터 이름.
        frame: 프레임 번호.
        value: 키의 값.
        expression: 값 대신 걸 식.
        interpolation: constant / linear / cubic / bezier / ease 등.
    """
    if interpolation not in INTERPOLATIONS:
        raise ValueError(
            f"interpolation 은 {', '.join(INTERPOLATIONS)} 중 하나여야 합니다: {interpolation!r}"
        )
    parm = _require_parm(path, name)

    key = hou.Keyframe()
    key.setFrame(frame)
    if expression is not None:
        key.setExpression(expression, hou.exprLanguage.Hscript)
    else:
        key.setValue(parm.evalAtFrame(frame) if value is None else value)
        # Houdini 는 보간을 식으로 표현한다. linear() / cubic() / constant() 처럼.
        key.setExpression(f"{INTERP_EXPR[interpolation]}()", hou.exprLanguage.Hscript)

    try:
        parm.setKeyframe(key)
    except hou.OperationFailed as exc:
        raise ValueError(f"키프레임을 찍지 못했습니다: {exc}") from exc

    return {
        "path": path,
        "name": name,
        "frame": frame,
        "value": parm.evalAtFrame(frame),
        "keyframes": len(parm.keyframes()),
    }


@tool()
def get_keyframes(path: str, name: str) -> dict[str, Any]:
    """파라미터의 키프레임 목록.

    Args:
        path: 노드 경로.
        name: 파라미터 이름.
    """
    parm = _require_parm(path, name)
    keys = []
    for key in parm.keyframes():
        entry: dict[str, Any] = {"frame": key.frame()}
        try:
            entry["value"] = key.value()
        except hou.OperationFailed:
            pass
        try:
            expression = key.expression()
            if expression:
                entry["expression"] = expression
        except hou.OperationFailed:
            pass
        keys.append(entry)
    return {"path": path, "name": name, "count": len(keys), "keyframes": keys}


@tool()
@undoable("Delete keyframes")
def delete_keyframes(
    path: str, name: str, start: float | None = None, end: float | None = None
) -> dict[str, Any]:
    """키프레임을 지운다. 범위를 주면 그 구간만.

    Args:
        path: 노드 경로.
        name: 파라미터 이름.
        start: 지울 구간 시작 프레임. 생략하면 전부.
        end: 지울 구간 끝 프레임.
    """
    parm = _require_parm(path, name)
    before = len(parm.keyframes())
    if start is None and end is None:
        parm.deleteAllKeyframes()
    else:
        rng = hou.playbar.frameRange()
        parm.deleteKeyframesInRange(
            start if start is not None else rng[0],
            end if end is not None else rng[1],
        )
    return {
        "path": path,
        "name": name,
        "removed": before - len(parm.keyframes()),
        "remaining": len(parm.keyframes()),
    }


@tool()
def list_animated_parms(path: str) -> dict[str, Any]:
    """노드에서 키프레임이나 식이 걸린 파라미터를 찾는다.

    Args:
        path: 노드 경로.
    """
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")

    animated = []
    for parm in node.parms():
        keys = len(parm.keyframes())
        expression = None
        try:
            expression = parm.expression()
        except hou.OperationFailed:
            pass
        if keys or expression:
            entry: dict[str, Any] = {"name": parm.name(), "value": parm.eval()}
            if keys:
                entry["keyframes"] = keys
            if expression:
                entry["expression"] = expression
            animated.append(entry)

    return {"path": node.path(), "count": len(animated), "parms": animated}
