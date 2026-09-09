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
            "UI 가 없는 세션이라 뷰포트를 캡처할 수 없습니다. "
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
    }
