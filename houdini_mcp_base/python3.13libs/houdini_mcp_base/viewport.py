"""뷰포트를 보고 다루는 툴들.

`viewport_snapshot` 이 핵심이다. 씬을 만든 뒤 결과를 눈으로 확인할 수
있어야 고칠 근거가 생긴다.

캡처는 Houdini 의 flipbook 을 단일 프레임으로 돌려서 한다. Houdini 자신이
`husd/assetutils.py: saveThumbnailFromViewer()` 에서 쓰는 방식과 같다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import hou
import toolutils

from houdini_mcp import image_result, tool

DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 540

MAX_SIDE = 4096
"""한 변의 최대 픽셀. 너무 큰 이미지는 모델이 받기도 전에 응답을 무겁게 만든다."""


def _scene_viewer() -> hou.SceneViewer:
    """현재 씬 뷰어를 얻는다.

    must_be_current=False 로 둔다. 사용자가 다른 탭을 보고 있어도 캡처할 수
    있어야 하기 때문이다.
    """
    if not hou.isUIAvailable():
        raise RuntimeError(
            "UI 가 없는 세션이라 뷰포트를 다룰 수 없습니다. "
            "Houdini 를 GUI 로 실행하세요."
        )
    viewer = toolutils.sceneViewer(must_be_current=False)
    if viewer is None:
        raise RuntimeError("씬 뷰어를 찾지 못했습니다. 씬 뷰 패널을 하나 열어 주세요.")
    return viewer


@tool()
def viewport_snapshot(
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    frame: float | None = None,
    crop_to_camera: bool = False,
) -> Any:
    """현재 뷰포트를 캡처해서 그림으로 돌려준다.

    만든 결과가 실제로 어떻게 생겼는지 확인할 때 쓴다. 노드를 만들거나 고친 뒤
    이 툴로 보고, 이상하면 다시 고치면 된다.

    Args:
        width: 가로 픽셀.
        height: 세로 픽셀.
        frame: 캡처할 프레임. 생략하면 현재 프레임.
        crop_to_camera: 카메라 마스크 바깥을 잘라낸다. 카메라를 보고 있을 때만
            의미가 있다.
    """
    if width < 1 or height < 1:
        raise ValueError(f"해상도가 잘못됐습니다: {width}x{height}")
    if width > MAX_SIDE or height > MAX_SIDE:
        raise ValueError(
            f"해상도가 너무 큽니다: {width}x{height}. 한 변을 {MAX_SIDE} 이하로 주세요."
        )

    viewer = _scene_viewer()
    viewport = viewer.curViewport()
    at_frame = hou.frame() if frame is None else float(frame)

    with tempfile.TemporaryDirectory(prefix="hmcp_snap_") as tmp:
        output = Path(tmp) / "snapshot.png"

        settings = viewer.flipbookSettings().stash()
        settings.frameRange([at_frame, at_frame])
        settings.outputToMPlay(False)
        settings.useResolution(True)
        settings.resolution((width, height))
        settings.output(str(output))
        settings.cropOutMaskOverlay(crop_to_camera)
        # 뷰포트는 선형이 아니라 보정된 색으로 보이므로 감마를 맞춰 준다.
        settings.overrideGamma(2.2)

        # 격자와 기준면은 결과 판단에 방해가 되므로 잠시 감춘다.
        reference = viewer.referencePlane()
        construction = viewer.constructionPlane()
        was_reference = reference.isVisible()
        was_construction = construction.isVisible()
        reference.setIsVisible(False)
        construction.setIsVisible(False)
        try:
            viewer.flipbook(viewport=viewport, settings=settings)
        finally:
            reference.setIsVisible(was_reference)
            construction.setIsVisible(was_construction)

        written = _find_output(output)
        if written is None:
            raise RuntimeError(
                "캡처 파일이 만들어지지 않았습니다. 뷰포트가 그릴 수 있는 상태인지 "
                "확인하세요."
            )
        return image_result(written.read_bytes(), "png")


def _find_output(expected: Path) -> Path | None:
    """flipbook 이 실제로 쓴 파일을 찾는다.

    프레임 패턴을 주지 않아도 Houdini 가 파일명에 프레임 번호를 붙일 수 있어서,
    기대한 이름이 없으면 같은 디렉토리에서 png 를 찾는다.
    """
    if expected.exists():
        return expected
    candidates = sorted(expected.parent.glob("*.png"))
    return candidates[0] if candidates else None


@tool()
def frame_all() -> dict[str, Any]:
    """뷰포트를 씬 전체가 보이도록 맞춘다.

    캡처 전에 부르면 만든 것이 화면 밖에 있는 일을 막을 수 있다.
    """
    viewport = _scene_viewer().curViewport()
    viewport.frameAll()
    return {"framed": "all"}


@tool()
def frame_node(path: str) -> dict[str, Any]:
    """뷰포트를 특정 노드의 지오메트리에 맞춘다.

    Args:
        path: 노드 경로. 예: /obj/castle/castle_wall
    """
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")

    geometry = getattr(node, "geometry", None)
    if geometry is None:
        raise ValueError(f"{path} 에는 지오메트리가 없습니다. SOP 경로를 주세요.")
    geo = geometry()
    if geo is None:
        raise ValueError(f"{path} 의 지오메트리를 읽지 못했습니다.")

    viewport = _scene_viewer().curViewport()
    viewport.frameBoundingBox(geo.boundingBox())
    return {"framed": node.path()}


@tool()
def viewport_info() -> dict[str, Any]:
    """현재 뷰포트의 이름, 크기, 카메라 상태."""
    viewer = _scene_viewer()
    viewport = viewer.curViewport()
    size = viewport.size()
    camera = viewport.camera()
    return {
        "name": viewport.name(),
        "size": [size[2], size[3]],
        "type": str(viewport.type()),
        "camera": camera.path() if camera is not None else None,
        "camera_locked": viewport.isCameraLockedToView(),
        "frame": hou.frame(),
        "viewing_scene_graph": viewer.isViewingSceneGraph(),
        # Hydra 렌더러는 LOP 스테이지를 볼 때만 있다. /obj 를 보는 뷰어에서
        # currentHydraRenderer() 를 부르면 "not a scene graph view" 로 예외가
        # 난다(GUI 실측 - hython 에는 hou.ui 가 없어 테스트로 잡지 못했다).
        "renderer": viewer.currentHydraRenderer() if viewer.isViewingSceneGraph() else None,
    }


# ---- 뷰 방향·표시 방식 ------------------------------------------------
#
# 캡처 전에 무엇을 어떻게 볼지 정하는 것들이다. 같은 씬도 위에서 보느냐 앞에서
# 보느냐에 따라 알 수 있는 것이 다르다 - 배치가 맞는지는 위에서, 높이가 맞는지는
# 앞에서 봐야 안다.

DIRECTIONS = {
    "top": hou.geometryViewportType.Top,
    "bottom": hou.geometryViewportType.Bottom,
    "front": hou.geometryViewportType.Front,
    "back": hou.geometryViewportType.Back,
    "left": hou.geometryViewportType.Left,
    "right": hou.geometryViewportType.Right,
    "persp": hou.geometryViewportType.Perspective,
    "uv": hou.geometryViewportType.UV,
}

SHADING = {
    "wire": hou.glShadingType.Wire,
    "wire_ghost": hou.glShadingType.WireGhost,
    "hidden_line": hou.glShadingType.HiddenLineInvisible,
    "hidden_line_ghost": hou.glShadingType.HiddenLineGhost,
    "flat": hou.glShadingType.Flat,
    "flat_wire": hou.glShadingType.FlatWire,
    "smooth": hou.glShadingType.Smooth,
    "smooth_wire": hou.glShadingType.SmoothWire,
    "bbox": hou.glShadingType.WireBoundingBox,
}


@tool()
def set_viewport_camera(path: str | None = None, lock: bool = False) -> dict[str, Any]:
    """뷰포트를 카메라로 본다. 렌더가 실제로 무엇을 담는지 확인할 때 쓴다.

    path 를 생략하면 카메라에서 빠져나와 자유 시점으로 돌아간다.

    Args:
        path: 카메라 노드 경로. 예: /obj/shot_cam
        lock: True 면 뷰를 카메라에 잠가 실수로 시점이 움직이지 않게 한다.
    """
    viewport = _scene_viewer().curViewport()
    if path is None:
        viewport.useDefaultCamera()
        return {"camera": None, "note": "자유 시점으로 돌아갔습니다."}

    camera = hou.node(path)
    if camera is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    if camera.type().category().name() != "Object":
        raise ValueError(
            f"{path} 는 카메라가 아닙니다 ({camera.type().name()}). "
            f"/obj 아래의 cam 노드 경로를 주세요."
        )

    viewport.setCamera(camera)
    viewport.lockCameraToView(lock)
    return {"camera": camera.path(), "comment": camera.comment(), "locked": lock}


@tool()
def set_viewport_direction(direction: str = "persp") -> dict[str, Any]:
    """뷰포트를 정해진 방향에서 보게 한다.

    배치가 맞는지는 top 에서, 높이가 맞는지는 front 에서 봐야 안다. 방향을
    바꾸고 `frame_all` 로 맞춘 뒤 `viewport_snapshot` 을 찍는 것이 보통이다.

    Args:
        direction: top / bottom / front / back / left / right / persp / uv
    """
    if direction not in DIRECTIONS:
        raise ValueError(
            f"direction 은 {', '.join(DIRECTIONS)} 중 하나여야 합니다: {direction!r}"
        )
    viewport = _scene_viewer().curViewport()
    viewport.changeType(DIRECTIONS[direction])
    return {"direction": direction, "type": str(viewport.type())}


@tool()
def set_viewport_display(shading: str = "smooth_wire", ghost_others: bool = False) -> dict[str, Any]:
    """뷰포트가 지오메트리를 어떻게 그릴지 정한다.

    형태만 볼 때는 `smooth`, 토폴로지를 볼 때는 `wire` 나 `smooth_wire`,
    아주 무거운 씬은 `bbox` 가 빠르다.

    ghost_others 를 켜면 지금 작업 중인 오브젝트 말고는 반투명으로 그린다.
    한 노드가 전체 안에서 어디쯤인지 볼 때 쓴다.

    Args:
        shading: wire / wire_ghost / hidden_line / hidden_line_ghost /
            flat / flat_wire / smooth / smooth_wire / bbox
        ghost_others: 작업 중이 아닌 오브젝트를 반투명으로.
    """
    if shading not in SHADING:
        raise ValueError(
            f"shading 은 {', '.join(SHADING)} 중 하나여야 합니다: {shading!r}"
        )
    settings = _scene_viewer().curViewport().settings()

    changed = ["current"]
    settings.displaySet(hou.displaySetType.SceneObject).setShadedMode(SHADING[shading])
    settings.displaySet(hou.displaySetType.DisplayModel).setShadedMode(SHADING[shading])
    if ghost_others:
        settings.displaySet(hou.displaySetType.GhostObject).setShadedMode(
            hou.glShadingType.WireGhost
        )
        changed.append("ghost")
    return {"shading": shading, "applied_to": changed, "ghost_others": ghost_others}


@tool()
def set_viewport_renderer(name: str | None = None) -> dict[str, Any]:
    """뷰포트 렌더러를 바꾼다. 이름을 생략하면 고를 수 있는 것을 알려 준다.

    기본은 Houdini GL 이다. Karma XPU 로 바꾸면 실제 렌더에 가까운 그림을
    볼 수 있지만 훨씬 느리다 - 캡처 한 장을 위해 몇 초에서 몇 분이 걸린다.
    최종 확인이 필요할 때만 바꾸고, 끝나면 되돌린다.

    LOP 스테이지(/stage 등)를 보고 있을 때만 쓸 수 있다. /obj 를 보는 뷰어에는
    Hydra 렌더러가 없다.

    Args:
        name: 렌더러 이름. 생략하면 지금 것과 고를 수 있는 것만 돌려준다.
    """
    viewer = _scene_viewer()
    if not viewer.isViewingSceneGraph():
        raise ValueError(
            f"뷰어가 {viewer.pwd().path()} 를 보고 있어 Hydra 렌더러가 없습니다. "
            f"렌더러는 LOP 스테이지를 볼 때만 바뀝니다 - set_current_network('/stage') 로 "
            f"LOP 네트워크를 띄운 뒤 다시 부르세요."
        )
    available = list(viewer.hydraRenderers())
    if name is None:
        return {"current": viewer.currentHydraRenderer(), "available": available}

    if name not in available:
        raise ValueError(
            f"그런 렌더러가 없습니다: {name!r}. 쓸 수 있는 것: {', '.join(available)}"
        )
    viewer.setHydraRenderer(name)
    return {"current": viewer.currentHydraRenderer(), "available": available}


# ---- 패널 ------------------------------------------------------------


@tool()
def list_panes() -> dict[str, Any]:
    """지금 열려 있는 패널 탭들. 사용자가 무엇을 보고 있는지 알 수 있다.

    네트워크 에디터가 어느 네트워크를 열고 있는지도 함께 주므로,
    "이거 고쳐 줘" 처럼 대상이 생략된 요청의 맥락을 잡는 데 쓴다.
    """
    if not hou.isUIAvailable():
        raise RuntimeError(
            "UI 가 없는 세션이라 패널을 볼 수 없습니다. Houdini 를 GUI 로 실행하세요."
        )
    tabs = []
    for tab in hou.ui.paneTabs():
        entry: dict[str, Any] = {
            "name": tab.name(),
            "type": str(tab.type()).rsplit(".", 1)[-1],
            "current": bool(tab.isCurrentTab()),
        }
        pwd = getattr(tab, "pwd", None)
        if pwd is not None:
            try:
                entry["network"] = pwd().path()
            except hou.OperationFailed:
                pass
        tabs.append(entry)
    return {"count": len(tabs), "panes": tabs}


@tool()
def set_current_network(path: str) -> dict[str, Any]:
    """네트워크 에디터가 보는 네트워크를 바꾼다.

    작업한 곳을 사용자에게 열어 보여줄 때 쓴다. `set_selection` 과 함께 쓰면
    "여기 이것들을 만들었습니다" 가 화면에 그대로 뜬다.

    Args:
        path: 열 네트워크 경로. 예: /obj/castle
    """
    if not hou.isUIAvailable():
        raise RuntimeError(
            "UI 가 없는 세션이라 네트워크 에디터를 다룰 수 없습니다. "
            "Houdini 를 GUI 로 실행하세요."
        )
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")

    editors = [
        tab for tab in hou.ui.paneTabs() if tab.type() == hou.paneTabType.NetworkEditor
    ]
    if not editors:
        raise RuntimeError(
            "열려 있는 네트워크 에디터가 없습니다. 네트워크 뷰 패널을 하나 열어 주세요."
        )

    changed = []
    for editor in editors:
        editor.setPwd(node)
        changed.append(editor.name())
    return {"network": node.path(), "comment": node.comment(), "editors": changed}
