"""팩 전체가 쓰는 헬퍼. 툴은 여기 없다.

네 가지를 모아 뒀다.

1. **노드·트랙·파라미터 해석** — 경로를 받아 CHOP 과 트랙을 꺼낸다. 쿡을
   강제하고, 실패하면 노드 에러를 그대로 전한다.
2. **벌크 샘플 읽기** — `hou.Track.allSamples()` 한 번으로 튜플을 받아 numpy 로
   꽂는다. 실측으로 240샘플에 파이썬 루프의 1/360 이다. 지오메트리와 달리
   바이트 버퍼 경로(`*AsString` 류)는 CHOP 에 없으므로 `numpy.asarray` 가
   유일한 벌크 경로다.
3. **조립과 리포트** — CHOP 을 만들어 잇고, 쿡해서 채널 요약을 돌려준다.
4. **분석** — 이 팩의 존재 이유. 샘플 목록 대신 통계·튐·정지 구간·루프 판정·
   스파크라인을 낸다. 전부 numpy 한두 줄이다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Sequence

import hou
import numpy

SPARKLINE_POINTS = 48
"""스파크라인 기본 점 수. 모델이 읽을 수 있는 선에서 모양이 남는 크기."""

SPIKE_THRESHOLD = 6.0
"""튐 판정 기본 문턱. 인접 샘플 차이의 MAD 대비 몇 배까지 정상으로 볼지."""

LOOP_TOLERANCE = 0.01
"""루프 판정 기본 허용치. 값 범위 대비 비율이다."""

INTERPOLATIONS = ("constant", "linear", "cubic", "bezier", "ease")
"""키에 걸 보간. Houdini 는 보간을 `linear()` 같은 채널 식으로 표현한다.

transfer 와 bake 가 같이 쓴다. 한쪽에 두고 import 하면 모듈 격리가 깨진다 —
register_pack 이 모듈을 하나씩 따로 읽는 이유가 없어진다.
"""


# --------------------------------------------------------------------------
# 노드·트랙·파라미터 해석
# --------------------------------------------------------------------------


def require_node(path: str) -> hou.Node:
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 부모 네트워크 안을 먼저 확인하세요."
        )
    return node


def require_chop(path: str) -> hou.ChopNode:
    """CHOP 노드를 얻는다. 아니면 무엇을 주면 되는지 알려 주고 실패한다."""
    node = require_node(path)
    if not isinstance(node, hou.ChopNode):
        raise ValueError(
            f"{path} 는 CHOP 이 아니라 {node.type().category().name()} 노드입니다. "
            f"CHOP 경로를 주세요. 예: /obj/motion/noise_shake. "
            f"CHOP 네트워크가 아직 없으면 create_chop_network 로 먼저 만드세요."
        )
    return node


def require_chop_parent(path: str) -> hou.Node:
    """CHOP 을 담을 수 있는 네트워크인지 확인한다."""
    node = require_node(path)
    if node.childTypeCategory() != hou.chopNodeTypeCategory():
        raise ValueError(
            f"{path} 안에는 CHOP 을 만들 수 없습니다 "
            f"({node.childTypeCategory().name()} 네트워크입니다). "
            f"create_chop_network 로 CHOP 네트워크를 먼저 만들고 그 경로를 주세요."
        )
    return node


def resolve_parm(ref: str) -> hou.Parm:
    """`/obj/box/tx` 또는 `/obj/box:tx` 형태의 참조를 파라미터로 푼다.

    CHOP 채널 이름이 `node:parm` 꼴을 쓰기 때문에 둘 다 받는다.
    """
    if not ref.startswith("/"):
        raise ValueError(
            f"파라미터 참조는 절대 경로여야 합니다: {ref!r}. "
            f"/obj/box/tx 처럼 노드 경로에 파라미터 이름을 붙여 주세요."
        )
    candidate = ref.rsplit(":", 1)
    path = "/".join(candidate) if len(candidate) == 2 else ref

    parm = hou.parm(path)
    if parm is not None:
        return parm

    tuple_parm = hou.parmTuple(path)
    if tuple_parm is not None:
        components = ", ".join(p.path() for p in tuple_parm)
        raise ValueError(
            f"{ref!r} 는 벡터 파라미터입니다. 성분 경로로 주세요: {components}"
        )

    node_path, _, parm_name = path.rpartition("/")
    node = hou.node(node_path)
    if node is None:
        raise ValueError(
            f"{ref!r} 에서 노드 {node_path!r} 를 찾지 못했습니다. "
            f"find_nodes 로 노드 경로를 먼저 확인하세요."
        )
    names = sorted(p.name() for p in node.parms())
    raise ValueError(
        f"{node_path} 에 파라미터 {parm_name!r} 가 없습니다. "
        f"list_parms 로 확인하세요. 있는 것 일부: {', '.join(names[:12])}"
    )


def cooked_tracks(node: hou.ChopNode, output_index: int = 0) -> tuple[hou.Track, ...]:
    """CHOP 을 쿡해서 트랙을 꺼낸다.

    `tracks()` 는 기본으로 쿡하고, 쿡이 실패하면 예외를 던진다. 여기서 그것을
    노드 에러와 함께 다시 던져 모델이 무엇을 고쳐야 하는지 알게 한다.
    """
    try:
        return tuple(node.tracks(output_index))
    except hou.Error as exc:
        detail = " ".join(node.errors()) or str(exc)
        raise ValueError(
            f"{node.path()} ({node.type().name()}) 쿡에 실패했습니다: {detail} "
            f"파라미터와 입력 연결을 고친 뒤 다시 부르세요."
        ) from exc


def pick_tracks(
    node: hou.ChopNode, channels: Sequence[str] | None, output_index: int = 0
) -> list[hou.Track]:
    """이름으로 트랙을 고른다. 생략하면 전부. 없는 이름은 있는 목록을 알려 준다."""
    tracks = cooked_tracks(node, output_index)
    if not tracks:
        raise ValueError(
            f"{node.path()} 에 채널이 없습니다. 입력이 연결돼 있는지, "
            f"scope 파라미터가 채널을 전부 걸러내지 않는지 확인하세요."
        )
    if channels is None:
        return list(tracks)

    by_name = {track.name(): track for track in tracks}
    picked = []
    for name in channels:
        track = by_name.get(name)
        if track is None:
            raise ValueError(
                f"{node.path()} 에 채널 {name!r} 가 없습니다. "
                f"있는 채널: {', '.join(by_name) or '(없음)'}"
            )
        picked.append(track)
    return picked


def track_values(track: hou.Track) -> numpy.ndarray:
    """트랙의 모든 샘플을 numpy 배열로.

    `allSamples()` 는 파이썬 float 튜플을 준다 — 지오메트리의 `*AsString` 같은
    바이트 버퍼 경로가 CHOP 에는 없다. 그래도 C++ 호출 한 번이라 샘플마다
    `evalAtSample` 을 부르는 것보다 실측 360배 빠르다.
    """
    return numpy.asarray(track.allSamples(), dtype=numpy.float64)


def frame_axis(node: hou.ChopNode, count: int) -> tuple[float, float]:
    """샘플 인덱스를 프레임으로 옮기는 (시작 프레임, 간격).

    `samplesToFrame` 은 선형이므로 두 번만 불러 기울기를 얻는다. 샘플마다
    부르면 그것 자체가 파이썬 루프다.
    """
    start = float(node.samplesToFrame(0))
    if count < 2:
        return start, 1.0
    return start, float(node.samplesToFrame(1)) - start


def frame_of(index: float, start: float, step: float) -> float:
    """샘플 인덱스 하나를 프레임으로."""
    return round(float(start + index * step), 6)


def frames_of(indices: numpy.ndarray, start: float, step: float) -> list[float]:
    """샘플 인덱스 배열을 프레임 목록으로."""
    return [frame_of(index, start, step) for index in indices]


# --------------------------------------------------------------------------
# 조립과 리포트
# --------------------------------------------------------------------------


def require_comment(comment: str) -> None:
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 노드가 무엇을 위한 것인지 영어로 적어 주세요. "
            "Lag camera shake, 0.2s attack 처럼 구체적으로."
        )


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def set_parms(node: hou.Node, parms: dict[str, Any]) -> None:
    """값이 None 인 것은 건너뛴다. 벡터는 parmTuple 로 건다."""
    for name, value in parms.items():
        if value is None:
            continue
        parm = node.parm(name)
        if parm is not None:
            parm.set(value)
            continue
        tuple_parm = node.parmTuple(name)
        if tuple_parm is None:
            raise ValueError(
                f"{node.type().name()} 에 파라미터 {name!r} 가 없습니다. "
                f"list_parms 로 이 노드의 파라미터 이름을 확인하세요."
            )
        tuple_parm.set(tuple(value))


def build(
    parent: hou.Node,
    node_type: str,
    comment: str,
    name: str | None = None,
    parms: dict[str, Any] | None = None,
    inputs: Sequence[hou.ChopNode] = (),
) -> hou.ChopNode:
    """CHOP 네트워크 안에 노드를 만들어 잇는다.

    코멘트를 달고 네트워크 뷰에 보이게 하며, 디스플레이 플래그를 새 노드로
    옮긴다. 새 노드가 체인의 끝이 되기 때문이다. CHOP 에는 렌더 플래그가 없다.
    """
    require_comment(comment)
    try:
        node = parent.createNode(node_type, node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent.path()} 안에 {node_type!r} CHOP 을 만들지 못했습니다. "
            f"list_node_types 로 CHOP 카테고리에 있는 타입인지 확인하세요. ({exc})"
        ) from exc

    for index, upstream in enumerate(inputs):
        node.setInput(index, upstream)

    set_comment(node, comment)
    if parms:
        set_parms(node, parms)

    try:
        node.moveToGoodPosition()
    except hou.Error:
        # 배치는 결과에 영향이 없다. 실패해도 툴을 실패시키지 않는다.
        pass
    node.setDisplayFlag(True)
    return node


def channel_brief(node: hou.ChopNode, track: hou.Track) -> dict[str, Any]:
    """채널 한 줄 요약. 목록에 실을 만큼만 — 전체 분석은 channel_stats 다."""
    values = track_values(track)
    brief: dict[str, Any] = {"name": track.name(), "samples": int(values.size)}
    if values.size:
        finite = values[numpy.isfinite(values)]
        brief.update(
            {
                "first": float(values[0]),
                "last": float(values[-1]),
                "min": float(finite.min()) if finite.size else None,
                "max": float(finite.max()) if finite.size else None,
                "std": float(finite.std()) if finite.size else None,
            }
        )
        if finite.size != values.size:
            brief["non_finite"] = int(values.size - finite.size)
    return brief


def node_report(
    node: hou.ChopNode, extra: dict[str, Any] | None = None, output_index: int = 0
) -> dict[str, Any]:
    """만든 노드를 쿡해서 채널 요약과 함께 돌려준다.

    조작 툴이 `{"ok": true}` 대신 돌려주는 것이 이것이다. 모델이 필터가 실제로
    먹었는지 std 를 보고 알 수 있어야 한다.
    """
    tracks = cooked_tracks(node, output_index)
    count = tracks[0].numSamples() if tracks else 0
    start, step = frame_axis(node, count)
    return {
        "path": node.path(),
        "name": node.name(),
        "type": node.type().name(),
        "comment": node.comment(),
        "sample_rate": float(node.sampleRate()),
        "samples": int(count),
        "frame_range": [start, round(start + max(count - 1, 0) * step, 6)],
        "channel_count": len(tracks),
        "channels": [channel_brief(node, track) for track in tracks],
        "warnings": list(node.warnings()),
        **(extra or {}),
    }


# --------------------------------------------------------------------------
# 분석 — 이 팩의 존재 이유
# --------------------------------------------------------------------------


def sparkline(values: numpy.ndarray, points: int = SPARKLINE_POINTS) -> list[float]:
    """등간격으로 추린 배열. 모양만 남기고 크기를 줄인다."""
    if values.size <= points:
        return [round(float(v), 6) for v in values]
    index = numpy.linspace(0, values.size - 1, points).round().astype(numpy.int64)
    return [round(float(v), 6) for v in values[index]]


def spike_indices(
    values: numpy.ndarray, threshold: float = SPIKE_THRESHOLD
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """튄 샘플의 인덱스와 그 점수.

    인접 샘플 차이의 중앙값 절대편차(MAD)를 기준으로 본다. 평균·표준편차를
    쓰면 튐 자체가 기준을 끌어올려 스스로를 가려버린다. 상수에 가까운 채널은
    MAD 가 0 이 되므로 평균 편차로 떨어진다.

    기준에는 **바닥을 깔아야 한다.** 선형에 가까운 채널은 MAD 가 부동소수점
    오차 수준(1e-17)까지 내려가고, 그러면 아무 의미 없는 마지막 자리 오차가
    전부 튐으로 잡힌다 — 실측으로 확인한 오검출이다. 신호 크기의 1e-9 보다
    작은 변화는 수치적으로 의미가 없으므로 거기서 끊는다.

    차이 j 가 크면 샘플 j+1 에서 값이 뛴 것이다. 그래서 인덱스를 하나 민다.
    """
    if values.size < 3:
        return numpy.empty(0, dtype=numpy.int64), numpy.empty(0)

    diff = numpy.diff(values)
    deviation = numpy.abs(diff - numpy.median(diff))
    mad = 1.4826 * float(numpy.median(deviation))
    # MAD 가 정확히 0 이면(절반 이상이 같은 간격) 평균 편차로 떨어진다. 평균은
    # 튐 자체에 끌려 올라가므로 최후의 수단으로만 쓴다.
    floor = 1e-9 * max(float(numpy.abs(values).max()), 1.0)
    scale = max(mad if mad > 0.0 else float(deviation.mean()), floor)

    score = deviation / scale
    hits = numpy.flatnonzero(score > threshold)
    return hits + 1, score[hits]


def still_runs(
    values: numpy.ndarray, tolerance: float, min_length: int = 3
) -> list[tuple[int, int]]:
    """변화가 허용치 이하인 연속 구간의 (시작, 끝) 샘플 인덱스.

    `numpy.diff` 로 낸 불리언 배열의 경계만 찾는다. 파이썬으로 샘플을 훑지
    않는다.
    """
    if values.size < 2:
        return []
    flat = numpy.abs(numpy.diff(values)) <= tolerance
    if not flat.any():
        return []

    # 경계에 0 을 덧대면 상승/하강 엣지가 구간의 시작과 끝이 된다.
    padded = numpy.concatenate(([False], flat, [False]))
    edges = numpy.flatnonzero(padded[1:] != padded[:-1])
    runs = []
    for begin, end in zip(edges[0::2], edges[1::2]):
        # diff 인덱스 begin..end-1 이 평평하다 = 샘플 begin..end 가 같은 값이다.
        if end - begin + 1 >= min_length:
            runs.append((int(begin), int(end)))
    return runs


def loop_verdict(
    values: numpy.ndarray, tolerance: float = LOOP_TOLERANCE
) -> dict[str, Any]:
    """루프가 되는지 실제 값으로 판정한다.

    두 가지를 본다. 값이 제자리로 돌아오는가(위치 연속), 그리고 들어오는
    기울기와 나가는 기울기가 같은가(속도 연속). 값만 맞고 기울기가 다르면
    이어 붙인 자리에서 꺾여 보인다.

    허용치는 값 범위에 대한 비율이다. 진폭이 100 인 채널과 0.01 인 채널에
    같은 절대값을 들이대면 한쪽은 언제나 통과하고 한쪽은 언제나 실패한다.
    """
    if values.size < 3:
        return {
            "loops": False,
            "reason": "샘플이 3개 미만이라 판정할 수 없습니다.",
        }

    finite = values[numpy.isfinite(values)]
    if finite.size != values.size:
        return {
            "loops": False,
            "reason": f"NaN/inf 샘플이 {values.size - finite.size}개 있습니다. "
            f"find_spikes 로 위치를 확인하세요.",
        }

    span = float(values.max() - values.min())
    scale = span if span > 0.0 else max(abs(float(values[0])), 1.0)

    value_gap = float(abs(values[-1] - values[0]))
    slope_in = float(values[1] - values[0])
    slope_out = float(values[-1] - values[-2])
    slope_gap = abs(slope_out - slope_in)

    value_ratio = value_gap / scale
    slope_ratio = slope_gap / scale
    value_ok = value_ratio <= tolerance
    slope_ok = slope_ratio <= tolerance

    reasons = []
    if not value_ok:
        reasons.append(
            f"끝 값이 첫 값과 {value_gap:.6g} 만큼 다릅니다 "
            f"(값 범위의 {value_ratio * 100:.2f}%)"
        )
    if not slope_ok:
        reasons.append(
            f"들어오는 기울기 {slope_in:.6g} 와 나가는 기울기 {slope_out:.6g} 가 "
            f"다릅니다 (값 범위의 {slope_ratio * 100:.2f}%)"
        )

    return {
        "loops": value_ok and slope_ok,
        "value_continuous": value_ok,
        "slope_continuous": slope_ok,
        "first": float(values[0]),
        "last": float(values[-1]),
        "value_gap": value_gap,
        "value_gap_ratio": value_ratio,
        "slope_in": slope_in,
        "slope_out": slope_out,
        "slope_gap": slope_gap,
        "slope_gap_ratio": slope_ratio,
        "tolerance": tolerance,
        "reason": "; ".join(reasons)
        or "첫 샘플과 끝 샘플이 값과 기울기 모두 이어집니다.",
    }


def analyze(
    values: numpy.ndarray,
    start_frame: float,
    frame_step: float,
    *,
    spike_threshold: float = SPIKE_THRESHOLD,
    still_tolerance: float | None = None,
    still_min_frames: int = 3,
    loop_tolerance: float = LOOP_TOLERANCE,
    sparkline_points: int = SPARKLINE_POINTS,
) -> dict[str, Any]:
    """채널 하나의 전체 분석. 샘플 목록은 돌려주지 않는다."""
    count = int(values.size)
    result: dict[str, Any] = {"samples": count}
    if count == 0:
        result["reason"] = "샘플이 없습니다. 입력과 프레임 범위를 확인하세요."
        return result

    finite_mask = numpy.isfinite(values)
    non_finite = int(count - int(finite_mask.sum()))
    result["non_finite"] = {
        "count": non_finite,
        "nan": int(numpy.isnan(values).sum()),
        "inf": int(numpy.isinf(values).sum()),
        "frames": frames_of(
            numpy.flatnonzero(~finite_mask)[:20], start_frame, frame_step
        ),
    }

    finite = values[finite_mask]
    if finite.size == 0:
        result["reason"] = "모든 샘플이 NaN/inf 입니다. 상류 노드를 확인하세요."
        return result

    # NaN 을 끼워 넣고 nanargmin 으로 찾으면 비유한 샘플을 건너뛴 위치가 나온다.
    safe = numpy.where(finite_mask, values, numpy.nan)
    quantiles = numpy.quantile(finite, [0.05, 0.5, 0.95])
    result["stats"] = {
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": float(finite.mean()),
        "std": float(finite.std()),
        "range": float(finite.max() - finite.min()),
        "p05": float(quantiles[0]),
        "median": float(quantiles[1]),
        "p95": float(quantiles[2]),
        "min_frame": frame_of(int(numpy.nanargmin(safe)), start_frame, frame_step),
        "max_frame": frame_of(int(numpy.nanargmax(safe)), start_frame, frame_step),
    }
    result["first"] = float(values[0])
    result["last"] = float(values[-1])
    result["total_change"] = float(values[-1] - values[0])
    result["path_length"] = float(numpy.abs(numpy.diff(finite)).sum())

    hits, scores = spike_indices(values, spike_threshold)
    result["spikes"] = {
        "count": int(hits.size),
        "threshold": spike_threshold,
        "frames": frames_of(hits[:20], start_frame, frame_step),
        "scores": [round(float(s), 3) for s in scores[:20]],
    }

    span = float(finite.max() - finite.min())
    tolerance = (
        still_tolerance
        if still_tolerance is not None
        else max(span * 1e-4, 1e-12)
    )
    runs = still_runs(values, tolerance, max(int(still_min_frames), 2))
    still_samples = sum(end - begin + 1 for begin, end in runs)
    result["still"] = {
        "tolerance": tolerance,
        "range_count": len(runs),
        "sample_fraction": round(still_samples / count, 6),
        "ranges": [
            [
                frame_of(begin, start_frame, frame_step),
                frame_of(end, start_frame, frame_step),
            ]
            for begin, end in runs[:20]
        ],
    }

    result["loop"] = loop_verdict(values, loop_tolerance)
    result["sparkline"] = sparkline(values, sparkline_points)
    return result
