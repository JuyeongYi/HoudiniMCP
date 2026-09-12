"""렌더 결과 이미지를 실제로 읽는 헬퍼. OpenImageIO 를 쓴다. 툴은 없다.

이 팩의 존재 이유가 이 파일이다. 렌더를 걸고 "끝났습니다" 로 돌려주면
새까만 프레임이 나와도 아무도 모른다. 여기서 픽셀을 읽어 채널별 통계를 내고,
검거나 NaN 이 섞였으면 그렇다고 말한다.

OpenImageIO 2.5.18.0 (Houdini 22.0 번들). 실측으로 확인한 것들:

- `ImageBufAlgo.computePixelStats(buf)` 는 `PixelStats` 를 돌려준다.
  필드는 min/max/avg/stddev/sum/sum2/nancount/infcount/finitecount 이고
  전부 채널 수만큼의 리스트다.
- `isConstantColor` 는 균일하면 색 튜플을, 아니면 None 을 돌려준다.
- EXR 의 AOV 는 서브이미지로 나뉘어 들어가므로 서브이미지를 훑어야 전부 보인다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import OpenImageIO as oiio

MAX_CHANNELS = 32
"""통계를 낼 채널 수 상한. AOV 가 많은 EXR 은 채널이 수십 개다."""

MAX_SUBIMAGES = 64

INTERESTING_METADATA = (
    "renderTime_s",
    "renderMemory_s",
    "husk:command",
    "husk:usd_file",
    "camera",
    "oiio:ColorSpace",
    "compression",
    "frame",
    "Software",
)
"""렌더 결과를 판단하는 데 쓰이는 메타데이터만 골라 낸다."""

BLACK_EPS = 1e-6
"""이보다 작으면 0 으로 본다. half float 의 잡음을 검은색으로 잘못 읽지 않도록."""

DARK_EPS = 1e-3


def open_buf(path: Path, subimage: int = 0) -> oiio.ImageBuf:
    """이미지를 연다. 못 열면 OIIO 가 준 이유를 그대로 전한다."""
    buf = oiio.ImageBuf(str(path), int(subimage), 0)
    if not buf.initialized:
        raise ValueError(
            f"이미지를 열지 못했습니다: {path} - {buf.geterror() or '원인 불명'}. "
            f"렌더가 끝나기 전이거나 지원하지 않는 포맷일 수 있습니다."
        )
    # ImageBuf 는 게으르게 읽는다. 통계를 내려면 픽셀이 실제로 있어야 한다.
    if not buf.read():
        raise ValueError(
            f"이미지 픽셀을 읽지 못했습니다: {path} - {buf.geterror() or '원인 불명'}"
        )
    return buf


def subimages(path: Path) -> list[dict[str, Any]]:
    """EXR 의 서브이미지(대개 AOV) 목록. 이름과 채널만 가볍게 읽는다."""
    inp = oiio.ImageInput.open(str(path))
    if inp is None:
        return []
    out: list[dict[str, Any]] = []
    try:
        index = 0
        while index < MAX_SUBIMAGES and inp.seek_subimage(index, 0):
            spec = inp.spec()
            out.append({
                "index": index,
                "name": spec.get_string_attribute("oiio:subimagename") or None,
                "channels": list(spec.channelnames)[:MAX_CHANNELS],
                "resolution": [spec.width, spec.height],
            })
            index += 1
    finally:
        inp.close()
    return out


def describe_spec(buf: oiio.ImageBuf) -> dict[str, Any]:
    """해상도·채널·비트뎁스와, 판단에 쓸 만한 메타데이터."""
    spec = buf.spec()
    metadata = {}
    for attrib in spec.extra_attribs:
        if attrib.name in INTERESTING_METADATA:
            metadata[attrib.name] = attrib.value
    return {
        "resolution": [spec.width, spec.height],
        "channels": list(spec.channelnames)[:MAX_CHANNELS],
        "channel_count": spec.nchannels,
        "format": str(spec.format),
        "alpha_channel": spec.alpha_channel if spec.alpha_channel >= 0 else None,
        "file_format": buf.file_format_name,
        "deep": bool(buf.deep),
        "subimage_count": buf.nsubimages,
        "mip_levels": buf.nmiplevels,
        "data_window": [spec.x, spec.y, spec.width, spec.height],
        "display_window": [
            spec.full_x, spec.full_y, spec.full_width, spec.full_height
        ],
        "metadata": metadata,
    }


def channel_stats(buf: oiio.ImageBuf) -> list[dict[str, Any]]:
    """채널마다 min/max/avg/stddev 와 NaN·Inf 개수."""
    spec = buf.spec()
    stats = oiio.ImageBufAlgo.computePixelStats(buf)
    if stats is None:
        raise RuntimeError(
            f"픽셀 통계를 내지 못했습니다: {buf.geterror() or '원인 불명'}"
        )
    names = list(spec.channelnames)
    out = []
    for index in range(min(spec.nchannels, MAX_CHANNELS)):
        out.append({
            "channel": names[index] if index < len(names) else f"ch{index}",
            "min": round(float(stats.min[index]), 6),
            "max": round(float(stats.max[index]), 6),
            "avg": round(float(stats.avg[index]), 6),
            "stddev": round(float(stats.stddev[index]), 6),
            "nan": int(stats.nancount[index]),
            "inf": int(stats.infcount[index]),
        })
    return out


def diagnose(buf: oiio.ImageBuf, stats: list[dict[str, Any]]) -> list[str]:
    """통계를 사람 말로 옮긴다. 여기가 "새까맣다"를 말하는 자리다."""
    notes: list[str] = []
    spec = buf.spec()
    alpha_index = spec.alpha_channel
    color = [s for i, s in enumerate(stats) if i != alpha_index]

    if any(s["nan"] for s in stats):
        worst = max(stats, key=lambda s: s["nan"])
        notes.append(
            f"NaN 이 있습니다 ({worst['channel']} 채널에 {worst['nan']}개). "
            f"셰이더나 지오메트리에 0 나누기가 있을 수 있습니다."
        )
    if any(s["inf"] for s in stats):
        worst = max(stats, key=lambda s: s["inf"])
        notes.append(
            f"무한대 값이 있습니다 ({worst['channel']} 채널에 {worst['inf']}개). "
            f"라이트 세기나 이미시브가 과한지 보세요."
        )

    if color and all(abs(s["max"]) < BLACK_EPS for s in color):
        notes.append(
            "색 채널이 전부 0 입니다 - 완전히 새까만 이미지입니다. 라이트가 "
            "없거나, 카메라가 지오메트리를 안 보고 있거나, 렌더가 중간에 "
            "끊겼을 수 있습니다. validate_render 로 확인하세요."
        )
    elif color and all(s["avg"] < DARK_EPS for s in color):
        notes.append(
            f"거의 검습니다 (색 평균 {max(s['avg'] for s in color):.6f}). "
            f"노출이나 라이트 세기를 올려 보세요."
        )

    if alpha_index is not None and 0 <= alpha_index < len(stats):
        alpha = stats[alpha_index]
        if alpha["max"] < BLACK_EPS:
            notes.append(
                "알파가 전부 0 입니다 - 카메라에 아무것도 안 잡혔다는 뜻입니다. "
                "카메라 위치와 지오메트리의 purpose 를 확인하세요."
            )
        elif alpha["min"] > 1.0 - BLACK_EPS and alpha["avg"] > 1.0 - BLACK_EPS:
            notes.append("알파가 전부 1 입니다 - 화면 전체가 무언가로 덮여 있습니다.")

    constant = oiio.ImageBufAlgo.isConstantColor(buf)
    if constant is not None:
        notes.append(
            f"이미지 전체가 한 가지 색입니다: "
            f"{[round(float(c), 6) for c in constant][:MAX_CHANNELS]}"
        )

    if color and max(s["max"] for s in color) > 1e4:
        notes.append(
            f"값이 매우 큽니다 (최대 {max(s['max'] for s in color):.1f}). "
            f"파이어플라이나 과한 이미시브일 수 있습니다."
        )

    if not notes:
        notes.append("특이사항 없습니다 - 값이 정상 범위에 있습니다.")
    return notes


def summarize(path: Path, subimage: int = 0, with_stats: bool = True) -> dict[str, Any]:
    """이미지 하나를 통째로 설명한다. 스펙 + AOV + 통계 + 진단."""
    buf = open_buf(path, subimage)
    report: dict[str, Any] = {
        "file": str(path),
        "bytes": path.stat().st_size,
        "subimage": subimage,
    }
    report.update(describe_spec(buf))
    if buf.nsubimages > 1:
        report["subimages"] = subimages(path)
    if with_stats:
        stats = channel_stats(buf)
        report["stats"] = stats
        report["diagnosis"] = diagnose(buf, stats)
    return report


def quick_level(path: Path) -> dict[str, Any]:
    """시퀀스를 훑을 때 쓰는 가벼운 요약. 평균과 NaN 여부만."""
    buf = open_buf(path, 0)
    spec = buf.spec()
    stats = oiio.ImageBufAlgo.computePixelStats(buf)
    alpha = spec.alpha_channel
    color_indices = [i for i in range(spec.nchannels) if i != alpha]
    avgs = [float(stats.avg[i]) for i in color_indices] or [0.0]
    return {
        "mean": round(sum(avgs) / len(avgs), 6),
        "max": round(max(float(stats.max[i]) for i in color_indices), 6)
        if color_indices
        else 0.0,
        "nan": int(sum(stats.nancount)),
        "inf": int(sum(stats.infcount)),
        "resolution": [spec.width, spec.height],
    }


def thumbnail_png(
    path: Path, width: int, subimage: int = 0, exposure: float = 0.0
) -> bytes:
    """썸네일 PNG 바이트. 선형 이미지는 sRGB 로 옮겨야 사람이 볼 수 있다."""
    buf = open_buf(path, subimage)
    spec = buf.spec()
    height = max(1, round(width * spec.height / max(1, spec.width)))
    roi = oiio.ROI(0, int(width), 0, int(height), 0, 1, 0, spec.nchannels)
    small = oiio.ImageBufAlgo.resize(buf, roi=roi)
    if small is None or not small.initialized:
        raise RuntimeError(f"썸네일을 만들지 못했습니다: {buf.geterror() or path}")

    if exposure:
        scaled = oiio.ImageBufAlgo.mul(small, float(2.0**exposure))
        if scaled is not None and scaled.initialized:
            small = scaled

    # half/float 은 씬 리니어다. 그대로 8비트로 쓰면 어둡게 보인다.
    if str(spec.format) in ("half", "float", "double"):
        converted = oiio.ImageBufAlgo.colorconvert(small, "linear", "sRGB")
        if converted is not None and converted.initialized:
            small = converted

    import tempfile

    with tempfile.TemporaryDirectory(prefix="hmcp_render_thumb_") as tmp:
        out = Path(tmp) / "preview.png"
        if not small.write(str(out), "uint8"):
            raise RuntimeError(
                f"썸네일을 저장하지 못했습니다: {small.geterror() or '원인 불명'}"
            )
        return out.read_bytes()


def compare(a: Path, b: Path, fail_threshold: float, warn_threshold: float) -> dict[str, Any]:
    """두 이미지의 차이. 렌더를 고친 뒤 정말 달라졌는지 확인할 때 쓴다."""
    buf_a = open_buf(a, 0)
    buf_b = open_buf(b, 0)
    spec_a, spec_b = buf_a.spec(), buf_b.spec()
    if (spec_a.width, spec_a.height) != (spec_b.width, spec_b.height):
        raise ValueError(
            f"해상도가 다릅니다: {spec_a.width}x{spec_a.height} vs "
            f"{spec_b.width}x{spec_b.height}. 같은 해상도로 다시 렌더하거나 "
            f"image_info 로 각각을 확인하세요."
        )
    if spec_a.nchannels != spec_b.nchannels:
        raise ValueError(
            f"채널 수가 다릅니다: {spec_a.nchannels}({list(spec_a.channelnames)}) vs "
            f"{spec_b.nchannels}({list(spec_b.channelnames)})."
        )

    result = oiio.ImageBufAlgo.compare(
        buf_a, buf_b, float(fail_threshold), float(warn_threshold)
    )
    pixels = max(1, spec_a.width * spec_a.height)
    names = list(spec_a.channelnames)
    return {
        "a": str(a),
        "b": str(b),
        "resolution": [spec_a.width, spec_a.height],
        "mean_error": round(float(result.meanerror), 8),
        "rms_error": round(float(result.rms_error), 8),
        "max_error": round(float(result.maxerror), 8),
        "max_error_at": {
            "x": int(result.maxx),
            "y": int(result.maxy),
            "channel": names[result.maxc] if result.maxc < len(names) else result.maxc,
        },
        "psnr": None if result.PSNR == float("inf") else round(float(result.PSNR), 3),
        "failed_pixels": int(result.nfail),
        "warned_pixels": int(result.nwarn),
        "failed_fraction": round(result.nfail / pixels, 6),
        "identical": result.maxerror == 0.0,
    }
