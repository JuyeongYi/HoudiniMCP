"""렌더 결과 이미지를 읽는 툴들.

기존 Houdini MCP 구현 다섯 중 렌더 결과를 열어 보는 곳은 한 곳도 없다. 렌더를
걸고 `{"status": "done"}` 을 돌려주면, 새까만 프레임이 나와도 모델은 성공한
줄 안다. 여기의 툴은 픽셀을 실제로 읽는다.

`image_preview` 는 그림 자체를 돌려주고, 나머지는 숫자를 돌려준다. 숫자가 먼저다 -
평균이 0 이라는 사실은 썸네일을 보는 것보다 확실하고 싸다.
"""

from __future__ import annotations

from typing import Any

from houdini_mcp import image_result, tool

from ._common import expand_path, require_file
from ._image import compare, quick_level, subimages, summarize

MAX_PREVIEW_WIDTH = 2048
MAX_SEQUENCE_FRAMES = 240
"""시퀀스 점검에서 훑을 프레임 상한. 한 장마다 파일을 열어 통계를 낸다."""

FLICKER_RATIO = 2.0
"""이웃 프레임 대비 평균 밝기가 이 배수 이상 튀면 깜빡임으로 본다."""


@tool()
def image_info(path: str, frame: float | None = None, subimage: int = 0) -> dict[str, Any]:
    """렌더된 이미지를 열어 해상도·채널(AOV)·비트뎁스와 채널별 픽셀 통계를 낸다.

    렌더가 끝난 뒤 반드시 부른다. 채널마다 min/max/평균/표준편차와 NaN·Inf
    개수를 내고, 그것을 읽어 "전부 검다", "알파가 비었다", "NaN 이 있다" 같은
    진단을 `diagnosis` 에 담아 준다.

    EXR 의 AOV 가 서브이미지로 나뉘어 있으면 `subimages` 에 목록이 나온다.
    다른 AOV 의 통계를 보려면 `subimage` 를 바꿔 다시 부른다.

    Args:
        path: 이미지 경로. $HIP/$F4 같은 Houdini 변수를 써도 된다.
        frame: 경로에 $F 가 있을 때 풀어 넣을 프레임.
        subimage: 볼 서브이미지(AOV) 번호.
    """
    resolved = require_file(path, frame)
    return summarize(resolved, subimage=int(subimage), with_stats=True)


@tool()
def image_preview(
    path: str,
    width: int = 512,
    frame: float | None = None,
    subimage: int = 0,
    exposure: float = 0.0,
) -> Any:
    """렌더된 이미지를 썸네일로 줄여 그림으로 돌려준다. 눈으로 확인할 때.

    EXR 처럼 씬 리니어인 이미지는 sRGB 로 옮겨서 준다. 그냥 8비트로 줄이면
    실제보다 훨씬 어둡게 보여서 잘못된 판단을 하게 된다.

    숫자로 먼저 보는 편이 낫다 - `image_info` 가 평균이 0 이라고 말해 주면
    썸네일을 볼 필요도 없다. 이 툴은 구도나 형태를 확인할 때 쓴다.

    Args:
        path: 이미지 경로.
        width: 썸네일 가로 픽셀. 세로는 비율대로.
        frame: 경로에 $F 가 있을 때 풀어 넣을 프레임.
        subimage: 볼 서브이미지(AOV) 번호.
        exposure: 스톱 단위 노출 보정. 어두운 렌더를 볼 때 +2 처럼.
    """
    if width < 8 or width > MAX_PREVIEW_WIDTH:
        raise ValueError(
            f"width 는 8 이상 {MAX_PREVIEW_WIDTH} 이하여야 합니다: {width}"
        )
    resolved = require_file(path, frame)
    from ._image import thumbnail_png

    return image_result(
        thumbnail_png(resolved, int(width), int(subimage), float(exposure)), "png"
    )


@tool()
def compare_images(
    a: str,
    b: str,
    frame: float | None = None,
    fail_threshold: float = 0.01,
    warn_threshold: float = 0.001,
) -> dict[str, Any]:
    """두 렌더를 픽셀 단위로 비교한다. 고친 것이 정말 달라졌는지 확인할 때.

    파라미터를 바꾸고 다시 렌더했는데 아무것도 안 변했다면 그 파라미터는
    이 렌더에 영향이 없다는 뜻이다. 반대로 바뀌면 안 되는 것이 바뀌었는지도
    여기서 잡는다. 가장 크게 다른 픽셀의 좌표와 채널까지 알려 준다.

    Args:
        a: 첫 번째 이미지 경로.
        b: 두 번째 이미지 경로.
        frame: 두 경로에 $F 가 있을 때 풀어 넣을 프레임.
        fail_threshold: 이 값보다 큰 차이를 '실패 픽셀'로 센다.
        warn_threshold: 이 값보다 큰 차이를 '경고 픽셀'로 센다.
    """
    left = require_file(a, frame)
    right = require_file(b, frame)
    result = compare(left, right, fail_threshold, warn_threshold)
    if result["identical"]:
        result["verdict"] = "두 이미지가 완전히 같습니다. 바꾼 것이 렌더에 반영되지 않았습니다."
    elif result["failed_pixels"] == 0:
        result["verdict"] = (
            f"차이가 임계값({fail_threshold}) 아래입니다. "
            f"RMS {result['rms_error']} - 사실상 같은 그림입니다."
        )
    else:
        result["verdict"] = (
            f"픽셀 {result['failed_pixels']}개"
            f"({result['failed_fraction'] * 100:.2f}%)가 임계값을 넘습니다. "
            f"가장 큰 차이는 {result['max_error_at']} 에서 {result['max_error']}."
        )
    return result


@tool()
def image_sequence_report(
    path: str, start: float, end: float, inc: float = 1.0
) -> dict[str, Any]:
    """렌더한 시퀀스 전체를 훑어 빠진 프레임·검은 프레임·깜빡임을 찾는다.

    시퀀스 렌더가 끝나고 한 장씩 열어 보는 대신 한 번에 본다. 프레임마다
    파일이 있는지 보고, 있으면 색 채널 평균을 내서 셋을 잡는다.

    - 파일이 없는 프레임 (렌더가 거기서 죽었다)
    - 완전히 검은 프레임 (그 프레임만 라이트나 지오메트리가 빠졌다)
    - 이웃 대비 밝기가 2배 이상 튀는 프레임 (깜빡임)

    Args:
        path: $F4 같은 프레임 변수가 든 경로. 예: $HIP/render/beauty.$F4.exr
        start: 시작 프레임.
        end: 끝 프레임.
        inc: 프레임 증가폭.
    """
    if inc <= 0:
        raise ValueError(f"inc 는 0보다 커야 합니다: {inc}")
    frames: list[float] = []
    current = float(start)
    while current <= float(end) + 1e-6 and len(frames) < MAX_SEQUENCE_FRAMES:
        frames.append(round(current, 4))
        current += float(inc)
    if not frames:
        raise ValueError(f"프레임 범위가 비어 있습니다: {start}~{end} (inc={inc})")

    first = expand_path(path, frames[0])
    if str(first) == str(expand_path(path, frames[-1])) and len(frames) > 1:
        raise ValueError(
            f"경로에 프레임 변수가 없습니다: {path}. $F4 나 $F 를 넣으세요. "
            f"예: {first.parent.as_posix()}/{first.stem}.$F4{first.suffix}"
        )

    entries: list[dict[str, Any]] = []
    missing: list[float] = []
    black: list[float] = []
    broken: list[float] = []
    for frame in frames:
        resolved = expand_path(path, frame)
        if not resolved.exists():
            missing.append(frame)
            entries.append({"frame": frame, "missing": True})
            continue
        try:
            level = quick_level(resolved)
        except Exception as exc:  # noqa: BLE001 - 깨진 파일도 결과에 담는다
            broken.append(frame)
            entries.append({"frame": frame, "error": str(exc)[:200]})
            continue
        entry = {"frame": frame, "file": str(resolved), **level}
        if level["max"] <= 0.0:
            black.append(frame)
        entries.append(entry)

    # 깜빡임 - 이웃한 두 프레임의 평균 밝기가 크게 튀는 곳
    flicker: list[dict[str, Any]] = []
    levels = [(e["frame"], e["mean"]) for e in entries if "mean" in e]
    for (prev_frame, prev_mean), (frame, mean) in zip(levels, levels[1:]):
        low, high = sorted((prev_mean, mean))
        if low > 1e-6 and high / low >= FLICKER_RATIO:
            flicker.append({
                "from": prev_frame,
                "to": frame,
                "mean_from": prev_mean,
                "mean_to": mean,
            })

    resolutions = {tuple(e["resolution"]) for e in entries if "resolution" in e}
    summary: list[str] = []
    if missing:
        summary.append(f"파일이 없는 프레임 {len(missing)}개: {missing[:10]}")
    if black:
        summary.append(f"완전히 검은 프레임 {len(black)}개: {black[:10]}")
    if broken:
        summary.append(f"열지 못한 프레임 {len(broken)}개: {broken[:10]}")
    if len(resolutions) > 1:
        summary.append(f"해상도가 섞여 있습니다: {sorted(resolutions)}")
    if flicker:
        summary.append(f"밝기가 튀는 구간 {len(flicker)}곳")
    if not summary:
        summary.append(f"{len(frames)}프레임 모두 정상입니다.")

    return {
        "pattern": path,
        "frames_checked": len(frames),
        "truncated": len(frames) >= MAX_SEQUENCE_FRAMES,
        "missing_frames": missing,
        "black_frames": black,
        "unreadable_frames": broken,
        "flicker": flicker,
        "resolutions": [list(r) for r in sorted(resolutions)],
        "summary": summary,
        "frames": entries if len(entries) <= 60 else entries[:60],
    }


@tool()
def list_aovs(path: str, frame: float | None = None) -> dict[str, Any]:
    """이미지 파일에 실제로 들어 있는 AOV 목록. 렌더 설정이 아니라 결과에서 읽는다.

    `render_settings` 는 "무엇을 쓰기로 했는가"를, 이 툴은 "무엇이 실제로
    쓰였는가"를 보여준다. 둘이 다르면 RenderVar 가 델리게이트에 전달되지
    않은 것이다.

    Args:
        path: 이미지 경로.
        frame: 경로에 $F 가 있을 때 풀어 넣을 프레임.
    """
    resolved = require_file(path, frame)
    parts = subimages(resolved)
    if not parts:
        raise ValueError(
            f"{resolved} 의 서브이미지를 읽지 못했습니다. 지원하는 포맷인지 "
            f"image_info 로 확인하세요."
        )
    top = summarize(resolved, subimage=0, with_stats=False)
    return {
        "file": str(resolved),
        "file_format": top["file_format"],
        "subimage_count": len(parts),
        "aovs": parts,
        "flat_channels": top["channels"],
        "note": (
            "서브이미지가 하나면 AOV 가 채널로 합쳐져 있거나 beauty 뿐입니다."
            if len(parts) == 1
            else "각 AOV 의 통계는 image_info 에 subimage 번호를 주어 보세요."
        ),
    }
