"""오디오를 읽어 **파형을 분석한다.**

기존 구현의 `create_audio_driven` 은 File CHOP 을 만들고 끝냈다. 그러면 모델은
그 파일이 몇 초인지, 샘플레이트가 씬과 맞는지, 소리가 실제로 들어 있는지
모른다. 여기서는 읽은 직후 길이·샘플레이트·채널 수와 함께 **레벨 통계와
포락선**을 준다.

File CHOP 이 `.wav` 를 그대로 읽는 것을 실측했다(44.1kHz 스테레오 → 트랙 2개,
`sampleRate()` 44100.0). 채널 하나당 트랙 하나이고 파일에 이름이 없으면
`chan0`, `chan1`... 로 붙는다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou
import numpy

from houdini_mcp import tool, undoable

from . import _common as c

ENVELOPE_POINTS = 64
"""포락선 점 수. 구간마다 최대 진폭을 하나씩 낸다."""


def _envelope(values: numpy.ndarray, points: int) -> list[float]:
    """구간별 최대 절대값. 오디오는 등간격 추출로는 모양이 남지 않는다.

    44,100 샘플에서 64개를 골라 뽑으면 파형이 아니라 잡음이 나온다. 구간마다
    최대 진폭을 내야 소리가 어디서 큰지가 보인다.
    """
    if values.size == 0:
        return []
    points = max(min(points, values.size), 1)
    usable = values.size - (values.size % points)
    blocks = numpy.abs(values[:usable]).reshape(points, -1)
    return [round(float(v), 6) for v in blocks.max(axis=1)]


@tool()
@undoable("Load audio")
def load_audio(
    parent: str,
    file_path: str,
    comment: str,
    name: str | None = None,
    envelope_points: int = ENVELOPE_POINTS,
    set_audio_flag: bool = False,
) -> dict[str, Any]:
    """오디오 파일을 File CHOP 으로 읽고 파형을 분석해서 돌려준다.

    길이(초)·샘플레이트·채널 수와 함께 채널마다 피크·RMS·클리핑 샘플 수와
    구간별 최대 진폭 포락선을 준다. 포락선의 봉우리가 소리가 큰 지점이므로,
    그 프레임을 골라 애니메이션을 붙이면 된다.

    오디오는 샘플레이트가 씬 FPS 와 다르다. 프레임 단위로 쓰려면
    apply_chop_filter 의 `resample` 로 씬 FPS 에 맞춘 뒤 쓴다 — 돌려주는
    `scene_fps` 와 `sample_rate` 를 비교하면 필요 여부를 알 수 있다.

    Args:
        parent: CHOP 네트워크 경로. create_chop_network 가 돌려준 것.
        file_path: 오디오 파일 경로. .wav 를 확인했다.
        comment: 이 오디오가 무엇인지. 영어로 적는다.
        name: 노드 이름. 생략하면 Houdini 가 정한다.
        envelope_points: 포락선 점 수. 기본 64
        set_audio_flag: True 면 이 CHOP 을 씬의 오디오 소스로 지정한다.
    """
    source = Path(file_path)
    if not source.exists():
        raise ValueError(
            f"그런 파일이 없습니다: {source}. "
            f"경로를 확인하거나 $HIP 을 펼친 절대 경로를 주세요."
        )
    if envelope_points < 1:
        raise ValueError(f"envelope_points 는 1 이상이어야 합니다: {envelope_points}")

    net = c.require_chop_parent(parent)
    node = c.build(net, "file", comment, name, {"file": str(source)})

    tracks = c.cooked_tracks(node)
    if not tracks:
        raise ValueError(
            f"{source} 에서 채널을 읽지 못했습니다. Houdini 22 의 File CHOP 이 "
            f"읽을 수 있는 포맷인지 확인하세요 (.wav 는 확인됨)."
        )

    rate = float(node.sampleRate())
    count = tracks[0].numSamples()
    channels = []
    for track in tracks:
        values = c.track_values(track)
        magnitude = numpy.abs(values)
        peak = float(magnitude.max()) if magnitude.size else 0.0
        channels.append(
            {
                "name": track.name(),
                "samples": int(values.size),
                "peak": peak,
                "rms": float(numpy.sqrt(numpy.mean(values**2))) if values.size else 0.0,
                "clipped_samples": int((magnitude > 1.0).sum()),
                "silent": peak < 1e-6,
                "envelope": _envelope(values, envelope_points),
            }
        )

    if set_audio_flag:
        node.setAudioFlag(True)

    scene_fps = float(hou.fps())
    return {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "file_path": str(source),
        "sample_rate": rate,
        "samples": int(count),
        "duration_seconds": round(count / rate, 6) if rate else None,
        "channel_count": len(channels),
        "channels": channels,
        "scene_fps": scene_fps,
        "audio_flag": node.isAudioFlagSet(),
        "warnings": list(node.warnings()),
        "hint": (
            f"샘플레이트 {rate:g} 가 씬 FPS {scene_fps:g} 와 다릅니다. "
            f"프레임 단위로 쓰려면 apply_chop_filter 의 resample 에 "
            f"strength={scene_fps:g} 를 주세요."
            if rate and abs(rate - scene_fps) > 1e-6
            else None
        ),
    }
