"""텍스처를 붙이고, 붙이기 전에 **파일을 실제로 열어 확인하는** 툴.

기존 구현의 assign_texture 는 경로 문자열을 파라미터에 넣고 끝난다. 파일이
있는지, 노멀맵에 채널이 3개 있는지, 8비트 sRGB 를 러프니스에 물리고 있는지
모른다. 이런 것은 렌더를 돌려야 드러나고, 그때는 원인을 찾기 어렵다.

여기서는 Houdini 에 번들된 OpenImageIO 2.5.18 으로 파일을 열어 해상도, 채널,
비트뎁스, 컬러스페이스 메타데이터를 읽고 용도와 맞는지 판정한다. UDIM 은
경로의 토큰을 실제 타일 글롭으로 바꿔 몇 장이 있는지 센다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool, undoable

from houdini_mcp_base import paths

from .common import (
    require_comment,
    require_material,
    set_comment,
    terminal_shader,
)


USAGE_COLOR = "color"
USAGE_SCALAR = "scalar"
USAGE_NORMAL = "normal"
USAGES = (USAGE_COLOR, USAGE_SCALAR, USAGE_NORMAL)

SIGNATURE_FOR_TYPE = {
    "float": "default",
    "color": "color3",
    "vector": "vector3",
    "vector2": "vector2",
    "vector4": "vector4",
}
"""mtlximage 의 출력 타입을 대상 입력 타입에 맞춘다 (실측으로 확인한 대응)."""

SRGB_HINTS = ("srgb", "sRGB", "Gamma", "gamma", "g22", "g18", "g24")


def _oiio():
    try:
        import OpenImageIO as oiio
    except Exception as exc:  # noqa: BLE001 - 번들이 깨진 경우
        raise RuntimeError(
            f"OpenImageIO 를 읽지 못했습니다. Houdini 설치가 온전한지 확인하세요. ({exc})"
        ) from exc
    return oiio


def _udim_tiles(raw: str) -> tuple[str | None, list[str]]:
    """UDIM 토큰과 실제로 있는 타일들. 토큰이 없으면 (None, []).

    토큰 인식과 글롭은 base 의 paths 가 한다 - 네 자리 숫자만 타일로 센다.
    """
    token = paths.UDIM_TOKENS.search(paths.to_parm(raw))
    if token is None:
        return None, []
    tiles, _ = paths.resolve_files(raw)
    return token.group(), [tile.as_posix() for tile in tiles]


def _read_spec(file_path: Path) -> dict[str, Any]:
    """OIIO 로 파일을 열어 스펙을 읽는다."""
    oiio = _oiio()
    source = oiio.ImageInput.open(str(file_path))
    if source is None:
        raise ValueError(
            f"이미지를 열지 못했습니다: {file_path}. "
            f"({oiio.geterror() or '지원하지 않는 포맷일 수 있습니다'}) "
            f"exr, png, jpg, tif, rat 등을 씁니다."
        )
    try:
        spec = source.spec()
        attribs = {
            attrib.name: attrib.value for attrib in spec.extra_attribs
        }
        mip_levels = 0
        while source.seek_subimage(0, mip_levels):
            mip_levels += 1
        return {
            "width": spec.width,
            "height": spec.height,
            "channels": spec.nchannels,
            "channel_names": list(spec.channelnames),
            "format": str(spec.format),
            "mip_levels": mip_levels,
            "colorspace_metadata": attribs.get("oiio:ColorSpace", ""),
            "compression": attribs.get("compression", ""),
            "metadata": {
                name: value
                for name, value in attribs.items()
                if name not in ("oiio:ColorSpace", "compression")
            },
        }
    finally:
        source.close()


def _is_low_bitdepth(format_name: str) -> bool:
    return format_name in ("uint8", "int8", "uchar", "char")


def _usage_warnings(info: dict[str, Any], usage: str, colorspace: str) -> list[str]:
    """용도와 파일이 맞는지 본다. 렌더를 돌리기 전에 잡아 준다."""
    warnings: list[str] = []
    channels = info.get("channels", 0)
    fmt = info.get("format", "")
    declared = colorspace or info.get("colorspace_metadata", "")
    srgb_like = any(hint in declared for hint in SRGB_HINTS)

    if usage == USAGE_NORMAL:
        if channels < 3:
            warnings.append(
                f"노멀맵인데 채널이 {channels} 개입니다. XYZ 를 담으려면 3채널이어야 "
                f"합니다. 채널이 하나라면 노멀맵이 아니라 범프맵일 수 있습니다 — "
                f"그 경우 mtlxbump 를 쓰세요."
            )
        if _is_low_bitdepth(fmt):
            warnings.append(
                f"노멀맵이 {fmt} 입니다. 8비트 노멀맵은 밴딩이 생깁니다. "
                f"16비트 이상(exr, 16bit png)을 쓰세요."
            )
        if srgb_like:
            warnings.append(
                f"노멀맵의 컬러스페이스가 {declared!r} 입니다. 노멀은 색이 아니므로 "
                f"Raw 또는 linear 여야 합니다. set_color_space 로 고치세요."
            )
    elif usage == USAGE_SCALAR:
        if srgb_like:
            warnings.append(
                f"러프니스·메탈니스 같은 스칼라 맵의 컬러스페이스가 {declared!r} 입니다. "
                f"감마가 먹어 값이 틀어집니다. Raw 로 바꾸세요."
            )
        if channels > 1:
            warnings.append(
                f"스칼라 입력인데 채널이 {channels} 개입니다. 첫 채널만 쓰이거나 "
                f"평균이 쓰입니다. 의도한 채널이 맞는지 확인하세요."
            )
    elif usage == USAGE_COLOR:
        if channels < 3:
            warnings.append(
                f"컬러 입력인데 채널이 {channels} 개입니다."
            )
        if _is_low_bitdepth(fmt) and not srgb_like and declared:
            warnings.append(
                f"8비트 컬러 텍스처의 컬러스페이스가 {declared!r} 입니다. "
                f"8비트 컬러는 보통 sRGB 로 인코딩돼 있습니다. "
                f"list_color_spaces 로 확인하고 set_color_space 로 고치세요."
            )
    return warnings


def _inspect(raw: str, usage: str = "", colorspace: str = "") -> dict[str, Any]:
    """텍스처 하나를 조사한다. UDIM 이면 타일을 세고 첫 타일을 연다."""
    resolved = paths.to_path(raw)
    info: dict[str, Any] = {
        "raw": raw,
        "resolved": resolved.as_posix(),
    }

    token, tiles = _udim_tiles(raw)
    if token is not None:
        info["udim"] = True
        info["udim_token"] = token
        info["tile_count"] = len(tiles)
        info["tiles"] = tiles[:20]
        if not tiles:
            info["exists"] = False
            info["error"] = (
                f"UDIM 타일이 한 장도 없습니다: {resolved.parent}. "
                f"경로와 타일 번호(1001 부터)를 확인하세요."
            )
            return info
        resolved = Path(tiles[0])
        info["inspected_tile"] = resolved.as_posix()

    if not resolved.is_file():
        info["exists"] = False
        info["error"] = (
            f"파일이 없습니다: {resolved}. 경로가 맞는지, $HIP 이 기대한 곳을 "
            f"가리키는지 확인하세요. list_dependencies(kinds=['Image']) 로 씬이 참조하는 이미지를 "
            f"전부 볼 수 있습니다."
        )
        return info

    info["exists"] = True
    info["size_bytes"] = resolved.stat().st_size
    info.update(_read_spec(resolved))
    if usage:
        info["usage"] = usage
        warnings = _usage_warnings(info, usage, colorspace)
        if warnings:
            info["warnings"] = warnings
    return info


@tool()
def texture_info(file: str, usage: str = "", stats: bool = False) -> dict[str, Any]:
    """텍스처 파일을 실제로 열어 해상도·채널·비트뎁스·컬러스페이스를 읽는다.

    파일이 있는지만 보는 것이 아니라 OpenImageIO 로 헤더를 읽는다. UDIM 토큰이
    든 경로는 실제 타일을 글롭으로 세어 몇 장이 있는지 알려 준다.

    usage 를 주면 그 용도에 맞는 파일인지까지 판정한다. 노멀맵에 채널이 부족한
    경우, 러프니스에 sRGB 가 걸린 경우처럼 렌더를 돌려야 드러나는 문제를
    미리 잡는다.

    Args:
        file: 텍스처 경로. $HIP 같은 Houdini 변수를 써도 된다.
            UDIM 은 <UDIM> 토큰으로. 예: $HIP/tex/wall_basecolor.<UDIM>.exr
        usage: color / scalar / normal 중 하나. 비우면 판정하지 않는다.
        stats: True 면 픽셀 통계(최소·최대·평균)까지 계산한다. 큰 파일은 느리다.
    """
    if usage and usage not in USAGES:
        raise ValueError(
            f"usage 가 {usage!r} 입니다. 다음 중 하나여야 합니다: {', '.join(USAGES)}"
        )
    info = _inspect(file, usage)
    if stats and info.get("exists"):
        oiio = _oiio()
        target = info.get("inspected_tile", info["resolved"])
        buffer = oiio.ImageBuf(target)
        pixel_stats = oiio.ImageBufAlgo.computePixelStats(buffer)
        if pixel_stats is not None:
            info["stats"] = {
                "min": list(pixel_stats.min),
                "max": list(pixel_stats.max),
                "avg": list(pixel_stats.avg),
                "stddev": list(pixel_stats.stddev),
                "nan_count": pixel_stats.nancount,
                "inf_count": pixel_stats.infcount,
            }
    return info


def _file_parm(node: hou.VopNode, name: str) -> hou.Parm | None:
    """그 이름이 이미지 파일 파라미터인지."""
    parm = node.parm(name)
    if parm is None:
        return None
    template = parm.parmTemplate()
    if not isinstance(template, hou.StringParmTemplate):
        return None
    if template.stringType() != hou.stringParmType.FileReference:
        return None
    return parm


@tool()
@undoable("Assign texture")
def assign_texture(
    material: str,
    to_input: str,
    file: str,
    comment: str,
    usage: str = "",
    colorspace: str = "",
    name: str = "",
) -> dict[str, Any]:
    """텍스처를 셰이더 입력에 붙인다. 붙이기 전에 **파일을 열어 확인한다.**

    파일이 없으면 노드를 만들지 않고 실패한다. 있으면 해상도·채널·비트뎁스를
    읽어 함께 돌려주고, usage 와 맞지 않으면 경고한다.

    to_input 이 셰이더의 파일 파라미터 이름이면(principledshader 의
    basecolor_texture 처럼) 그 파라미터에 바로 건다. MaterialX 머티리얼이면
    mtlximage 노드를 만들어 그 입력에 잇고, 출력 타입을 대상 입력 타입에 맞춰
    signature 를 정한다.

    Args:
        material: 머티리얼 노드 경로. 예: /mat/wall_stone
        to_input: 붙일 입력 이름. 예: base_color, specular_roughness, normal
        file: 텍스처 경로. UDIM 은 <UDIM> 토큰으로.
        comment: 만들어지는 텍스처 노드의 코멘트. 필수. 영어로.
            예: "Sandstone base color, 4K sRGB"
        usage: color / scalar / normal. 주면 파일이 용도에 맞는지 판정한다.
        colorspace: mtlximage 의 filecolorspace 에 걸 값. 비우면 건드리지 않는다.
            쓸 수 있는 값은 list_color_spaces 로 본다.
        name: 만들 텍스처 노드 이름. 비우면 입력 이름에서 만든다.
    """
    comment = require_comment(comment, "이 텍스처 노드")
    if usage and usage not in USAGES:
        raise ValueError(
            f"usage 가 {usage!r} 입니다. 다음 중 하나여야 합니다: {', '.join(USAGES)}"
        )

    inspection = _inspect(file, usage, colorspace)
    if not inspection.get("exists"):
        raise ValueError(inspection.get("error", f"텍스처를 읽지 못했습니다: {file}"))

    material_node = require_material(material)
    shader = terminal_shader(material_node)
    if shader is None:
        raise ValueError(
            f"{material} 의 surface 출력에 셰이더가 물려 있지 않습니다. "
            f"material_info 로 상태를 먼저 보세요."
        )

    # 1) 셰이더 자신이 파일 파라미터를 가진 경우 (principledshader 등).
    direct = _file_parm(shader, to_input)
    if direct is not None:
        direct.set(paths.to_parm(file))
        return {
            "material": material_node.path(),
            "shader": shader.path(),
            "parm": to_input,
            "file": file,
            "mode": "parameter",
            "texture": inspection,
        }

    # 2) MaterialX 계열이면 mtlximage 를 만들어 잇는다.
    names = list(shader.inputNames())
    if to_input not in names:
        close = [candidate for candidate in names if to_input.lower() in candidate.lower()]
        hint = f" 비슷한 것: {', '.join(close[:8])}" if close else ""
        raise ValueError(
            f"{shader.path()} 에 {to_input!r} 이라는 입력도, 같은 이름의 파일 "
            f"파라미터도 없습니다.{hint} shader_inputs 로 입력 목록을 보세요."
        )

    input_type = list(shader.inputDataTypes())[names.index(to_input)]
    signature = SIGNATURE_FOR_TYPE.get(input_type, "default")

    node_name = name or f"{to_input}_tex"
    image = material_node.createNode("mtlximage", node_name=node_name)
    image.parm("signature").set(signature)
    image.parm("file").set(paths.to_parm(file))
    if colorspace:
        image.parm("filecolorspace").set(colorspace)
    set_comment(image, comment)
    shader.setNamedInput(to_input, image, "out")
    image.moveToGoodPosition()

    output_type = list(image.outputDataTypes())[0] if image.outputDataTypes() else ""
    result: dict[str, Any] = {
        "material": material_node.path(),
        "shader": shader.path(),
        "texture_node": image.path(),
        "comment": image.comment(),
        "to_input": to_input,
        "to_type": input_type,
        "from_type": output_type,
        "signature": signature,
        "colorspace": image.parm("filecolorspace").eval(),
        "mode": "node",
        "texture": inspection,
    }
    if output_type and input_type and output_type != input_type:
        result["warning"] = (
            f"타입이 다릅니다: {output_type} -> {input_type}. "
            f"mtlximage 의 signature 를 바꾸거나 변환 노드를 사이에 넣으세요."
        )
    if image.errors():
        result["errors"] = list(image.errors())
    return result


def _image_file_references() -> list[tuple[hou.Parm, str]]:
    """씬이 참조하는 이미지 파일 파라미터만 추린다."""
    entries = []
    for parm, raw in hou.fileReferences():
        if parm is None:
            continue
        template = parm.parmTemplate()
        if not isinstance(template, hou.StringParmTemplate):
            continue
        if template.stringType() != hou.stringParmType.FileReference:
            continue
        if template.fileType() != hou.fileType.Image:
            continue
        if not raw:
            continue
        entries.append((parm, raw))
    return entries


@tool()
@undoable("Reload textures")
def reload_textures() -> dict[str, Any]:
    """텍스처 캐시를 비운다. 디스크에서 텍스처를 바꿨을 때 쓴다.

    Houdini 는 텍스처를 캐시하므로 파일을 덮어써도 화면이 바뀌지 않는다.
    렌더러용 캐시(texcache)와 뷰포트용 캐시(glcache)를 함께 비운다.
    """
    texture_result, texture_error = hou.hscript("texcache -c")
    gl_result, gl_error = hou.hscript("glcache -c")
    references = _image_file_references()
    return {
        "texture_cache": (texture_result or texture_error).strip(),
        "viewport_cache": (gl_result or gl_error).strip(),
        "image_references": len(references),
        "note": "캐시를 비웠습니다. 다음 렌더·뷰포트 갱신에서 디스크를 다시 읽습니다.",
    }
