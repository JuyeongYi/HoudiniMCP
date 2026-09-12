"""채널을 읽는다 — 값 목록이 아니라 분석 결과로.

기존 구현들은 `for i in range(n): track.evalAtSampleIndex(i)` 로 샘플을 하나씩
파고 그 목록을 그대로 JSON 에 실었다. 샘플 5,000개를 모델에게 보내면 컨텍스트만
탄다. 여기서는 `allSamples()` 한 번으로 받아 numpy 로 압축한다.

원본 샘플이 정말 필요하면 `channel_samples` 로 창을 좁혀 보거나
`export_channels` 로 파일에 쓴다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy

from houdini_mcp import tool

from . import _common as c

MAX_SAMPLE_POINTS = 200
"""channel_samples 가 한 번에 돌려주는 값의 상한. 넘으면 추려서 준다."""


@tool()
def list_channels(path: str, output_index: int = 0) -> dict[str, Any]:
    """CHOP 의 채널 목록. 이름·샘플 수·값 범위까지 한 줄씩.

    어떤 채널이 있고 대략 어떤 값인지 먼저 본다. 자세한 분석은
    channel_stats 다.

    Args:
        path: CHOP 경로.
        output_index: 출력이 여러 개인 CHOP 의 출력 번호.
    """
    node = c.require_chop(path)
    tracks = c.cooked_tracks(node, output_index)
    count = tracks[0].numSamples() if tracks else 0
    start, step = c.frame_axis(node, count)
    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "sample_rate": float(node.sampleRate()),
        "samples": int(count),
        "frame_range": [start, c.frame_of(max(count - 1, 0), start, step)],
        "frame_step": step,
        "count": len(tracks),
        "channels": [c.channel_brief(node, track) for track in tracks],
        "warnings": list(node.warnings()),
    }


@tool()
def channel_stats(
    path: str,
    channels: Sequence[str] | None = None,
    output_index: int = 0,
    spike_threshold: float = c.SPIKE_THRESHOLD,
    still_tolerance: float | None = None,
    loop_tolerance: float = c.LOOP_TOLERANCE,
    sparkline_points: int = c.SPARKLINE_POINTS,
) -> dict[str, Any]:
    """채널의 전체 분석. 이 팩의 핵심 툴이다.

    채널마다 다음을 낸다.

      stats        min/max/mean/std/range/분위수와 극값이 난 프레임
      first/last   처음·끝 값과 전체 변화량, 누적 이동량(path_length)
      non_finite   NaN/inf 개수와 그 프레임
      spikes       인접 샘플 차이의 이상치가 난 프레임
      still        변화가 없는 프레임 구간과 그 비율
      loop         첫·끝 값과 기울기로 본 루프 가능 여부
      sparkline    모양만 남긴 다운샘플 배열

    샘플 목록은 돌려주지 않는다. 원본이 필요하면 channel_samples 나
    export_channels 를 쓴다.

    Args:
        path: CHOP 경로.
        channels: 볼 채널 이름들. 생략하면 전부.
        output_index: 출력이 여러 개인 CHOP 의 출력 번호.
        spike_threshold: 튐 판정 문턱. 낮출수록 민감해진다. 기본 6.0
        still_tolerance: 정지로 볼 변화량. 생략하면 값 범위의 0.01%.
        loop_tolerance: 루프 판정 허용치. 값 범위 대비 비율. 기본 0.01
        sparkline_points: 스파크라인 점 수. 기본 48
    """
    node = c.require_chop(path)
    tracks = c.pick_tracks(node, channels, output_index)
    count = tracks[0].numSamples()
    start, step = c.frame_axis(node, count)

    analyzed = []
    for track in tracks:
        entry = c.analyze(
            c.track_values(track),
            start,
            step,
            spike_threshold=spike_threshold,
            still_tolerance=still_tolerance,
            loop_tolerance=loop_tolerance,
            sparkline_points=sparkline_points,
        )
        entry["name"] = track.name()
        analyzed.append(entry)

    return {
        "path": node.path(),
        "type": node.type().name(),
        "comment": node.comment(),
        "sample_rate": float(node.sampleRate()),
        "frame_range": [start, c.frame_of(max(count - 1, 0), start, step)],
        "count": len(analyzed),
        "channels": analyzed,
    }


@tool()
def channel_samples(
    path: str,
    channel: str,
    start_frame: float | None = None,
    end_frame: float | None = None,
    max_points: int = MAX_SAMPLE_POINTS,
    output_index: int = 0,
) -> dict[str, Any]:
    """채널의 **실제 값**을 본다. 구간을 좁히거나 추려서.

    분석만으로 부족해서 숫자를 직접 봐야 할 때 쓴다. 전 구간을 요구하면
    max_points 로 추려서 주고 `downsampled: true` 를 붙인다. 전체 원본이
    필요하면 export_channels 로 파일에 쓴다.

    Args:
        path: CHOP 경로.
        channel: 볼 채널 이름. list_channels 가 알려 준다.
        start_frame: 볼 구간 시작 프레임. 생략하면 채널의 처음.
        end_frame: 볼 구간 끝 프레임(포함). 생략하면 채널의 끝.
        max_points: 돌려줄 값의 상한. 넘으면 등간격으로 추린다.
        output_index: 출력이 여러 개인 CHOP 의 출력 번호.
    """
    if max_points < 2:
        raise ValueError(f"max_points 는 2 이상이어야 합니다: {max_points}")

    node = c.require_chop(path)
    track = c.pick_tracks(node, [channel], output_index)[0]
    total = track.numSamples()
    axis_start, step = c.frame_axis(node, total)
    if step == 0.0:
        raise ValueError(
            f"{path} 의 샘플 간격이 0 입니다. resample 필터로 rate 를 고치세요."
        )

    first = 0 if start_frame is None else int(round((start_frame - axis_start) / step))
    last = (
        total - 1 if end_frame is None else int(round((end_frame - axis_start) / step))
    )
    first, last = max(first, 0), min(last, total - 1)
    if first > last:
        raise ValueError(
            f"요청한 구간이 채널 밖입니다. 이 채널은 프레임 "
            f"{axis_start} ~ {c.frame_of(total - 1, axis_start, step)} 입니다."
        )

    # evalAtSampleRange 는 양끝을 포함해서 준다(실측).
    window = numpy.asarray(
        track.evalAtSampleRange(first, last), dtype=numpy.float64
    )
    downsampled = window.size > max_points
    if downsampled:
        index = numpy.linspace(0, window.size - 1, max_points).round().astype(numpy.int64)
        values = window[index]
        frames = c.frames_of(index + first, axis_start, step)
    else:
        values = window
        frames = c.frames_of(numpy.arange(window.size) + first, axis_start, step)

    return {
        "path": node.path(),
        "channel": track.name(),
        "total_samples": int(total),
        "window_samples": int(window.size),
        "returned": int(values.size),
        "downsampled": downsampled,
        "frame_range": [frames[0], frames[-1]] if frames else [],
        "frames": frames,
        "values": [round(float(v), 6) for v in values],
        "hint": (
            "전체 원본이 필요하면 export_channels 로 .bclip 에 쓰세요."
            if downsampled
            else None
        ),
    }
