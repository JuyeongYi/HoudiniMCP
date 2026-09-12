"""파라미터의 식을 키프레임으로 굽고, **구운 값이 원래와 같은지 검증한다.**

base 의 `set_expression` / `set_keyframe` 은 하나씩 건다. 여기는 이미 걸린
식을 프레임마다 평가해 키로 굳히는 일괄 작업이고, 굽기 전후 값을 맞춰 보는
것이 본질이다. 굽고 나서 애니메이션이 달라져 있으면 아무 의미가 없다.

식 평가에는 벌크 경로가 없다 — `hou.Parm` 은 프레임 범위를 한 번에 주는
메서드를 갖고 있지 않다. 그래서 여기만은 프레임 루프를 돈다. 대신 키를 거는
것은 `setKeyframes` 한 번이고, 검증도 numpy 로 한 번에 비교한다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Sequence

import hou
import numpy

from houdini_mcp import tool, undoable

from . import _common as c

MAX_BAKE_FRAMES = 20000
"""한 번에 구울 수 있는 프레임 수 상한. 넘으면 무엇을 해야 하는지 알려 준다."""


@tool()
@undoable("Bake parameters to keyframes")
def bake_channels(
    parms: Sequence[str],
    start_frame: float | None = None,
    end_frame: float | None = None,
    step: float = 1.0,
    interpolation: str = "linear",
    keep_expression: bool = False,
) -> dict[str, Any]:
    """파라미터에 걸린 식을 키프레임으로 굽는다. 값이 보존됐는지 확인해서 준다.

    식은 씬의 다른 부분에 묶여 있다. 참조하는 노드를 지우거나 다른 씬으로
    가져가면 깨진다. 구워 두면 값만 남아 독립적이 된다.

    돌려주는 `verified.max_error` 가 굽기 전후의 최대 차이다. step 을 1 보다
    크게 주면 그만큼 커진다 — 곡선이 심하면 step 을 1 로 두거나 보간을
    바꾼다.

    Args:
        parms: 구울 파라미터 경로들. 예: ["/obj/cam/tx", "/obj/cam/rz"]
        start_frame: 시작 프레임. 생략하면 씬의 전역 시작.
        end_frame: 끝 프레임(포함). 생략하면 씬의 전역 끝.
        step: 키 간격(프레임). 1 이면 매 프레임.
        interpolation: constant / linear / cubic / bezier / ease. 기본 linear.
        keep_expression: True 면 식을 지우지 않고 키만 더한다. 보통 False 다.
    """
    if interpolation not in c.INTERPOLATIONS:
        raise ValueError(
            f"interpolation 은 {', '.join(c.INTERPOLATIONS)} 중 하나여야 합니다: "
            f"{interpolation!r}"
        )
    if step <= 0.0:
        raise ValueError(f"step 은 0 보다 커야 합니다: {step}")
    if not parms:
        raise ValueError(
            "parms 가 비어 있습니다. 구울 파라미터 경로를 주세요. "
            "list_animated_parms 가 식이 걸린 파라미터를 알려 줍니다."
        )

    playback = hou.playbar.frameRange()
    first = float(playback[0]) if start_frame is None else float(start_frame)
    last = float(playback[1]) if end_frame is None else float(end_frame)
    if last < first:
        raise ValueError(
            f"end_frame({last}) 이 start_frame({first}) 보다 앞입니다. 순서를 바꾸세요."
        )

    frames = numpy.arange(first, last + step * 0.5, step, dtype=numpy.float64)
    if frames.size > MAX_BAKE_FRAMES:
        raise ValueError(
            f"프레임이 {frames.size}개라 한 번에 구울 수 없습니다(상한 "
            f"{MAX_BAKE_FRAMES}). 구간을 나누거나 step 을 키우세요."
        )

    results = []
    for reference in parms:
        parm = c.resolve_parm(reference)
        expression = None
        try:
            expression = parm.expression()
        except hou.OperationFailed:
            pass

        # 식 평가에는 벌크 경로가 없다. 이 루프가 유일한 방법이다.
        before = numpy.array(
            [parm.evalAtFrame(float(frame)) for frame in frames], dtype=numpy.float64
        )

        keys = []
        for frame, value in zip(frames, before):
            key = hou.Keyframe()
            key.setFrame(float(frame))
            key.setValue(float(value))
            key.setExpression(f"{interpolation}()", hou.exprLanguage.Hscript)
            keys.append(key)

        try:
            if not keep_expression:
                parm.deleteAllKeyframes()
            parm.setKeyframes(keys)
        except hou.PermissionError as exc:
            raise ValueError(
                f"{parm.path()} 에 키를 걸 수 없습니다: {exc} "
                f"파라미터 잠금(lock_parm)이나 HDA 잠금을 먼저 푸세요."
            ) from exc

        after = numpy.array(
            [parm.evalAtFrame(float(frame)) for frame in frames], dtype=numpy.float64
        )
        error = numpy.abs(after - before)
        worst = int(numpy.argmax(error)) if error.size else 0
        results.append(
            {
                "parm": parm.path(),
                "expression_before": expression,
                "keyframes": len(parm.keyframes()),
                "frame_range": [first, last],
                "step": step,
                "verified": {
                    "max_error": round(float(error.max()) if error.size else 0.0, 9),
                    "worst_frame": float(frames[worst]) if frames.size else None,
                    "matches": bool(error.size and error.max() < 1e-6),
                },
                "value_range": [float(before.min()), float(before.max())],
            }
        )

    mismatched = [entry["parm"] for entry in results if not entry["verified"]["matches"]]
    return {
        "count": len(results),
        "frame_range": [first, last],
        "step": step,
        "interpolation": interpolation,
        "baked": results,
        "all_match": not mismatched,
        "mismatched_parms": mismatched,
        "hint": (
            "구운 값이 원래 식과 다릅니다. step 을 1 로 줄이거나 "
            "interpolation 을 linear 로 바꾸세요."
            if mismatched
            else None
        ),
    }
