"""COP 노드의 결과 이미지를 보고 수치로 읽는다.

    cop_preview     노드 출력 여러 개를 한 장의 그림으로 (composite view 대신)
    cop_layer_info  출력마다 해상도, 채널, 저장형, 데이터 성격, 채널별 값 범위

파일로 내보내지 않고 쿡된 레이어를 메모리에서 읽는다. 내보내기 설정(색 변환,
해상도 덮어쓰기)에 영향받지 않고 노드가 실제로 낸 값을 본다.

실측 메모 (Houdini 22.0.368)
- CopNode.layer(출력) 이 hou.ImageLayer 를 준다. allBufferElements() 는 bytes 이고
  1024² Float32 한 장을 읽는 데 0.01초 안팎이다.
- 출력마다 채널 수와 데이터 성격이 다르다. worleynoise 하나가 Mono(dist1),
  UV 2채널(center, typeInfo Position, 값 -1..1), ID(Int32, 해시 값)를 함께 낸다.
  그대로 0..1 로 자르면 UV 는 반이 검고 ID 는 전부 흰색이라 성격별로 표시한다.
- heighttonormal 의 offset 노멀은 typeInfo OffsetNormal, 값 0..1 이다.
- 버퍼는 (y, x) 순서로 쌓이고(bufferIndex(x, y) 와 일치), 버퍼 y=0 이 이미지
  아래쪽이다(bufferToImage(0,0) 의 y 가 -1). 그림으로 만들 때 행을 뒤집는다.
- file COP 은 쿡해도 outputLabels() 가 비어 있었다. 파일 레이어를 출력으로 따로
  잡아 줘야 하는 것으로 보이며, 이 툴은 출력이 없으면 그렇게 알린다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/ImageLayer.html
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import hou
import numpy

from houdini_mcp import image_result, tool

MAX_TILES = 16
MAX_SIDE = 4096

_DTYPES = {
    "Float32": numpy.float32,
    "Float16": numpy.float16,
    "Int32": numpy.int32,
    "Int16": numpy.int16,
    "Int8": numpy.int8,
    "Fixed16": numpy.uint16,
    "Fixed8": numpy.uint8,
}
_FIXED_SCALE = {"Fixed16": 65535.0, "Fixed8": 255.0}

_DATA_KINDS = {"Position", "Vector", "Normal", "TextureCoord", "SDF"}
"""값이 0..1 밖에 흩어지는 데이터. 그림으로 볼 때 채널별 범위로 늘린다."""


# --------------------------------------------------------------------------
# 읽기
# --------------------------------------------------------------------------


def _resolve(spec: str) -> tuple[hou.CopNode, int]:
    """"/img/net/node" 또는 "/img/net/node:출력이름|번호" 를 노드와 출력 번호로."""
    path, _, output = spec.partition(":")
    node = hou.node(path)
    if node is None:
        raise ValueError(f"그런 노드가 없습니다: {path}")
    if not isinstance(node, hou.CopNode):
        category = node.type().category().name()
        hint = ""
        if category == "CopNet" or node.type().name() == "copnet":
            hint = " copnet 자체가 아니라 그 안의 노드 경로를 주세요."
        elif category == "Cop2":
            hint = " 옛 COP2(cop2net) 는 다루지 않습니다. Copernicus(copnet) 노드를 주세요."
        raise ValueError(f"{path} 는 Copernicus COP 노드가 아닙니다({category}).{hint}")
    # file COP 처럼 읽은 파일의 레이어로 출력이 정해지는 노드는 쿡 전에는 출력이
    # 비어 있다(실측). 출력 목록을 보기 전에 쿡한다.
    try:
        node.cook()
    except hou.OperationFailed:
        pass
    labels = list(node.outputLabels())
    if not labels:
        raise ValueError(f"{path} 에는 출력이 없습니다. 출력 노드(rop_image 등)가 아니라 이미지를 내는 노드를 주세요.")
    if not output:
        index = 0
    elif output.isdigit():
        index = int(output)
    elif output in labels:
        index = labels.index(output)
    else:
        index = -1
    if not 0 <= index < len(labels):
        listed = ", ".join(f"{i}={name}" for i, name in enumerate(labels))
        raise ValueError(f"{path} 에 '{output}' 출력이 없습니다. 출력: {listed}")
    return node, index


def _layer(node: hou.CopNode, index: int, frame: float | None) -> hou.ImageLayer:
    data_type = list(node.outputDataTypes())[index]
    try:
        layer = node.layer(index) if frame is None else node.layerAtFrame(float(frame), index)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{node.path()} 의 {index}번 출력({data_type})을 이미지 레이어로 읽지 못했습니다: {exc}. "
            f"지오메트리나 VDB 출력은 이미지가 아닙니다."
        ) from exc
    if layer is None:
        errors = "; ".join(node.errors()) or "쿡 에러 없음"
        raise ValueError(f"{node.path()} 의 {index}번 출력이 비어 있습니다({errors}).")
    return layer


def _enum_name(value: Any) -> str:
    return str(value).rsplit(".", 1)[-1]


def _rect(rect: hou.BoundingRect) -> list[float]:
    """[xmin, ymin, xmax, ymax]. dataWindow 은 리스트가 아니라 BoundingRect 다(실측)."""
    low, high = rect.min(), rect.max()
    return [low[0], low[1], high[0], high[1]]


def _pixels(layer: hou.ImageLayer) -> numpy.ndarray:
    """(높이, 너비, 채널) 배열. 첫 행이 이미지 위쪽이 되게 뒤집는다."""
    width, height = layer.bufferResolution()
    channels = layer.channelCount()
    storage = _enum_name(layer.storageType())
    dtype = _DTYPES.get(storage)
    if dtype is None:
        raise ValueError(f"지원하지 않는 저장형입니다: {storage}")
    data = numpy.frombuffer(layer.allBufferElements(), dtype=dtype)
    pixels = data.reshape(height, width, channels).astype(numpy.float64)
    if storage in _FIXED_SCALE:
        pixels /= _FIXED_SCALE[storage]
    return pixels[::-1]


def _channel_stats(pixels: numpy.ndarray) -> list[dict[str, float]]:
    return [
        {
            "min": round(float(pixels[..., c].min()), 4),
            "max": round(float(pixels[..., c].max()), 4),
            "mean": round(float(pixels[..., c].mean()), 4),
        }
        for c in range(pixels.shape[2])
    ]


# --------------------------------------------------------------------------
# 표시
# --------------------------------------------------------------------------


def _display(pixels: numpy.ndarray, kind: str, normalize: str) -> tuple[numpy.ndarray, str]:
    """그림으로 볼 0..1 RGB 와, 어떻게 바꿨는지 한 줄 설명."""
    channels = pixels.shape[2]
    if kind == "ID":
        ids = pixels[..., 0].astype(numpy.int64) & 0xFFFFFFFF
        hashed = (ids * 2654435761) & 0xFFFFFFFF
        rgb = numpy.stack([(hashed >> s) & 255 for s in (0, 8, 16)], axis=-1) / 255.0
        return rgb, "id hash colors"

    data = pixels[..., : min(channels, 3)]
    low, high = data.min(), data.max()
    stretch = normalize == "on" or (
        normalize == "auto" and (kind in _DATA_KINDS or low < -1e-3 or high > 1.0 + 1e-3)
    )
    if stretch:
        mins = data.reshape(-1, data.shape[2]).min(axis=0)
        spans = numpy.maximum(data.reshape(-1, data.shape[2]).max(axis=0) - mins, 1e-9)
        data = (data - mins) / spans
        # 그림 안에 적는 글이라 ASCII 로 쓴다. OIIO 기본 글꼴에 한글이 없어 네모로 깨졌다.
        note = "stretched per channel"
    else:
        data = numpy.clip(data, 0.0, 1.0)
        note = "clamped 0..1"
    if channels >= 3 and kind in ("Color", "Raw") and not stretch:
        data = numpy.where(data <= 0.0031308, data * 12.92, 1.055 * numpy.power(data, 1 / 2.4) - 0.055)
        note += ", sRGB"
    if data.shape[2] == 1:
        data = numpy.repeat(data, 3, axis=2)
    elif data.shape[2] == 2:
        data = numpy.concatenate([data, numpy.zeros(data.shape[:2] + (1,))], axis=2)
    return data, note


@tool()
def cop_preview(
    nodes: list[str],
    frame: float | None = None,
    tile_size: int = 384,
    columns: int = 4,
    normalize: str = "auto",
) -> Any:
    """COP 노드가 만든 이미지를 그림으로 본다. composite view 를 대신한다.

    텍스처나 마스크를 만들었으면 재질에 붙이기 전에 반드시 이 툴로 본다. 크기,
    대비, 반복 무늬, 노멀 방향은 수치만으로 판단할 수 없다. 여러 노드를 한 장에
    나란히 놓으므로 단계별로 무엇이 바뀌는지 비교할 수 있다. 칸마다 아래에 이름,
    해상도, 채널, 값 범위, 표시 방식을 적는다.

    표시 방식(normalize="auto"):
    - Mono/RGB 색 데이터는 0..1 로 자르고 RGB 는 sRGB 로 보여 준다
    - 위치·UV·벡터처럼 0..1 밖으로 퍼지는 값은 채널별 범위로 늘린다
    - ID 는 값마다 다른 색으로 칠한다
    - 2채널은 R, G 로, 4채널은 알파를 빼고 보여 준다

    Args:
        nodes: COP 노드 경로들. 출력을 고르려면 ":" 뒤에 이름이나 번호를 붙인다.
            최대 16개. 예: ["/img/tex/noise1", "/img/tex/worley1:dist2"]
        frame: 볼 프레임. 생략하면 현재 프레임.
        tile_size: 칸 하나의 한 변 픽셀. 이미지 비율은 유지한다.
        columns: 한 줄의 칸 수.
        normalize: "auto", "on"(항상 범위로 늘림), "off"(항상 0..1 로 자름).
    """
    if not nodes:
        raise ValueError('nodes 가 비어 있습니다. 예: ["/img/tex/noise1"]')
    if len(nodes) > MAX_TILES:
        raise ValueError(f"노드가 {len(nodes)}개입니다. 한 장에 최대 {MAX_TILES}개까지 봅니다.")
    if normalize not in ("auto", "on", "off"):
        raise ValueError(f'normalize 는 "auto", "on", "off" 중 하나입니다: {normalize}')
    columns = max(1, min(int(columns), len(nodes)))
    rows = -(-len(nodes) // columns)
    if tile_size < 64 or max(tile_size * columns, tile_size * rows) > MAX_SIDE:
        raise ValueError(f"칸 {tile_size} 는 64 이상, 전체 한 변은 {MAX_SIDE} 이하가 되게 주세요.")

    import OpenImageIO as oiio

    label_height = 62
    cell_h = tile_size + label_height
    sheet = oiio.ImageBuf(oiio.ImageSpec(tile_size * columns, cell_h * rows, 3, "float"))
    oiio.ImageBufAlgo.fill(sheet, (0.12, 0.12, 0.12))
    for position, spec in enumerate(nodes):
        node, index = _resolve(spec)
        layer = _layer(node, index, frame)
        kind = _enum_name(layer.typeInfo())
        pixels = _pixels(layer)
        rgb, note = _display(pixels, kind, normalize)
        source = oiio.ImageBuf(numpy.ascontiguousarray(rgb, dtype=numpy.float32))
        height, width = rgb.shape[:2]
        scale = tile_size / max(width, height)
        fit_w, fit_h = max(1, round(width * scale)), max(1, round(height * scale))
        tile = oiio.ImageBufAlgo.resize(source, roi=oiio.ROI(0, fit_w, 0, fit_h, 0, 1, 0, 3))
        col, row = position % columns, position // columns
        x0 = col * tile_size + (tile_size - fit_w) // 2
        y0 = row * cell_h + (tile_size - fit_h) // 2
        oiio.ImageBufAlgo.paste(sheet, x0, y0, 0, 0, tile)

        stats = _channel_stats(pixels)
        low = min(s["min"] for s in stats)
        high = max(s["max"] for s in stats)
        label_output = list(node.outputLabels())[index]
        lines = (
            (f"{node.name()}:{label_output}", 15, (1.0, 1.0, 1.0)),
            (f"{width}x{height} {pixels.shape[2]}ch {kind}", 13, (0.8, 0.8, 0.8)),
            (f"[{low:.4g} .. {high:.4g}] {note}", 13, (0.8, 0.8, 0.8)),
        )
        base_y = row * cell_h + tile_size
        for number, (text, size, color) in enumerate(lines):
            limit = max(8, int(tile_size / (size * 0.62)))
            if len(text) > limit:
                text = text[: limit - 2] + ".."
            oiio.ImageBufAlgo.render_text(sheet, col * tile_size + 6, base_y + 17 + number * 18, text, size, "", color)

    with tempfile.TemporaryDirectory(prefix="hmcp_cop_") as tmp:
        output = Path(tmp) / "cop_preview.png"
        if not sheet.write(str(output), "uint8"):
            raise RuntimeError(f"미리보기 이미지를 쓰지 못했습니다: {sheet.geterror()}")
        return image_result(output.read_bytes(), "png")


@tool()
def cop_layer_info(path: str, frame: float | None = None) -> dict[str, Any]:
    """COP 노드의 출력마다 레이어 정보를 수치로 돌려준다.

    해상도, 채널 수, 저장형(Float32 등), 데이터 성격(typeInfo: Raw, Color,
    OffsetNormal, Position, ID ...), 데이터/표시 창, 채널별 최소·최대·평균을 준다.
    텍스처 값이 의도한 범위에 들어가는지(예: 알베도 0..1, 거칠기 0.3..0.9) 확인하거나,
    어느 출력이 이미지인지 알 때 쓴다. 그림은 cop_preview 로 본다.

    Args:
        path: COP 노드 경로. 예: "/img/tex/worley1"
        frame: 볼 프레임. 생략하면 현재 프레임.
    """
    node, _ = _resolve(path)
    outputs = []
    for index, (label, data_type) in enumerate(zip(node.outputLabels(), node.outputDataTypes())):
        entry: dict[str, Any] = {"index": index, "name": label, "data_type": data_type}
        try:
            layer = _layer(node, index, frame)
        except ValueError as exc:
            entry["image"] = False
            entry["note"] = str(exc)
            outputs.append(entry)
            continue
        pixels = _pixels(layer)
        entry.update({
            "image": True,
            "resolution": list(layer.bufferResolution()),
            "channels": layer.channelCount(),
            "storage": _enum_name(layer.storageType()),
            "type_info": _enum_name(layer.typeInfo()),
            "data_window": _rect(layer.dataWindow()),
            "display_window": _rect(layer.displayWindow()),
            "border": _enum_name(layer.border()),
            "constant": layer.isConstant(),
            "channel_stats": _channel_stats(pixels),
        })
        outputs.append(entry)
    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
        "outputs": outputs,
    }
