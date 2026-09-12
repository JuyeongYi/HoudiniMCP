"""컬러 매니지먼트 툴. 목록을 하드코딩하지 않고 OCIO 설정에서 읽는다.

Houdini 22.0.368 은 PyOpenColorIO 2.5.0 을 번들하고 있다(실측 확인). 기본
설정은 ACES CG Config 다. 컬러스페이스 이름을 문자열로 넘겨받아 그대로 거는
대신, 설정에 실제로 있는 이름인지 확인한다.

주의할 점이 하나 있다. 셰이더의 filecolorspace 파라미터 메뉴는 설정의
표시 이름("sRGB Encoded Rec.709 (sRGB)")이 아니라 **별칭**("srgb_texture")을
쓴다. 그래서 둘 다 돌려주고, 둘 다 받는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from .common import require_vop

COLORSPACE_PARMS = ("filecolorspace", "colorspace", "ocio_colorspace")
"""텍스처 노드가 컬러스페이스에 쓰는 파라미터 이름들."""


def _ocio():
    try:
        import PyOpenColorIO as ocio
    except Exception as exc:  # noqa: BLE001 - 번들이 깨진 경우
        raise RuntimeError(
            f"PyOpenColorIO 를 읽지 못했습니다. Houdini 설치가 온전한지 "
            f"확인하세요. ({exc})"
        ) from exc
    return ocio


def _colorspace_entries(config) -> list[dict[str, Any]]:
    entries = []
    for space in config.getColorSpaces():
        entries.append(
            {
                "name": space.getName(),
                "aliases": list(space.getAliases()),
                "family": space.getFamily(),
                "is_data": space.isData(),
            }
        )
    return entries


@tool()
def list_color_spaces(pattern: str = "") -> dict[str, Any]:
    """쓸 수 있는 컬러스페이스를 OCIO 설정에서 읽어 돌려준다.

    하드코딩된 목록이 아니다. 지금 Houdini 가 쓰고 있는 OCIO 설정을 열어
    컬러스페이스, 별칭, 롤(role), 디스플레이를 읽는다.

    셰이더 파라미터에 넣을 값은 texture_parm_menu 쪽을 본다. 그쪽이 파라미터
    메뉴가 실제로 받는 값이다.

    Args:
        pattern: 이름이나 별칭에 이 문자열이 든 것만. 비우면 전부.
    """
    ocio = _ocio()
    config = ocio.GetCurrentConfig()

    entries = _colorspace_entries(config)
    if pattern:
        lowered = pattern.lower()
        entries = [
            entry
            for entry in entries
            if lowered in entry["name"].lower()
            or any(lowered in alias.lower() for alias in entry["aliases"])
        ]

    roles = {role: space for role, space in config.getRoles()}
    displays = list(config.getDisplays())

    return {
        "config_file": hou.text.expandString("$OCIO"),
        "config_name": config.getName(),
        "count": len(entries),
        "color_spaces": entries,
        "roles": roles,
        "displays": displays,
        "note": (
            "셰이더의 filecolorspace 파라미터는 별칭(aliases)을 씁니다. "
            "texture_parm_colorspaces 로 그 메뉴를 그대로 볼 수 있습니다."
        ),
    }


@tool()
def texture_parm_colorspaces(path: str = "", parm: str = "") -> dict[str, Any]:
    """텍스처 노드의 컬러스페이스 파라미터가 실제로 받는 값 목록.

    OCIO 설정의 표시 이름이 아니라 파라미터 메뉴가 받는 값이다. 여기 없는
    값을 넣으면 조용히 무시되므로, 값을 걸기 전에 이걸 본다.

    Args:
        path: 텍스처 노드 경로. 비우면 임시 mtlximage 로 기본 메뉴를 본다.
        parm: 파라미터 이름. 비우면 filecolorspace 등을 자동으로 찾는다.
    """
    if path:
        node = require_vop(path)
        target = node.parm(parm) if parm else None
        if target is None:
            for candidate in COLORSPACE_PARMS:
                target = node.parm(candidate)
                if target is not None:
                    break
        if target is None:
            raise ValueError(
                f"{path} 에 컬러스페이스 파라미터가 없습니다. "
                f"찾아본 이름: {', '.join(COLORSPACE_PARMS)}"
            )
        return {
            "node": node.path(),
            "parm": target.name(),
            "current": target.eval(),
            "values": list(target.menuItems()),
            "labels": list(target.menuLabels()),
        }

    # 노드를 주지 않으면 mtlximage 의 기본 메뉴를 보여 준다. 임시로 만들고 지운다.
    container = hou.node("/mat")
    if container is None:
        raise ValueError(
            "/mat 네트워크가 없어 기본 메뉴를 읽을 수 없습니다. "
            "텍스처 노드 경로를 path 로 주세요."
        )
    probe = container.createNode("mtlximage")
    try:
        target = probe.parm("filecolorspace")
        return {
            "node": None,
            "parm": "filecolorspace",
            "values": list(target.menuItems()),
            "labels": list(target.menuLabels()),
            "note": "mtlximage 의 기본 메뉴입니다.",
        }
    finally:
        probe.destroy()


@tool()
@undoable("Set color space")
def set_color_space(path: str, colorspace: str, parm: str = "") -> dict[str, Any]:
    """텍스처 노드의 컬러스페이스를 건다. 메뉴에 없는 값이면 거절한다.

    문자열을 그대로 넣지 않는다. 파라미터 메뉴에 있는 값인지 확인하고, 없으면
    비슷한 것을 알려 준다. 조용히 무시돼 렌더가 틀어지는 것을 막기 위해서다.

    Args:
        path: 텍스처 노드 경로. 예: /mat/wall_stone/base_color_tex
        colorspace: 걸 값. 예: srgb_texture, lin_rec709, Raw
        parm: 파라미터 이름. 비우면 filecolorspace 등을 자동으로 찾는다.
    """
    node = require_vop(path)
    target = node.parm(parm) if parm else None
    if target is None:
        for candidate in COLORSPACE_PARMS:
            target = node.parm(candidate)
            if target is not None:
                break
    if target is None:
        raise ValueError(
            f"{path} 에 컬러스페이스 파라미터가 없습니다. "
            f"찾아본 이름: {', '.join(COLORSPACE_PARMS)}. "
            f"list_parms 로 파라미터 이름을 확인하세요."
        )

    values = list(target.menuItems())
    if values and colorspace not in values:
        lowered = colorspace.lower()
        close = [value for value in values if lowered in value.lower()]
        hint = f" 비슷한 것: {', '.join(close[:8])}" if close else ""
        raise ValueError(
            f"{colorspace!r} 은 {node.path()} 의 {target.name()} 메뉴에 없습니다.{hint} "
            f"texture_parm_colorspaces 로 쓸 수 있는 값을 보세요."
        )

    previous = target.eval()
    target.set(colorspace)
    return {
        "path": node.path(),
        "parm": target.name(),
        "previous": previous,
        "colorspace": target.eval(),
        "comment": node.comment(),
    }
