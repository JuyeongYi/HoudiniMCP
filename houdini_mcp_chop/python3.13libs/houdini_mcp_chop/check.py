"""채널을 **실제 값으로** 판정한다.

기존 구현의 `validate_loop_contract` 는 노드 속성을 비교했다 — 프레임 범위가
맞나, 파라미터가 같나. 그것으로는 커브가 끊기는지 알 수 없다. 여기서는 첫
샘플과 끝 샘플의 값과 기울기를 직접 본다.

튐도 마찬가지다. 값 목록을 모델에게 던져 "튀는 데 있어?"라고 묻는 대신, 인접
샘플 차이의 이상치를 numpy 로 찾아 **프레임 번호**를 준다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy

from houdini_mcp import tool

from . import _common as c


@tool()
def check_loop(
    path: str,
    channels: Sequence[str] | None = None,
    tolerance: float = c.LOOP_TOLERANCE,
    output_index: int = 0,
) -> dict[str, Any]:
    """채널이 루프로 이어 붙일 수 있는지 실제 값으로 판정한다.

    두 가지를 본다.

      값 연속   끝 샘플이 첫 샘플로 돌아오는가. 아니면 이어 붙인 자리에서 튄다.
      기울기 연속  나가는 기울기가 들어오는 기울기와 같은가. 값만 맞고
                기울기가 다르면 그 자리에서 꺾여 보인다.

    허용치는 채널의 값 범위에 대한 **비율**이다. 진폭 100 인 채널과 0.01 인
    채널에 같은 절대값을 들이대면 판정이 무의미해지기 때문이다.

    Args:
        path: CHOP 경로.
        channels: 볼 채널 이름들. 생략하면 전부.
        tolerance: 허용치. 값 범위 대비 비율. 기본 0.01 (1%)
        output_index: 출력이 여러 개인 CHOP 의 출력 번호.
    """
    node = c.require_chop(path)
    tracks = c.pick_tracks(node, channels, output_index)

    results = []
    for track in tracks:
        verdict = c.loop_verdict(c.track_values(track), tolerance)
        verdict["name"] = track.name()
        results.append(verdict)

    failing = [entry["name"] for entry in results if not entry["loops"]]
    return {
        "path": node.path(),
        "tolerance": tolerance,
        "count": len(results),
        "loops": not failing,
        "failing_channels": failing,
        "channels": results,
        "hint": (
            "루프를 맞추려면 cycle CHOP 의 blend 나 shift 로 끝을 첫 값에 붙이세요."
            if failing
            else None
        ),
    }


@tool()
def find_spikes(
    path: str,
    channels: Sequence[str] | None = None,
    threshold: float = c.SPIKE_THRESHOLD,
    max_report: int = 40,
    output_index: int = 0,
) -> dict[str, Any]:
    """채널이 튄 프레임을 찾는다.

    인접 샘플 차이의 중앙값 절대편차(MAD)를 기준으로 본다. 평균·표준편차를
    쓰면 튐 자체가 기준을 끌어올려 스스로를 가려버린다.

    돌려주는 `frames` 는 **값이 뛴 샘플의 프레임**이고, `score` 는 정상 변화량
    대비 몇 배인지다. 시뮬레이션이 한 프레임 터진 자리나, 캐시가 빠진 구간을
    찾는 데 쓴다.

    NaN/inf 는 튐과 별개로 `non_finite` 에 따로 센다.

    Args:
        path: CHOP 경로.
        channels: 볼 채널 이름들. 생략하면 전부.
        threshold: 문턱. 낮출수록 민감해진다. 기본 6.0
        max_report: 채널당 돌려줄 튐 개수 상한.
        output_index: 출력이 여러 개인 CHOP 의 출력 번호.
    """
    if threshold <= 0.0:
        raise ValueError(
            f"threshold 는 0 보다 커야 합니다: {threshold}. "
            f"민감하게 보려면 3.0, 큰 것만 보려면 10.0 정도를 주세요."
        )

    node = c.require_chop(path)
    tracks = c.pick_tracks(node, channels, output_index)
    count = tracks[0].numSamples()
    start, step = c.frame_axis(node, count)

    results = []
    total = 0
    for track in tracks:
        values = c.track_values(track)
        hits, scores = c.spike_indices(values, threshold)
        total += int(hits.size)
        entry: dict[str, Any] = {
            "name": track.name(),
            "count": int(hits.size),
            "spikes": [
                {
                    "frame": c.frame_of(index, start, step),
                    "value": round(float(values[index]), 6),
                    "jump": round(float(values[index] - values[index - 1]), 6),
                    "score": round(float(score), 3),
                }
                for index, score in zip(hits[:max_report], scores[:max_report])
            ],
        }
        non_finite = int((~numpy.isfinite(values)).sum())
        if non_finite:
            entry["non_finite"] = non_finite
        results.append(entry)

    return {
        "path": node.path(),
        "threshold": threshold,
        "frame_range": [start, c.frame_of(max(count - 1, 0), start, step)],
        "total_spikes": total,
        "channels": results,
        "hint": (
            "튄 구간을 고르려면 apply_chop_filter 로 smooth 나 lag 를 거세요."
            if total
            else None
        ),
    }
