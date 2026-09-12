"""wrangle 노드를 만들고, 고치고, 찾고, 진단한다.

create_wrangle 과 update_wrangle 은 **코드를 씬에 넣기 전에 먼저 컴파일한다.**
컴파일이 실패하면 노드를 만들지도, 기존 코드를 덮지도 않는다. 모델이 깨진 VEX 를
씬에 남기지 않게 하기 위해서다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Iterator

import hou

from houdini_mcp import tool, undoable

from . import snippet
from .validate import (
    DEFAULT_CONTEXT,
    check,
    cross_check,
    format_errors,
    geometry_attribs,
)

SNIPPET_PARMS = ("snippet", "vexsnippet")
"""VEX 스니펫이 들어가는 문자열 파라미터 이름. 노드 타입마다 다르다(실측)."""

VOP_CODE_TYPES = frozenset({"snippet", "inline"})
"""VOP 카테고리에서 `code` 파라미터에 VEX 를 담는 타입."""

RUN_OVER_INDEX = {"detail": 0, "prim": 1, "primitive": 1, "point": 2, "vertex": 3}
"""attribwrangle 의 class 파라미터 메뉴 순서."""

MAX_NODES = 500
MAX_PREVIEW = 240


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _walk(root: hou.Node, depth: int) -> Iterator[hou.Node]:
    stack: list[tuple[hou.Node, int]] = [(c, 1) for c in root.children()]
    seen = 0
    while stack:
        node, level = stack.pop(0)
        yield node
        seen += 1
        if seen >= MAX_NODES:
            return
        if level < depth:
            stack.extend((c, level + 1) for c in node.children())


def snippet_parm(node: hou.Node) -> hou.Parm | None:
    """노드에서 VEX 스니펫 파라미터를 찾는다. wrangle 이 아니면 None."""
    names = list(SNIPPET_PARMS)
    category = node.type().category().name()
    if category == "Vop" and node.type().name() in VOP_CODE_TYPES:
        names.append("code")
    for name in names:
        parm = node.parm(name)
        if parm is None:
            continue
        if parm.parmTemplate().type() == hou.parmTemplateType.String:
            return parm
    return None


def _require_snippet_parm(node: hou.Node) -> hou.Parm:
    parm = snippet_parm(node)
    if parm is None:
        raise ValueError(
            f"{node.path()} 는 wrangle 이 아닙니다(타입 {node.type().name()}). "
            f"VEX 스니펫 파라미터({', '.join(SNIPPET_PARMS)})가 없습니다. "
            f"list_wrangles 로 씬의 wrangle 을 먼저 찾아 보세요."
        )
    return parm


def _run_over_of(node: hou.Node, fallback: str = "point") -> str:
    """노드의 class 파라미터에서 도는 요소를 읽는다. 없으면 fallback."""
    parm = node.parm("class")
    if parm is None:
        return fallback
    index = parm.eval()
    for name, value in RUN_OVER_INDEX.items():
        if value == index and name != "primitive":
            return name
    return fallback


def _cook_report(node: hou.Node) -> dict[str, Any]:
    """쿡해 보고 결과를 요약한다. 만들어 놓고 되는지 모르는 일이 없게."""
    report: dict[str, Any] = {}
    try:
        node.cook(force=True)
    except hou.OperationFailed as exc:
        report["cook_failed"] = str(exc).splitlines()[0]

    for kind in ("errors", "warnings"):
        method = getattr(node, kind, None)
        if method is None:
            continue
        try:
            items = [t.strip() for t in method() if t and t.strip()]
        except hou.OperationFailed:
            items = []
        if items:
            report[kind] = [t[:600] for t in items[:5]]

    getter = getattr(node, "geometry", None)
    if getter is not None:
        try:
            geo = getter()
        except hou.OperationFailed:
            geo = None
        if geo is not None:
            report["points"] = len(geo.points())
            report["prims"] = len(geo.prims())
    return report


def _reject_on_error(result: dict[str, Any], what: str) -> None:
    if result["ok"]:
        return
    raise ValueError(
        f"VEX 가 컴파일되지 않아 {what}. 아래를 고쳐서 다시 부르세요.\n"
        f"{format_errors(result)}"
    )


def _missing_channels(node: hou.Node, channels: list[dict[str, Any]]) -> list[dict]:
    """ch() 가 가리키는데 노드에 없는 파라미터. 0 으로 읽히므로 조용히 틀린다."""
    missing = []
    for channel in channels:
        if node.parm(channel["name"]) is None and node.parmTuple(channel["name"]) is None:
            missing.append(channel)
    return missing


# ---- 툴 ---------------------------------------------------------------


@tool()
@undoable("Create wrangle")
def create_wrangle(
    parent: str,
    code: str,
    comment: str,
    node_type: str = "attribwrangle",
    name: str | None = None,
    run_over: str = "point",
    group: str | None = None,
    input_path: str | None = None,
    attrib_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    """wrangle 노드를 만들고 VEX 코드를 넣는다. 넣기 전에 먼저 컴파일해 본다.

    컴파일이 실패하면 노드를 만들지 않고 에러를 줄·열 번호와 함께 돌려준다.
    깨진 코드가 씬에 남지 않는다.

    만든 뒤에는 쿡해서 결과(점·프리미티브 수, 노드 에러)를 함께 돌려준다.
    입력을 연결했다면 코드가 읽는 어트리뷰트가 실제로 있는지도 대조한다.

    name 은 무엇을 하는지 드러나게 짓는다. attribwrangle1 같은 기본 이름은
    나중에 그래프를 읽을 수 없게 만든다. 좋은 예: scatter_noise,
    orient_to_normal.

    Args:
        parent: 부모 네트워크 경로. 예: /obj/geo1
        code: wrangle 스니펫. `@P.y += 1;` 처럼 `@` 문법을 그대로 쓴다.
        comment: 이 wrangle 이 무엇을 하는지. 필수. 씬 파일에 저장되므로 영어로
            쓴다. 예: "Push points up by noise"
        node_type: 만들 노드 타입. attribwrangle, pointwrangle, volumewrangle,
            deformationwrangle, popwrangle, geometrywrangle, channelwrangle 등.
        name: 노드 이름. 역할이 드러나게, 영어로. 생략하면 Houdini 가 정한다.
        run_over: 도는 요소. "point", "prim", "vertex", "detail". class
            파라미터가 있는 노드에만 적용된다.
        group: 처리할 그룹 이름. 생략하면 전부.
        input_path: 첫 입력으로 연결할 노드 경로.
        attrib_types: 접두사를 쓰지 않은 어트리뷰트의 타입 지정.
            예: {"myvec": "vector"}
    """
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 wrangle 이 무엇을 하는지 적어 주세요."
        )
    if run_over not in RUN_OVER_INDEX:
        raise ValueError(
            f"run_over 는 {', '.join(sorted(RUN_OVER_INDEX))} 중 하나여야 합니다: "
            f"{run_over!r}"
        )

    parent_node = _require(parent)
    result = check(code, context=DEFAULT_CONTEXT, attrib_types=attrib_types)
    _reject_on_error(result, "노드를 만들지 않았습니다")

    try:
        node = parent_node.createNode(node_type, node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent} 안에 {node_type!r} 노드를 만들지 못했습니다. 그 네트워크에서 "
            f"쓸 수 있는 타입인지 확인하세요. SOP 라면 attribwrangle, DOP 라면 "
            f"geometrywrangle 입니다. ({exc})"
        ) from exc

    parm = snippet_parm(node)
    if parm is None:
        node.destroy()
        raise ValueError(
            f"{node_type!r} 에는 VEX 스니펫 파라미터가 없습니다. wrangle 계열 노드 "
            f"타입을 고르세요: attribwrangle, pointwrangle, volumewrangle, "
            f"deformationwrangle, popwrangle, geometrywrangle, channelwrangle."
        )
    parm.set(code)

    class_parm = node.parm("class")
    if class_parm is not None:
        class_parm.set(RUN_OVER_INDEX[run_over])
    if group:
        group_parm = node.parm("group")
        if group_parm is None:
            raise ValueError(
                f"{node_type!r} 에는 group 파라미터가 없습니다. group 을 빼고 다시 "
                f"부르세요."
            )
        group_parm.set(group)

    if input_path:
        node.setFirstInput(_require(input_path))

    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    return _report(node, parm, result, run_over=_run_over_of(node, run_over))


@tool()
@undoable("Update wrangle code")
def update_wrangle(
    path: str,
    code: str,
    comment: str | None = None,
    attrib_types: dict[str, str] | None = None,
) -> dict[str, Any]:
    """wrangle 의 VEX 코드를 갈아 끼운다. 넣기 전에 먼저 컴파일해 본다.

    컴파일이 실패하면 기존 코드를 그대로 두고 에러만 돌려준다. 고치려다 더
    망가지는 일이 없다.

    Args:
        path: wrangle 노드 경로.
        code: 새 스니펫.
        comment: 코멘트도 함께 바꾼다. 하는 일이 달라졌으면 같이 고친다.
            씬에 저장되므로 영어로 쓴다.
        attrib_types: 접두사를 쓰지 않은 어트리뷰트의 타입 지정.
    """
    node = _require(path)
    parm = _require_snippet_parm(node)

    result = check(code, context=DEFAULT_CONTEXT, attrib_types=attrib_types)
    _reject_on_error(result, "코드를 바꾸지 않았습니다")

    previous = parm.evalAsString()
    parm.set(code)
    if comment is not None:
        if not comment.strip():
            raise ValueError("comment 가 비어 있습니다.")
        node.setComment(comment.strip())
        node.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    report = _report(node, parm, result, run_over=_run_over_of(node))
    report["previous_line_count"] = len(previous.splitlines())
    return report


def _report(
    node: hou.Node,
    parm: hou.Parm,
    result: dict[str, Any],
    *,
    run_over: str,
) -> dict[str, Any]:
    """만들거나 고친 뒤의 상태를 한 덩어리로. 모델이 다음을 정할 수 있게."""
    report: dict[str, Any] = {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "snippet_parm": parm.name(),
        "line_count": result["line_count"],
        "bindings": result["bindings"],
        "run_over": run_over,
    }
    if result["warnings"]:
        report["warnings"] = result["warnings"]
    for key in ("assumed_float", "type_conflicts"):
        if result.get(key):
            report[key] = result[key]

    channels = result["channels"]
    if channels:
        report["channels"] = channels
        missing = _missing_channels(node, channels)
        if missing:
            report["missing_channel_parms"] = missing
            report["channel_hint"] = (
                "ch() 가 가리키는 파라미터가 노드에 없습니다. 0 으로 읽히므로 "
                "에러는 나지 않습니다. 노드 파라미터 인터페이스에서 스페어 "
                "파라미터를 만들거나(Houdini UI 의 'Create Spare Parameters'), "
                "값을 코드에 직접 쓰세요."
            )

    report["cook"] = _cook_report(node)

    upstream = node.inputs()[0] if node.inputs() else None
    if upstream is not None:
        attribs = geometry_attribs(upstream)
        if attribs:
            _body, bindings, _conflicts = snippet.translate(parm.evalAsString())
            report["input"] = {"path": upstream.path(), "comment": upstream.comment()}
            report["cross_check"] = cross_check(bindings, attribs, run_over=run_over)
    return report


@tool()
def list_wrangles(root: str = "/obj", depth: int = 3, contains: str | None = None) -> dict[str, Any]:
    """범위 안의 wrangle 과 그 코드를 훑는다.

    씬에 VEX 가 어디에 얼마나 들어 있는지 먼저 본다. 코드는 앞부분만 보여 주고,
    전체가 필요하면 diagnose_wrangle 로 하나씩 본다.

    Args:
        root: 훑기 시작할 경로.
        depth: 하위 네트워크를 몇 단계까지 따라 들어갈지.
        contains: 코드에 이 문자열이 든 것만. 예: "@Cd"
    """
    scope = _require(root)
    found: list[dict[str, Any]] = []
    scanned = 0
    for node in _walk(scope, depth):
        scanned += 1
        # wrangle 은 안에 attribvop 같은 내부 노드를 품고 있다. 잠긴 HDA 안쪽은
        # 사용자가 고칠 수 있는 것이 아니므로 목록에서 뺀다.
        if getattr(node, "isInsideLockedHDA", lambda: False)():
            continue
        parm = snippet_parm(node)
        if parm is None:
            continue
        code = parm.evalAsString()
        if contains and contains not in code:
            continue
        stripped = code.strip()
        found.append(
            {
                "path": node.path(),
                "type": node.type().name(),
                "comment": node.comment(),
                "snippet_parm": parm.name(),
                "line_count": len(code.splitlines()),
                "empty": not stripped,
                "preview": stripped[:MAX_PREVIEW],
                "truncated": len(stripped) > MAX_PREVIEW,
                "has_errors": bool(node.errors()),
            }
        )
    return {
        "root": scope.path(),
        "scanned": scanned,
        "count": len(found),
        "wrangles": found,
        "truncated": scanned >= MAX_NODES,
    }


@tool()
def diagnose_wrangle(path: str, cook: bool = True) -> dict[str, Any]:
    """wrangle 하나를 컴파일 에러·쿡 에러·어트리뷰트 세 방향에서 본다.

    셋을 한 번에 보는 것이 핵심이다. 컴파일은 통과하는데 결과가 안 나오는
    wrangle 은 대개 없는 어트리뷰트를 읽고 있거나 ch() 가 가리키는 파라미터가
    없다. 둘 다 에러가 아니라서 노드는 조용히 0 을 읽는다.

    Args:
        path: wrangle 노드 경로.
        cook: 노드를 쿡해서 실제 에러도 볼지. 무거우면 False 로 둔다.
    """
    node = _require(path)
    parm = _require_snippet_parm(node)
    code = parm.evalAsString()

    run_over = _run_over_of(node)
    result = check(code, context=DEFAULT_CONTEXT)

    report: dict[str, Any] = {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "snippet_parm": parm.name(),
        "run_over": run_over,
        "code": code,
        "compile": {
            "ok": result["ok"],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "summary": result["summary"],
        },
        "bindings": result["bindings"],
    }
    for key in ("assumed_float", "type_conflicts"):
        if result.get(key):
            report[key] = result[key]

    channels = result["channels"]
    if channels:
        report["channels"] = channels
        missing = _missing_channels(node, channels)
        if missing:
            report["missing_channel_parms"] = missing

    upstream = node.inputs()[0] if node.inputs() else None
    if upstream is None:
        report["input"] = None
    else:
        attribs = geometry_attribs(upstream)
        report["input"] = {"path": upstream.path(), "comment": upstream.comment()}
        if attribs:
            _body, bindings, _conflicts = snippet.translate(code)
            report["cross_check"] = cross_check(bindings, attribs, run_over=run_over)

    if cook:
        report["cook"] = _cook_report(node)

    report["summary"] = _diagnosis(report)
    return report


def _diagnosis(report: dict[str, Any]) -> str:
    """무엇부터 고쳐야 하는지 한 줄로."""
    compile_result = report["compile"]
    if not compile_result["ok"]:
        return compile_result["summary"]
    cooked = report.get("cook", {})
    if cooked.get("errors"):
        return f"컴파일은 되는데 쿡에서 막힙니다: {cooked['errors'][0]}"
    missing = report.get("cross_check", {}).get("missing") or []
    if missing:
        names = ", ".join(entry["name"] for entry in missing)
        return (
            f"입력에 없는 어트리뷰트를 읽습니다: {names}. 0 으로 읽히므로 에러는 "
            f"나지 않지만 결과가 비어 보일 수 있습니다."
        )
    if report.get("missing_channel_parms"):
        names = ", ".join(entry["name"] for entry in report["missing_channel_parms"])
        return (
            f"ch() 가 가리키는 파라미터가 노드에 없습니다: {names}. 0 으로 "
            f"읽힙니다."
        )
    mismatched = report.get("cross_check", {}).get("type_mismatch") or []
    if mismatched:
        first = mismatched[0]
        return (
            f"타입이 어긋납니다: {first['name']} 은 입력에서 "
            f"{first['geometry_type']} 인데 코드는 {first['snippet_type']} 로 "
            f"읽습니다. 접두사를 맞추세요."
        )
    return "컴파일·쿡·어트리뷰트 모두 문제 없습니다."
