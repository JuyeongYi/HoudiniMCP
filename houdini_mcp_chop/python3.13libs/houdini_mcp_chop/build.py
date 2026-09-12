"""CHOP 네트워크와 노드를 만들고 필터를 건다.

전부 만들고 끝내지 않는다. 반드시 쿡해서 채널 요약을 돌려주고, 필터는 **전후
표준편차를 나란히** 준다. 모델이 "lag 가 실제로 먹었나"를 다시 묻지 않아도
되게 하기 위해서다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Sequence

import hou

from houdini_mcp import tool, undoable

from . import _common as c

# 필터 이름 -> (노드 타입, 강도 파라미터 이름들). 강도 하나로 조절할 수 있게
# 묶어 두고, 세부는 parms 로 덮어쓴다. 실측한 파라미터 이름이다
# (docs/design/packs/chop.md 참고).
FILTERS: dict[str, dict[str, Any]] = {
    "lag": {
        "type": "lag",
        "strength": ("lag1", "lag2"),
        "doc": "값이 목표를 뒤따라오게 한다. strength 는 초 단위 지연이다.",
    },
    "smooth": {
        "type": "filter",
        "strength": ("width",),
        "doc": "이동 평균으로 고른다. strength 는 창 너비(프레임)다.",
    },
    "limit": {
        "type": "limit",
        "strength": (),
        "doc": "값을 min/max 로 자르거나 양자화한다. parms 로 min/max 를 준다.",
    },
    "shift": {
        "type": "shift",
        "strength": ("scroll",),
        "doc": "채널을 시간축으로 민다. strength 는 미는 양이다.",
    },
    "resample": {
        "type": "resample",
        "strength": ("rate",),
        "doc": "샘플레이트를 바꾼다. strength 는 새 rate 다.",
    },
    "spring": {
        "type": "spring",
        "strength": ("springk",),
        "doc": "스프링으로 뒤따라오며 오버슈트한다. strength 는 스프링 상수다.",
    },
    "jiggle": {
        "type": "jiggle",
        "strength": ("stiff",),
        "doc": "2차 진동을 더한다. strength 는 강성이다.",
    },
}
FILTER_NAMES = tuple(FILTERS)


@tool()
@undoable("Create CHOP network")
def create_chop_network(
    parent: str, comment: str, name: str | None = None
) -> dict[str, Any]:
    """CHOP 네트워크(chopnet)를 만든다.

    CHOP 은 아무 데나 만들 수 없다. 먼저 이 네트워크를 만들고, 그 경로를
    create_chop_node 에 준다. 씬의 샘플레이트와 프레임 범위를 함께 돌려주므로
    모델이 채널이 몇 샘플이 될지 미리 알 수 있다.

    이름은 역할이 드러나게 짓는다. `chopnet1` 이 아니라 `camera_shake`,
    `audio_drive` 처럼.

    Args:
        parent: 네트워크를 놓을 부모 경로. 예: /obj
        comment: 이 네트워크가 무엇을 위한 것인지. 영어로 적는다.
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    c.require_comment(comment)
    node = c.require_node(parent)
    try:
        net = node.createNode("chopnet", node_name=name)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{parent} 안에 chopnet 을 만들지 못했습니다. "
            f"/obj 나 geo 오브젝트 안처럼 chopnet 을 담을 수 있는 곳을 주세요. ({exc})"
        ) from exc

    c.set_comment(net, comment)
    try:
        net.moveToGoodPosition()
    except hou.Error:
        pass

    start, end = hou.playbar.frameRange()
    return {
        "path": net.path(),
        "name": net.name(),
        "type": net.type().name(),
        "comment": net.comment(),
        "fps": float(hou.fps()),
        "frame_range": [float(start), float(end)],
        "expected_samples": int(round(end - start)) + 1,
        "hint": "이 경로를 create_chop_node 의 parent 로 주세요.",
    }


@tool()
@undoable("Create CHOP node")
def create_chop_node(
    parent: str,
    node_type: str,
    comment: str,
    name: str | None = None,
    parms: dict[str, Any] | None = None,
    inputs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """CHOP 네트워크 안에 CHOP 을 만들고 쿡해서 채널을 돌려준다.

    자주 쓰는 타입: `noise`(난수), `wave`(사인·사각 등), `constant`(고정값),
    `file`(파일·오디오), `channel`(파라미터), `math`, `merge`, `blend`,
    `trigger`, `beat`. 필터를 걸 것이라면 apply_chop_filter 가 더 낫다.

    이름은 역할이 드러나게 짓는다. `noise1` 이 아니라 `handheld_shake`.

    Args:
        parent: CHOP 네트워크 경로. create_chop_network 가 돌려준 것.
        node_type: CHOP 타입 이름. 예: noise, wave, constant
        comment: 이 노드가 무엇을 하는지. 영어로 적는다.
        name: 노드 이름. 생략하면 Houdini 가 정한다.
        parms: 걸 파라미터. 예: {"channelname": "shake", "amp": 0.4}
        inputs: 입력으로 이을 CHOP 경로들. 순서대로 0번 입력부터.
    """
    net = c.require_chop_parent(parent)
    upstream = [c.require_chop(path) for path in (inputs or ())]
    node = c.build(net, node_type, comment, name, parms, upstream)
    return c.node_report(node)


@tool()
@undoable("Apply CHOP filter")
def apply_chop_filter(
    path: str,
    filter: str,
    comment: str,
    name: str | None = None,
    strength: float | None = None,
    parms: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """CHOP 뒤에 필터를 달고 **전후 통계를 비교해서** 돌려준다.

    lag / smooth / limit / shift / resample / spring / jiggle 을 받는다.
    `smooth` 는 Filter CHOP 이다 — Houdini 에 smooth CHOP 은 없다.

    돌려주는 `comparison` 을 보면 필터가 실제로 무엇을 했는지 알 수 있다.
    고르게 하는 필터는 std 가 줄고, 미는 필터는 std 가 그대로면서 첫 값이
    바뀐다.

    Args:
        path: 필터를 걸 CHOP 경로.
        filter: lag, smooth, limit, shift, resample, spring, jiggle 중 하나.
        comment: 왜 이 필터를 거는지. 영어로 적는다.
        name: 노드 이름. 생략하면 Houdini 가 정한다.
        strength: 필터의 주 파라미터. 생략하면 노드 기본값.
        parms: 세부 파라미터를 직접 덮어쓴다. 예: {"min": 0, "max": 1}
    """
    if filter not in FILTERS:
        lines = "\n".join(
            f"  {key}: {spec['doc']}" for key, spec in FILTERS.items()
        )
        raise ValueError(
            f"filter 는 {', '.join(FILTER_NAMES)} 중 하나여야 합니다: {filter!r}\n{lines}"
        )

    source = c.require_chop(path)
    before = {
        track.name(): c.channel_brief(source, track)
        for track in c.cooked_tracks(source)
    }

    spec = FILTERS[filter]
    settings: dict[str, Any] = {}
    if strength is not None:
        if not spec["strength"]:
            raise ValueError(
                f"{filter} 필터에는 strength 가 없습니다. "
                f"parms 로 직접 주세요. {spec['doc']}"
            )
        settings.update({key: strength for key in spec["strength"]})
    if parms:
        settings.update(parms)

    node = c.build(source.parent(), spec["type"], comment, name, settings, [source])
    report = c.node_report(node)

    comparison = []
    for channel in report["channels"]:
        previous = before.get(channel["name"])
        if previous is None or previous.get("std") is None:
            continue
        comparison.append(
            {
                "name": channel["name"],
                "std_before": previous["std"],
                "std_after": channel["std"],
                "std_delta": (channel["std"] or 0.0) - previous["std"],
                "range_before": [previous["min"], previous["max"]],
                "range_after": [channel["min"], channel["max"]],
                "first_before": previous["first"],
                "first_after": channel["first"],
            }
        )
    report["filter"] = filter
    report["source"] = source.path()
    report["comparison"] = comparison
    return report
