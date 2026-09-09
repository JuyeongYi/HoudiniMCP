"""어트리뷰트 비주얼라이저를 다루는 툴들.

지오메트리를 눈으로 확인할 때 형태만으로는 알 수 없는 것이 있다. 어트리뷰트가
어떤 값으로 퍼져 있는지는 색으로 봐야 안다. 이 모듈은 뷰포트 비주얼라이저를
붙여서, viewport_snapshot 으로 그 색을 볼 수 있게 한다.

`hou.viewportVisualizers` 는 UI 세션에만 있다. hython 에서는 아예 없으므로
GUI 로 띄운 Houdini 에서만 쓸 수 있다.

vis_color 파라미터 값은 실측으로 확인했다.

    class      vertex / point / primitive / detail / auto
    colortype  attribasis / attribramped / constant / random / attribrandom
    rangespec  auto / min-max / center-width

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

GEOMETRY_CLASSES = ("vertex", "point", "primitive", "detail", "auto")
COLOR_MODES = ("attribasis", "attribramped", "constant", "random", "attribrandom")
RANGE_MODES = ("auto", "min-max", "center-width")

COLOR_TYPE = "vis_color"


def _require_ui() -> Any:
    """비주얼라이저 모듈을 얻는다. UI 세션에만 있다."""
    if not hou.isUIAvailable():
        raise RuntimeError(
            "UI 가 없는 세션이라 비주얼라이저를 다룰 수 없습니다. "
            "Houdini 를 GUI 로 실행하세요."
        )
    visualizers = getattr(hou, "viewportVisualizers", None)
    if visualizers is None:
        raise RuntimeError("hou.viewportVisualizers 를 찾지 못했습니다.")
    return visualizers


def _require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    return node


def _describe(vis: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": vis.name(),
        "label": vis.label(),
        "type": vis.type().name(),
        "active": bool(vis.isActive()),
    }
    # vis_color 가 아니면 이 파라미터들이 없다.
    for parm in ("attrib", "class", "colortype", "rangespec"):
        try:
            entry[parm] = vis.evalParmAsString(parm)
        except hou.OperationFailed:
            pass
    return entry


def _find(visualizers: Any, node: hou.Node, name: str) -> Any | None:
    for vis in visualizers.visualizers(
        category=hou.viewportVisualizerCategory.Node, node=node
    ):
        if vis.name() == name:
            return vis
    return None


@tool()
@undoable("Visualize attribute")
def visualize_attribute(
    node: str,
    attribute: str,
    label: str,
    name: str | None = None,
    geometry_class: str = "point",
    color_mode: str = "attribramped",
    range_mode: str = "auto",
    min_value: float | None = None,
    max_value: float | None = None,
) -> dict[str, Any]:
    """어트리뷰트를 뷰포트에 색으로 표시한다.

    붙인 뒤 viewport_snapshot 을 찍으면 값이 어떻게 퍼져 있는지 볼 수 있다.
    같은 이름이 이미 있으면 새로 만들지 않고 고쳐 쓴다.

    Args:
        node: 비주얼라이저를 붙일 노드 경로. 보통 geo 오브젝트를 준다.
        attribute: 표시할 어트리뷰트 이름. 예: Cd, density, P
        label: 뷰포트 툴바에 뜨는 이름. 영어로 쓴다.
        name: 내부 이름. 생략하면 어트리뷰트 이름을 쓴다.
        geometry_class: vertex / point / primitive / detail / auto
        color_mode: attribasis(벡터를 그대로 색으로) / attribramped(램프) /
            constant / random / attribrandom
        range_mode: auto / min-max / center-width
        min_value: range_mode 가 min-max 일 때 하한.
        max_value: range_mode 가 min-max 일 때 상한.
    """
    if geometry_class not in GEOMETRY_CLASSES:
        raise ValueError(
            f"geometry_class 는 {', '.join(GEOMETRY_CLASSES)} 중 하나여야 합니다: "
            f"{geometry_class!r}"
        )
    if color_mode not in COLOR_MODES:
        raise ValueError(
            f"color_mode 는 {', '.join(COLOR_MODES)} 중 하나여야 합니다: {color_mode!r}"
        )
    if range_mode not in RANGE_MODES:
        raise ValueError(
            f"range_mode 는 {', '.join(RANGE_MODES)} 중 하나여야 합니다: {range_mode!r}"
        )

    visualizers = _require_ui()
    target = _require_node(node)
    vis_name = name or attribute

    vis = _find(visualizers, target, vis_name)
    if vis is None:
        vis = visualizers.createVisualizer(
            visualizers.type(COLOR_TYPE),
            category=hou.viewportVisualizerCategory.Node,
            node=target,
        )
        vis.setName(vis_name)

    vis.setLabel(label)
    vis.setParm("attrib", attribute)
    vis.setParm("class", geometry_class)
    vis.setParm("colortype", color_mode)
    vis.setParm("rangespec", range_mode)
    if min_value is not None:
        vis.setParm("minscalar", min_value)
    if max_value is not None:
        vis.setParm("maxscalar", max_value)
    vis.setIsActive(True)

    return {"node": target.path(), **_describe(vis)}


@tool()
def list_visualizers(node: str | None = None) -> dict[str, Any]:
    """붙어 있는 비주얼라이저를 나열한다.

    Args:
        node: 노드 경로. 주면 그 노드에 붙은 것만, 생략하면 씬 전역의 것.
    """
    visualizers = _require_ui()
    if node is None:
        found = visualizers.visualizers(category=hou.viewportVisualizerCategory.Scene)
        scope = "scene"
    else:
        target = _require_node(node)
        found = visualizers.visualizers(
            category=hou.viewportVisualizerCategory.Node, node=target
        )
        scope = target.path()
    return {"scope": scope, "count": len(found), "visualizers": [_describe(v) for v in found]}


@tool()
@undoable("Toggle visualizer")
def set_visualizer_active(node: str, name: str, active: bool = True) -> dict[str, Any]:
    """비주얼라이저를 켜거나 끈다.

    Args:
        node: 비주얼라이저가 붙은 노드 경로.
        name: 비주얼라이저 이름.
        active: 켤지 끌지.
    """
    visualizers = _require_ui()
    target = _require_node(node)
    vis = _find(visualizers, target, name)
    if vis is None:
        raise ValueError(f"{node} 에 그런 비주얼라이저가 없습니다: {name}")
    vis.setIsActive(bool(active))
    return {"node": target.path(), **_describe(vis)}


@tool()
@undoable("Remove visualizer")
def remove_visualizer(node: str, name: str) -> dict[str, str]:
    """비주얼라이저를 지운다.

    Args:
        node: 비주얼라이저가 붙은 노드 경로.
        name: 비주얼라이저 이름.
    """
    visualizers = _require_ui()
    target = _require_node(node)
    vis = _find(visualizers, target, name)
    if vis is None:
        raise ValueError(f"{node} 에 그런 비주얼라이저가 없습니다: {name}")
    vis.destroy()
    return {"node": target.path(), "removed": name}
