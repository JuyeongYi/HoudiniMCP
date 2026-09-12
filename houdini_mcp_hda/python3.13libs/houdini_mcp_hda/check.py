"""만든 HDA 가 실제로 도는지 확인한다.

기존 구현 다섯 중 이걸 하는 것이 하나도 없다. 굽고 끝내면 정의가 깨져 있어도
누군가 그 노드를 놓아 볼 때까지 모른다.

`validate_hda` 가 하는 일:

1. 임시 컨테이너를 만든다 (SOP 이면 `/obj` 밑의 geo, LOP 이면 lopnet ...)
2. 그 안에 에셋 인스턴스를 하나 놓는다
3. 파라미터를 걸고 **쿡한다**
4. 에러·경고·지오메트리 통계를 읽고, 인터페이스가 인스턴스에 다 나타났는지 본다
5. **임시 노드를 지운다** — 성공했든 실패했든 씬을 더럽히지 않는다

ROP(Driver) 카테고리는 쿡이 곧 렌더라 쿡하지 않는다. 인스턴스화와 파라미터만
확인한다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/Node.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable
from houdini_mcp_base.parmtemplate import component_names

from ._common import (
    TEMP_PREFIX,
    definition_summary,
    interface_parm_count,
    make_container,
    require_definition,
)

NO_COOK = frozenset({"Driver"})
"""쿡이 곧 렌더/실행인 카테고리. 검증하느라 렌더를 돌리지 않는다."""


def _expected_parm_names(definition: hou.HDADefinition) -> list[str]:
    """정의가 내놓기로 한 실제 파라미터 이름들. 폴더는 빼고 성분까지 편다."""
    names: list[str] = []

    def walk(templates) -> None:
        for template in templates:
            children = getattr(template, "parmTemplates", None)
            if children is not None:
                walk(children())
                continue
            names.extend(component_names(template))

    walk(definition.parmTemplateGroup().parmTemplates())
    return names


def _geometry_stats(node: hou.Node) -> dict[str, Any] | None:
    """SOP 이면 만들어진 지오메트리 통계. 빈 결과도 정보다."""
    getter = getattr(node, "geometry", None)
    if getter is None:
        return None
    geo = getter()
    if geo is None:
        return None
    bbox = geo.boundingBox()
    stats: dict[str, Any] = {
        "points": geo.pointCount(),
        "prims": geo.primCount(),
        "vertices": geo.vertexCount(),
    }
    if bbox.isValid():
        size = bbox.sizevec()
        stats["bbox_size"] = [size[0], size[1], size[2]]
    return stats


@tool()
@undoable("Validate digital asset")
def validate_hda(
    target: str, parms: dict[str, Any] | None = None, frame: float | None = None
) -> dict[str, Any]:
    """HDA 를 실제로 인스턴스화하고 쿡해서 동작하는지 확인한다. 임시 노드는 지운다.

    구운 직후, 인터페이스를 고친 뒤, `collapse_hda` 로 왕복한 뒤에 부른다.
    "만들어졌다"와 "동작한다"는 다르다.

    임시 컨테이너를 만들어 그 안에서만 돌리므로 사용자의 씬은 그대로다. 검증이
    실패해도 임시 노드는 지워진다. 그래서 이 툴에는 comment 를 받지 않는다 —
    남는 노드가 없다.

    결과의 `cooked` 가 True 이고 `errors` 가 비어 있으면 쓸 수 있는 에셋이다.
    `missing_parms` 가 비어 있지 않으면 정의의 인터페이스가 인스턴스에 온전히
    나타나지 않은 것이다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름
            (Sop/ns::brick_maker::1.0).
        parms: 쿡하기 전에 걸어 볼 파라미터. 예: {"size": 2.0}
        frame: 검증할 프레임. 생략하면 현재 프레임.
    """
    definition = require_definition(target)
    node_type = definition.nodeType()
    if node_type is None:
        raise ValueError(
            f"{definition.nodeTypeName()} 정의가 설치돼 있지 않아 인스턴스를 만들 수 "
            f"없습니다. install_hda 로 {definition.libraryFilePath()} 를 먼저 "
            f"설치하세요."
        )

    category = definition.nodeTypeCategory().name()
    parent, temporary = make_container(category)
    instance: hou.Node | None = None
    restore_frame = hou.frame() if frame is not None else None

    try:
        try:
            instance = parent.createNode(
                node_type.name(), node_name=f"{TEMP_PREFIX}_probe"
            )
        except hou.OperationFailed as exc:
            raise ValueError(
                f"{parent.path()} 안에 {node_type.name()!r} 인스턴스를 만들지 "
                f"못했습니다: {exc} 정의가 그 카테고리({category})에 맞는지 "
                f"hda_info 로 확인하세요."
            ) from exc

        expected = _expected_parm_names(definition)
        actual = {parm.name() for parm in instance.parms()}
        missing = [name for name in expected if name not in actual]

        applied: dict[str, Any] = {}
        unknown: list[str] = []
        for name, value in (parms or {}).items():
            parm = instance.parm(name)
            if parm is not None:
                parm.set(value)
                applied[name] = parm.eval()
                continue
            parm_tuple = instance.parmTuple(name)
            if parm_tuple is None:
                unknown.append(name)
                continue
            parm_tuple.set(tuple(value) if isinstance(value, (list, tuple)) else value)
            applied[name] = list(parm_tuple.eval())

        if unknown:
            raise ValueError(
                f"{node_type.name()} 에 파라미터가 없습니다: {', '.join(unknown)}. "
                f"hda_interface 로 이름을 확인하세요. "
                f"있는 것: {', '.join(sorted(actual)) or '(없음)'}"
            )

        if frame is not None:
            hou.setFrame(frame)

        cooked = False
        cook_error: str | None = None
        if category not in NO_COOK:
            try:
                instance.cook(force=True)
                cooked = True
            except hou.Error as exc:
                cook_error = str(exc).strip()

        result: dict[str, Any] = {
            "definition": definition_summary(definition),
            "instantiated": True,
            "probe_path": instance.path(),
            "category": category,
            "cooked": cooked,
            "cook_skipped": category in NO_COOK,
            "errors": list(instance.errors()),
            "warnings": list(instance.warnings()),
            "interface_parm_count": interface_parm_count(
                definition.parmTemplateGroup()
            ),
            "expected_parms": expected,
            "missing_parms": missing,
            "applied_parms": applied,
            "frame": hou.frame(),
        }
        if cook_error:
            result["cook_error"] = cook_error
        if category in NO_COOK:
            result["cook_skipped_why"] = (
                f"{category} 노드는 쿡이 곧 실행이라 검증에서 돌리지 않습니다."
            )

        stats = _geometry_stats(instance) if cooked else None
        if stats is not None:
            result["geometry"] = stats

        result["ok"] = cooked and not result["errors"] and not missing
        return result
    finally:
        # 성공하든 실패하든 씬을 원래대로 둔다.
        if restore_frame is not None:
            hou.setFrame(restore_frame)
        if temporary is not None:
            temporary.destroy()
        elif instance is not None:
            instance.destroy()
