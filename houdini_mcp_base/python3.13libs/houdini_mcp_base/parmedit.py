"""파라미터를 고치는 툴들. 값이 아니라 파라미터 자체를 다룬다.

`parms` 모듈은 읽기만 하고 `set_parms`(edit)는 값만 건다. 여기는 그 사이에
없던 것들이다 - 없는 파라미터를 새로 붙이고, 두 파라미터를 묶고, 실수로
바뀌지 않게 잠그고, 기본값으로 되돌린다.

파라미터 템플릿을 만드는 일은 `parmtemplate` 헬퍼에 있다. `houdini_mcp_hda`
팩이 HDA 인터페이스를 짤 때 같은 헬퍼를 쓴다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/Parm.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from .parmtemplate import KINDS, build_parm_template, component_names, describe_parm_template


def _require(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _require_parm(path: str, name: str) -> hou.Parm:
    """파라미터 하나를 찾는다. 벡터를 통째로 주려 한 경우를 짚어 준다."""
    node = _require(path)
    parm = node.parm(name)
    if parm is not None:
        return parm
    tuple_parm = node.parmTuple(name)
    if tuple_parm is not None:
        components = ", ".join(p.name() for p in tuple_parm)
        raise ValueError(
            f"{name!r} 은 벡터 파라미터입니다. 성분 이름으로 지정하세요: {components}"
        )
    raise ValueError(
        f"{path} 에 그런 파라미터가 없습니다: {name}. "
        f"list_parms 로 이름을 확인하세요."
    )


@tool()
@undoable("Add spare parameter")
def add_spare_parm(
    path: str,
    kind: str,
    name: str,
    label: str,
    size: int = 1,
    default: Any = None,
    min_value: float | None = None,
    max_value: float | None = None,
    menu_items: list[str] | None = None,
    menu_labels: list[str] | None = None,
    string_type: str = "regular",
    help_text: str | None = None,
    folder: list[str] | None = None,
) -> dict[str, Any]:
    """노드에 스페어 파라미터를 붙인다.

    노드에 없는 값을 하나 얹어 두고 다른 파라미터가 그걸 참조하게 하면, 값
    하나만 고쳐 여러 곳을 함께 바꿀 수 있다. 서브넷에 조절 손잡이를 다는 것도
    같은 일이다. 붙인 뒤 `link_parms` 로 묶는다.

    label 은 Houdini UI 에 그대로 뜨므로 영어로 쓴다. name 은 식과 `set_parms`
    가 쓰는 내부 이름이라 짧고 소문자로 짓는다.

    벡터(size > 1)를 붙이면 실제 파라미터 이름이 갈라진다 - 결과의
    `component_names` 가 `set_parms` 에 줄 이름이다.

    Args:
        path: 노드 경로.
        kind: float / int / string / toggle / menu / button / ramp_float /
            ramp_color / separator.
        name: 내부 이름. 예: wall_height
        label: UI 에 뜨는 이름. 영어로. 예: "Wall Height"
        size: 성분 수. float/int/string 에만 의미가 있다.
        default: 기본값. 벡터면 목록으로 주거나 값 하나로 전부 채운다.
        min_value: 슬라이더 최솟값.
        max_value: 슬라이더 최댓값.
        menu_items: menu 종류일 때 고를 값들.
        menu_labels: 그 값들의 표시 이름.
        string_type: string 종류일 때 regular / file / node / node_list.
        help_text: 파라미터 툴팁. 영어로.
        folder: 넣을 폴더 경로. 예: ["Controls"]. 없으면 만든다.
    """
    node = _require(path)
    if node.parm(name) is not None or node.parmTuple(name) is not None:
        raise ValueError(
            f"{path} 에 이미 {name!r} 파라미터가 있습니다. 다른 이름을 쓰거나, "
            f"스페어 파라미터라면 remove_spare_parm 으로 먼저 지우세요."
        )

    template = build_parm_template(
        kind=kind,
        name=name,
        label=label,
        size=size,
        default=default,
        min_value=min_value,
        max_value=max_value,
        menu_items=menu_items,
        menu_labels=menu_labels,
        string_type=string_type,
        help_text=help_text,
    )

    try:
        node.addSpareParmTuple(
            template, in_folder=tuple(folder or ()), create_missing_folders=True
        )
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{path} 에 {name!r} 을 붙이지 못했습니다. ({exc}) "
            f"이 노드가 스페어 파라미터를 받을 수 있는지 확인하세요."
        ) from exc

    names = component_names(template)
    return {
        "path": node.path(),
        "template": describe_parm_template(template),
        "component_names": names,
        "folder": list(folder or ()),
        "spare_count": len(node.spareParms()),
    }


@tool()
@undoable("Remove spare parameter")
def remove_spare_parm(path: str, name: str) -> dict[str, Any]:
    """스페어 파라미터를 뗀다.

    노드 본래의 파라미터는 뗄 수 없다. 스페어로 붙인 것만 지워진다.

    Args:
        path: 노드 경로.
        name: 뗄 파라미터 이름. 벡터면 튜플 이름을 준다.
    """
    node = _require(path)
    spare_names = {p.name() for p in node.spareParms()}
    if not spare_names:
        raise ValueError(f"{path} 에는 스페어 파라미터가 없습니다.")

    parm_tuple = node.parmTuple(name)
    if parm_tuple is None:
        parm = node.parm(name)
        parm_tuple = parm.tuple() if parm is not None else None
    if parm_tuple is None:
        raise ValueError(
            f"{path} 에 그런 파라미터가 없습니다: {name}. "
            f"지금 붙어 있는 스페어: {', '.join(sorted(spare_names)) or '없음'}"
        )

    members = [p.name() for p in parm_tuple]
    if not any(member in spare_names for member in members):
        raise ValueError(
            f"{name!r} 은 {node.type().name()} 의 본래 파라미터라 뗄 수 없습니다. "
            f"뗄 수 있는 것: {', '.join(sorted(spare_names))}"
        )

    node.removeSpareParmTuple(parm_tuple)
    return {
        "path": node.path(),
        "removed": members,
        "spare_count": len(node.spareParms()),
    }


@tool()
@undoable("Link parameters")
def link_parms(
    source: str,
    source_parm: str,
    target: str,
    target_parm: str,
    relative: bool = True,
) -> dict[str, Any]:
    """target 파라미터가 source 파라미터를 따라가도록 식을 건다.

    값 하나를 여러 곳이 함께 쓰게 만든다. 예를 들어 서브넷에 붙인 스페어
    파라미터를 안쪽 노드들이 참조하면, 바깥에서 하나만 고쳐 전부 바뀐다.

    기본값인 상대 경로로 걸면 두 노드를 함께 복사해도 링크가 살아 있다.
    절대 경로는 씬 어디서든 같은 곳을 가리켜야 할 때만 쓴다.

    문자열 파라미터는 `chs()`, 숫자는 `ch()` 로 건다 - 타입에 맞춰 자동으로
    고른다.

    Args:
        source: 값을 내주는 노드 경로.
        source_parm: 그 노드의 파라미터 이름.
        target: 값을 받는 노드 경로.
        target_parm: 그 노드의 파라미터 이름.
        relative: True 면 상대 경로로 건다.
    """
    src = _require_parm(source, source_parm)
    dst = _require_parm(target, target_parm)
    if src.path() == dst.path():
        raise ValueError(
            f"같은 파라미터끼리는 이을 수 없습니다: {src.path()}. "
            f"식이 자기를 참조하면 순환합니다."
        )

    src_node, dst_node = src.node(), dst.node()
    if relative:
        node_path = dst_node.relativePathTo(src_node)
    else:
        node_path = src_node.path()

    # 문자열은 ch() 로 못 읽는다. 템플릿 타입을 보고 고른다.
    is_string = src.parmTemplate().type() == hou.parmTemplateType.String
    function = "chs" if is_string else "ch"
    expression = f'{function}("{node_path}/{src.name()}")'

    try:
        dst.setExpression(expression, language=hou.exprLanguage.Hscript)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{dst.path()} 에 식을 걸지 못했습니다: {expression} ({exc})"
        ) from exc

    return {
        "source": src.path(),
        "target": dst.path(),
        "expression": expression,
        "value": dst.eval(),
    }


@tool()
@undoable("Lock parameter")
def lock_parm(path: str, names: list[str], locked: bool = True) -> dict[str, Any]:
    """파라미터를 잠그거나 푼다.

    잠근 파라미터는 값이 바뀌지 않는다 - `set_parms` 도 식도 먹지 않는다.
    시행착오로 여기저기 고치는 동안 건드리면 안 되는 값을 지킬 때 쓴다.

    노드 전체를 얼리는 것과는 다르다. 노드의 쿡 결과를 굳히려면
    `set_node_lock` 을 쓴다.

    Args:
        path: 노드 경로.
        names: 파라미터 이름들. 벡터는 성분 이름으로. 예: ["tx", "ty"]
        locked: True 면 잠그고 False 면 푼다.
    """
    if not names:
        raise ValueError("names 가 비어 있습니다. 잠글 파라미터 이름을 주세요.")
    changed = []
    for name in names:
        parm = _require_parm(path, name)
        parm.lock(locked)
        changed.append({"name": parm.name(), "locked": parm.isLocked(), "value": parm.eval()})
    return {"path": _require(path).path(), "locked": locked, "parms": changed}


@tool()
@undoable("Revert parameters")
def revert_parm(path: str, names: list[str] | None = None) -> dict[str, Any]:
    """파라미터를 기본값으로 되돌린다. 되돌리기 전 값을 함께 돌려준다.

    잘못 건 값을 지우는 데 쓴다. names 를 생략하면 **기본값에서 벗어난 것을
    전부** 되돌리므로, 그 노드에 손댄 것이 통째로 사라진다. 돌려받은 이전 값을
    보고 필요하면 `set_parms` 로 다시 걸 수 있다.

    잠긴 파라미터는 건너뛴다. 먼저 `lock_parm(locked=False)` 로 풀어야 한다.

    Args:
        path: 노드 경로.
        names: 되돌릴 파라미터 이름들. 생략하면 기본값이 아닌 것 전부.
    """
    node = _require(path)
    if names:
        targets = [_require_parm(path, name) for name in names]
    else:
        targets = [parm for parm in node.parms() if not parm.isAtDefault()]

    reverted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for parm in targets:
        if parm.isLocked():
            skipped.append({"name": parm.name(), "why": "잠겨 있습니다"})
            continue
        before = parm.eval()
        try:
            parm.revertToDefaults()
        except hou.OperationFailed as exc:
            skipped.append({"name": parm.name(), "why": str(exc).splitlines()[0][:200]})
            continue
        reverted.append({"name": parm.name(), "was": before, "now": parm.eval()})

    result: dict[str, Any] = {
        "path": node.path(),
        "comment": node.comment(),
        "reverted": reverted,
        "count": len(reverted),
    }
    if skipped:
        result["skipped"] = skipped
    return result


@tool()
def spare_parms(path: str) -> dict[str, Any]:
    """노드에 붙어 있는 스페어 파라미터를 나열한다.

    `list_parms` 는 본래 파라미터와 스페어를 섞어서 준다. 무엇이 나중에 붙인
    것인지 알아야 `remove_spare_parm` 으로 뗄 수 있다.

    Args:
        path: 노드 경로.
    """
    node = _require(path)
    parms = []
    for parm in node.spareParms():
        template = parm.parmTemplate()
        parms.append(
            {
                "name": parm.name(),
                "label": template.label(),
                "kind": type(template).__name__.replace("ParmTemplate", "").lower(),
                "value": parm.eval(),
                "locked": parm.isLocked(),
            }
        )
    return {
        "path": node.path(),
        "comment": node.comment(),
        "count": len(parms),
        "parms": parms,
        "kinds": list(KINDS),
    }
