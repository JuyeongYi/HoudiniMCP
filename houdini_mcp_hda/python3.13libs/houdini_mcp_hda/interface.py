"""HDA **정의**의 파라미터 인터페이스를 짓는다.

`houdini_mcp_base` 의 parmedit 과 헷갈리면 안 된다.

| | base 의 `add_spare_parm` | 여기의 `add_hda_parm` |
|---|---|---|
| 대상 | 노드 인스턴스 하나 | HDA 정의 |
| 범위 | 그 노드에만 남는다 | 그 타입의 **모든 인스턴스**가 함께 바뀐다 |
| 저장 | hip 파일 | .hda 파일 |

파라미터 템플릿을 만드는 일은 base 의 `parmtemplate` 헬퍼를 그대로 쓴다.
DialogScript 문자열을 조립하지 않는다 — 기존 구현들이 거기서 깨졌다.

`promote_parm` 은 내부 노드의 템플릿을 **그대로 꺼내 올린다.** 이름·타입·범위·
메뉴·기본값이 자동으로 따라오고, 올린 뒤 내부 파라미터에 식을 걸어 묶는다.
문자열 조립으로는 이게 안 된다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/ParmTemplateGroup.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable
from houdini_mcp_base.parmtemplate import KINDS, build_parm_template, component_names

from ._common import (
    definition_summary,
    describe_entry,
    describe_group,
    interface_parm_count,
    persist,
    require_definition,
    top_level_names,
)


def _reject_conflict(group: hou.ParmTemplateGroup, name: str) -> None:
    if group.find(name) is not None:
        raise ValueError(
            f"인터페이스에 이미 {name!r} 파라미터가 있습니다. 다른 이름을 쓰거나 "
            f"remove_hda_parm 으로 먼저 지우세요."
        )


def _place(
    group: hou.ParmTemplateGroup, template: hou.ParmTemplate, folder: list[str] | None
) -> None:
    """템플릿을 그룹에 넣는다. 폴더를 주면 없을 때 만든다."""
    if not folder:
        group.append(template)
        return
    existing = group.findFolder(tuple(folder))
    if existing is None:
        # 중첩 폴더는 바깥부터 하나씩 만든다. 한 번에 만드는 API 가 없다.
        trail: list[str] = []
        for label in folder:
            trail.append(label)
            if group.findFolder(tuple(trail)) is not None:
                continue
            new_folder = hou.FolderParmTemplate(
                label.strip().lower().replace(" ", "_"), label
            )
            if len(trail) == 1:
                group.append(new_folder)
            else:
                group.appendToFolder(group.findFolder(tuple(trail[:-1])), new_folder)
        existing = group.findFolder(tuple(folder))
    group.appendToFolder(existing, template)


def _apply_group(
    definition: hou.HDADefinition, group: hou.ParmTemplateGroup
) -> None:
    try:
        definition.setParmTemplateGroup(group)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{definition.nodeTypeName()} 의 인터페이스를 바꾸지 못했습니다: {exc} "
            f"hda_interface 로 지금 구조를 확인하세요."
        ) from exc


def _interface_result(
    definition: hou.HDADefinition, extra: dict[str, Any]
) -> dict[str, Any]:
    group = definition.parmTemplateGroup()
    result: dict[str, Any] = {
        "definition": definition_summary(definition),
        "interface": describe_group(group),
        "interface_parm_count": interface_parm_count(group),
    }
    result.update(extra)
    return result


@tool()
def hda_interface(target: str) -> dict[str, Any]:
    """HDA 정의의 파라미터 인터페이스를 폴더까지 펼쳐 읽는다.

    인스턴스 하나의 `list_parms` 와 다르다. 여기는 **정의**가 무엇을 내놓기로
    했는지를 보여준다 — 폴더 구조, 기본값, 메뉴, 성분 이름까지.

    벡터 파라미터는 실제 이름이 갈라진다. `component_names` 가 `set_parms` 에
    줘야 할 이름이다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름
            (Sop/ns::brick_maker::1.0).
    """
    definition = require_definition(target)
    group = definition.parmTemplateGroup()
    return {
        "definition": definition_summary(definition),
        "version": definition.version(),
        "icon": definition.icon(),
        "interface": describe_group(group),
        "interface_parm_count": interface_parm_count(group),
        "top_level": top_level_names(group),
        "kinds": list(KINDS),
    }


@tool()
@undoable("Add HDA parameter")
def add_hda_parm(
    target: str,
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
    """HDA 정의의 인터페이스에 파라미터를 새로 붙이고 .hda 파일에 저장한다.

    그 타입의 **모든 인스턴스**에 나타난다. 노드 하나에만 붙이려면 base 의
    `add_spare_parm` 을 쓴다.

    내부 노드에 이미 있는 값을 바깥으로 내보내려면 이것 말고 `promote_parm` 을
    쓴다 — 타입·범위·메뉴가 자동으로 따라오고 식까지 걸린다. 여기는 내부에
    대응이 없는 새 손잡이를 만들 때다.

    label 은 Houdini UI 에 그대로 뜨므로 영어로 쓴다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름.
        kind: float / int / string / toggle / menu / button / ramp_float /
            ramp_color / separator.
        name: 내부 이름. 식과 set_parms 가 쓴다. 예: wall_height
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
    definition = require_definition(target)
    group = definition.parmTemplateGroup()
    _reject_conflict(group, name)

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
    _place(group, template, folder)
    _apply_group(definition, group)
    saved = persist(definition)

    return _interface_result(
        definition,
        {
            "added": describe_entry(template),
            "component_names": component_names(template),
            "folder": list(folder or ()),
            "saved_to": saved,
        },
    )


@tool()
@undoable("Promote HDA parameter")
def promote_parm(
    path: str,
    inner: str,
    parm: str,
    name: str | None = None,
    label: str | None = None,
    folder: list[str] | None = None,
    link: bool = True,
) -> dict[str, Any]:
    """내부 노드의 파라미터를 HDA 인터페이스로 끌어올리고 식으로 묶는다.

    내부 템플릿을 **그대로** 꺼내므로 타입·성분 수·범위·메뉴·기본값이 따라온다.
    올린 뒤 내부 파라미터마다 `ch("../<올린 이름>")` 식을 걸어, 바깥에서 값을
    바꾸면 안쪽이 따라오게 한다.

    내용물이 잠긴 인스턴스면 먼저 편집을 허용한 뒤 식을 걸고, 정의를 그 인스턴스
    내용으로 다시 굽는다. 즉 이 툴은 인터페이스와 내용물을 **함께** 저장한다.

    Args:
        path: HDA 인스턴스의 노드 경로. 내부 노드에 닿으려면 인스턴스가 필요하다.
        inner: 그 안쪽 노드의 상대 경로. 예: brick_body
        parm: 올릴 파라미터 이름. 벡터는 튜플 이름으로 준다. 예: size
        name: 인터페이스에서 쓸 새 이름. 생략하면 원래 이름 그대로.
        label: UI 에 뜨는 이름. 영어로. 생략하면 원래 라벨 그대로.
        folder: 넣을 폴더 경로. 예: ["Controls"]. 없으면 만든다.
        link: True 면 내부 파라미터에 식을 걸어 묶는다. False 면 올리기만 한다.
    """
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. HDA 인스턴스의 경로를 주세요."
        )
    definition = node.type().definition()
    if definition is None:
        raise ValueError(
            f"{path} 는 {node.type().name()} 타입이라 HDA 가 아닙니다. "
            f"create_hda 로 먼저 구우세요."
        )

    inner_node = node.node(inner)
    if inner_node is None:
        children = ", ".join(child.name() for child in node.children()) or "(없음)"
        raise ValueError(
            f"{path} 안에 {inner!r} 노드가 없습니다. 그 안의 노드: {children}"
        )

    parm_tuple = inner_node.parmTuple(parm)
    if parm_tuple is None:
        single = inner_node.parm(parm)
        parm_tuple = single.tuple() if single is not None else None
    if parm_tuple is None:
        raise ValueError(
            f"{inner_node.path()} 에 {parm!r} 파라미터가 없습니다. "
            f"list_parms 로 이름을 확인하세요."
        )

    template = parm_tuple.parmTemplate()
    if name:
        template.setName(name)
    if label:
        template.setLabel(label)

    group = definition.parmTemplateGroup()
    _reject_conflict(group, template.name())
    _place(group, template, folder)
    _apply_group(definition, group)

    promoted_names = component_names(template)
    links: list[dict[str, str]] = []
    if link:
        # 잠긴 내용물에는 식을 걸 수 없다. 편집을 열고 나면 정의를 이 인스턴스
        # 내용으로 다시 구워야 다른 인스턴스에도 식이 간다.
        node.allowEditingOfContents()
        relative = inner_node.relativePathTo(node)
        is_string = template.type() == hou.parmTemplateType.String
        function = "chs" if is_string else "ch"
        for component, promoted in zip(parm_tuple, promoted_names):
            expression = f'{function}("{relative}/{promoted}")'
            component.setExpression(expression, language=hou.exprLanguage.Hscript)
            links.append({"inner": component.path(), "expression": expression})

    saved = persist(definition, template_node=node if link else None)

    return _interface_result(
        definition,
        {
            "path": node.path(),
            "inner": inner_node.path(),
            "promoted": describe_entry(template),
            "component_names": promoted_names,
            "links": links,
            "linked": link,
            "values": list(node.parmTuple(template.name()).eval())
            if node.parmTuple(template.name()) is not None
            else None,
            "saved_to": saved,
        },
    )


@tool()
@undoable("Remove HDA parameter")
def remove_hda_parm(target: str, name: str) -> dict[str, Any]:
    """HDA 인터페이스에서 파라미터나 폴더를 뗀다.

    폴더 이름을 주면 그 안의 파라미터까지 통째로 사라진다. 떼기 전에
    `hda_interface` 로 구조를 확인한다. 그 타입의 모든 인스턴스에서 사라지며,
    그 파라미터를 참조하던 내부 식은 깨진다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름.
        name: 뗄 파라미터/폴더의 내부 이름. 벡터는 튜플 이름으로.
    """
    definition = require_definition(target)
    group = definition.parmTemplateGroup()
    template = group.find(name)
    if template is None:
        raise ValueError(
            f"{definition.nodeTypeName()} 인터페이스에 {name!r} 가 없습니다. "
            f"지금 있는 최상위 항목: {', '.join(top_level_names(group)) or '(없음)'}"
        )

    removed = describe_entry(template)
    group.remove(template)
    _apply_group(definition, group)
    saved = persist(definition)
    return _interface_result(definition, {"removed": removed, "saved_to": saved})


@tool()
@undoable("Reorder HDA parameters")
def reorder_hda_parms(target: str, order: list[str]) -> dict[str, Any]:
    """HDA 인터페이스의 최상위 항목 순서를 바꾼다.

    폴더는 통째로 움직이고 그 안의 순서는 그대로다. 지금 있는 최상위 이름을
    **빠짐없이** 원하는 순서로 줘야 한다 — 빠뜨린 것이 조용히 사라지는 일을
    막기 위해서다. 이름은 `hda_interface` 의 `top_level` 에 있다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름.
        order: 최상위 항목 이름들을 원하는 순서로. 예: ["size", "controls"]
    """
    definition = require_definition(target)
    group = definition.parmTemplateGroup()
    current = top_level_names(group)

    if sorted(order) != sorted(current):
        missing = [n for n in current if n not in order]
        unknown = [n for n in order if n not in current]
        detail = []
        if missing:
            detail.append(f"빠진 것: {', '.join(missing)}")
        if unknown:
            detail.append(f"없는 이름: {', '.join(unknown)}")
        raise ValueError(
            f"order 가 지금 최상위 항목과 맞지 않습니다. {'; '.join(detail)}. "
            f"지금 순서: {', '.join(current)}"
        )

    templates = {template.name(): template for template in group.parmTemplates()}
    rebuilt = hou.ParmTemplateGroup()
    for entry in order:
        rebuilt.append(templates[entry])
    _apply_group(definition, rebuilt)
    saved = persist(definition)

    return _interface_result(
        definition, {"was": current, "now": order, "saved_to": saved}
    )
