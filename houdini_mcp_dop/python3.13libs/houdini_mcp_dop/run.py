"""시뮬을 실제로 돌려 보고 무슨 일이 일어났는지 돌려주는 툴.

이것이 이 팩의 핵심이다. 기존 구현 다섯 중 어느 것도 시뮬을 돌려 보지 않는다.
만들고 끝내면 터지는지, 몇 초 걸리는지, 메모리를 얼마나 먹는지 모른다.
시뮬은 터지는 게 정상이고, **터졌는지 아는 것이 전부다.**

프레임 진행은 `hou.setFrame` + `dopnet.cook()` 으로 한다.
`hou.DopSimulation.setTime` 은 dopnet 이 소유한 시뮬에서 `hou.PermissionError`
를 낸다(실측). 시뮬은 앞 프레임에 의존하므로 프레임을 건너뛰지 않는다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from ._common import (
    require_dopnet,
    solver_nodes,
)
from ._state import (
    frame_state,
    memory_of,
    run_frames,
)

# 저해상도 시험 주행에서 건드리는 파라미터. 있는 노드에만 건다.
_RESOLUTION_PARMS = ("divsize", "particlesep", "voxelsize")


def _lower_resolution(dopnet: hou.Node, factor: float) -> list[dict[str, Any]]:
    """볼륨·파티클 해상도를 낮춘다. 되돌릴 수 있게 원래 값을 함께 돌려준다.

    divsize 는 복셀 한 변의 길이라 **키우면** 해상도가 낮아진다. 복셀 수는
    세제곱으로 줄어드니 factor 2 면 대략 8분의 1이다.
    """
    changed: list[dict[str, Any]] = []
    for node in dopnet.children():
        if not isinstance(node, hou.DopNode):
            continue
        for parm_name in _RESOLUTION_PARMS:
            parm = node.parm(parm_name)
            if parm is None or parm.isLocked():
                continue
            original = parm.eval()
            if not original:
                continue
            parm.set(original * factor)
            changed.append(
                {
                    "parm": parm.path(),
                    "original": original,
                    "test_value": original * factor,
                }
            )
    return changed


def _restore(changed: list[dict[str, Any]]) -> None:
    for entry in changed:
        parm = hou.parm(entry["parm"])
        if parm is not None:
            parm.set(entry["original"])


def _reset(dopnet: hou.Node) -> int:
    """시뮬 캐시를 버리고 처음으로 돌린다. 버린 바이트를 돌려준다."""
    before = int(dopnet.simulation().memoryUsage())
    dopnet.parm("resimulate").pressButton()
    return before - int(dopnet.simulation().memoryUsage())


@tool()
def step_simulation(
    dopnet: str,
    frames: int = 1,
    deep_fields: bool = False,
    speed_limit: float = 1.0e5,
) -> dict[str, Any]:
    """현재 프레임에서 N 프레임 진행시키고 프레임별 상태를 돌려준다.

    프레임마다 쿡 시간, 메모리, 오브젝트별 요소 수와 월드 위치, 필드 min/max/
    mean, 그리고 발산 징후를 기록한다. 끝나면 원래 프레임으로 돌려놓는다.

    파라미터를 바꾸지 않으므로 사용자가 만든 해상도 그대로 돈다. 무거운 시뮬은
    오래 걸린다 — 먼저 `test_simulation` 으로 저해상도 시험 주행을 하는 편이
    낫다.

    Args:
        dopnet: DOP 네트워크 경로.
        frames: 진행할 프레임 수. 1이면 다음 한 프레임만.
        deep_fields: 필드를 복셀까지 읽어 히스토그램과 NaN 개수를 낼지.
            필드가 크면 느려진다. 기본은 싼 min/max/mean 만.
        speed_limit: 점 속도가 이 값을 넘으면 발산으로 표시한다.
    """
    net = require_dopnet(dopnet)
    if frames < 1:
        raise ValueError(f"frames 는 1 이상이어야 합니다: {frames}. 되감으려면 reset_simulation 을 쓰세요.")

    start = int(hou.frame()) + 1
    end = start + frames - 1
    report = run_frames(net, start, end, deep=deep_fields, speed_limit=speed_limit)

    return {
        "dopnet": net.path(),
        "range": [start, end],
        "returned_to_frame": hou.frame(),
        **report,
    }


@tool()
def test_simulation(
    dopnet: str,
    start: int = 1,
    end: int = 10,
    resolution_factor: float = 2.0,
    substeps: int | None = None,
    deep_fields: bool = False,
    speed_limit: float = 1.0e5,
) -> dict[str, Any]:
    """저해상도로 N 프레임 돌려 보고 프레임별 리포트를 돌려준다.

    셋업이 맞는지 확인하는 데 쓴다. 기존 구현 다섯 중 어디에도 없는 툴이고,
    실제로 가장 쓸모 있다 — 전체 해상도로 200프레임을 돌린 뒤에 소스가 안
    붙어 있었다는 걸 아는 것보다 훨씬 낫다.

    하는 일은 넷이다.

    1. 볼륨·파티클 해상도 파라미터(divsize 등)를 `resolution_factor` 배로
       키운다. 복셀 수는 대략 세제곱으로 준다 — factor 2 면 8분의 1이다.
    2. 시뮬 캐시를 버리고 `start` 프레임부터 `end` 까지 순차로 돌린다.
    3. 프레임마다 쿡 시간, 메모리, 요소 수, 필드 통계, 발산 징후를 기록한다.
    4. 끝나면 **파라미터를 되돌리고 시뮬을 다시 리셋한다.** 저해상도 결과가
       캐시에 남지 않게 하기 위해서다. 프레임도 원래대로 돌린다.

    리포트에서 볼 것: `summary.first_divergence_frame`(처음 터진 프레임),
    `first_error_frame`(처음 에러가 난 프레임), `summary.element_trend`
    (요소 수가 늘고 있는가 — 소스가 먹고 있다는 뜻), `summary.memory_bytes`.

    Args:
        dopnet: DOP 네트워크 경로.
        start: 시작 프레임.
        end: 끝 프레임. start 와 가까울수록 빨리 끝난다.
        resolution_factor: 복셀/파티클 간격을 몇 배로 키울지. 1이면 원래
            해상도 그대로 돈다.
        substeps: 시험 주행 동안 쓸 서브스텝. 생략하면 그대로.
        deep_fields: 필드를 복셀까지 읽을지. 저해상도라 대개 감당된다.
        speed_limit: 점 속도가 이 값을 넘으면 발산으로 표시한다.
    """
    net = require_dopnet(dopnet)
    if end < start:
        raise ValueError(
            f"end({end}) 가 start({start}) 보다 앞섭니다. 시뮬은 앞으로만 돌릴 수 있습니다."
        )
    if resolution_factor <= 0:
        raise ValueError(
            f"resolution_factor 는 양수여야 합니다: {resolution_factor}. "
            "해상도를 반으로 낮추려면 2.0 을 주세요."
        )

    changed: list[dict[str, Any]] = []
    substep_parm = net.parm("substep")
    original_substeps = substep_parm.eval()

    try:
        if resolution_factor != 1.0:
            changed = _lower_resolution(net, resolution_factor)
        if substeps is not None:
            substep_parm.set(substeps)
        _reset(net)
        report = run_frames(
            net, start, end, deep=deep_fields, speed_limit=speed_limit
        )
    finally:
        _restore(changed)
        if substeps is not None:
            substep_parm.set(original_substeps)
        # 저해상도 결과를 캐시에 남기지 않는다. 사용자가 다음에 쿡하면
        # 원래 해상도로 다시 푼다.
        freed = _reset(net)

    summary = report["summary"]
    verdict = _verdict(report)

    return {
        "dopnet": net.path(),
        "range": [start, end],
        "test_settings": {
            "resolution_factor": resolution_factor,
            "lowered_parms": changed,
            "substeps": substeps if substeps is not None else original_substeps,
        },
        "verdict": verdict,
        "cache_freed_bytes": freed,
        "returned_to_frame": hou.frame(),
        **report,
        "next_steps": _next_steps(net, report, summary),
    }


def _verdict(report: dict[str, Any]) -> str:
    """리포트 한 줄 요약. 모델이 먼저 읽는 곳이다. 영어로 쓰지 않는다 —
    이 문자열은 씬에 저장되지 않고 모델에게만 간다."""
    if report["first_error_frame"] is not None:
        return f"프레임 {report['first_error_frame']} 에서 에러가 났습니다."
    diverged = report["summary"].get("first_divergence_frame")
    if diverged is not None:
        return f"프레임 {diverged} 에서 발산 징후가 보입니다."
    if not report["frames"]:
        return "프레임을 하나도 돌리지 못했습니다."
    return "에러 없이 끝났습니다."


def _next_steps(net: hou.Node, report: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    if report["first_error_frame"] is not None:
        steps.append(
            f"에러: {'; '.join(report['first_errors'])[:300]} — "
            f"validate_simulation('{net.path()}') 로 원인을 좁히세요"
        )
    if summary.get("first_divergence_frame") is not None:
        steps.append(
            "발산했습니다. dopnet 의 substep 을 올리거나, 소스 세기를 줄이거나, "
            "솔버의 CFL 조건 파라미터를 확인하세요"
        )
    # 아무것도 일어나지 않은 오브젝트를 찾는다. 움직이지도, 요소 수가 변하지도,
    # 필드가 채워지지도 않았으면 소스나 힘이 안 붙은 것이다.
    trend = summary.get("element_trend", {})
    fields = summary.get("field_trend", {})
    idle = []
    for name, slot in trend.items():
        if slot.get("passive") or slot.get("moved"):
            # 정적 충돌체는 가만히 있는 것이 정상이다.
            continue
        points = slot.get("points")
        if points and points["start"] != points["end"]:
            continue
        if any(key.startswith(f"{name}.") for key in fields):
            continue
        idle.append(name)
    if idle:
        steps.append(
            f"{', '.join(idle)} 에서 아무 일도 일어나지 않았습니다 — 움직이지도, "
            "요소 수가 변하지도, 필드가 채워지지도 않았습니다. 소스나 힘이 "
            "연결돼 있는지 확인하세요"
        )
    if not steps:
        steps.append(
            "셋업이 동작합니다. resolution_factor=1 로 다시 돌려 실제 해상도의 "
            "비용을 재거나, 전체 프레임을 write_sim_cache 로 구우세요"
        )
    return steps


@tool()
@undoable("Reset simulation")
def reset_simulation(dopnet: str, cook_first_frame: bool = True) -> dict[str, Any]:
    """시뮬 캐시를 버리고 처음 상태로 돌린다. 버린 메모리를 돌려준다.

    셋업을 바꾼 뒤에는 반드시 리셋해야 한다. DOP 은 앞 프레임 결과를 캐시에
    들고 있어서, 리셋하지 않으면 바꾼 파라미터가 적용되지 않은 옛 결과를
    계속 보게 된다.

    Args:
        dopnet: DOP 네트워크 경로.
        cook_first_frame: 리셋한 뒤 시작 프레임을 한 번 쿡할지. 켜면 리셋
            직후의 초기 상태를 바로 확인할 수 있다.
    """
    net = require_dopnet(dopnet)
    before = int(net.simulation().memoryUsage())
    original_frame = hou.frame()

    net.parm("resimulate").pressButton()
    after_reset = int(net.simulation().memoryUsage())

    state = None
    if cook_first_frame:
        start_frame = int(net.evalParm("startframe"))
        try:
            hou.setFrame(start_frame)
            net.cook()
            state = frame_state(net)
        finally:
            hou.setFrame(original_frame)

    return {
        "dopnet": net.path(),
        "memory_bytes": {
            "before": before,
            "after": after_reset,
            "freed": before - after_reset,
        },
        "initial_state": state,
        "errors": list(net.errors()),
        "next_steps": [
            f"step_simulation('{net.path()}', 5) 로 다시 진행시켜 보세요",
        ],
    }


@tool()
def sim_memory(dopnet: str, top: int = 15) -> dict[str, Any]:
    """시뮬 메모리를 오브젝트별·서브데이터별로 갈라 준다.

    `hou.DopSimulation.memoryUsage()` 는 총량 하나만 준다. 무엇이 먹고 있는지
    알려면 오브젝트마다 Basic 레코드의 memusage 를 봐야 한다. 파이로에서는
    대개 필드 하나가 전체의 절반을 먹는다.

    Args:
        dopnet: DOP 네트워크 경로.
        top: 가장 큰 서브데이터를 몇 개까지 보여줄지.
    """
    net = require_dopnet(dopnet)
    sim = net.simulation()

    objects = []
    heaviest: list[dict[str, Any]] = []
    for obj in sim.objects():
        own = memory_of(obj)
        children = []
        for key, data in obj.subData().items():
            size = memory_of(data)
            if not size:
                continue
            children.append({"name": key, "data_type": data.dataType(), "bytes": size})
            heaviest.append(
                {"object": obj.name(), "name": key, "data_type": data.dataType(), "bytes": size}
            )
        children.sort(key=lambda entry: entry["bytes"], reverse=True)
        objects.append(
            {
                "name": obj.name(),
                "bytes": own,
                "sub_data_bytes": sum(entry["bytes"] for entry in children),
                "sub_data": children[:top],
            }
        )

    heaviest.sort(key=lambda entry: entry["bytes"], reverse=True)
    objects.sort(key=lambda entry: entry["sub_data_bytes"], reverse=True)

    total = int(sim.memoryUsage())
    return {
        "dopnet": net.path(),
        "frame": hou.frame(),
        "total_bytes": total,
        "total_mb": round(total / (1024 * 1024), 3),
        "cache_max_mb": int(net.evalParm("cachemaxsize")),
        "objects": objects,
        "heaviest": heaviest[:top],
        "solvers": [node.path() for node in solver_nodes(net)],
        "next_steps": [
            "메모리가 상한에 닿으면 dopnet 의 cachemaxsize 를 올리거나 "
            "cachetodisk 를 켜세요",
            f"reset_simulation('{net.path()}') 로 캐시를 비울 수 있습니다",
        ],
    }
