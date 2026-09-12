"""CHOP 과 파라미터 사이를 오간다.

세 경로가 있고, 셋 다 필요하다.

1. **키프레임으로 굽기** (`export_to_keyframes`) — 트랙 샘플을 읽어 파라미터에
   키로 박는다. CHOP 과 끊어진 사본이라 CHOP 을 지워도 애니메이션이 남는다.
2. **익스포트 플래그** (`set_chop_export`) — CHOP 이 파라미터를 계속 몬다.
   살아 있는 연결이라 CHOP 을 고치면 바로 반영된다.
3. **파라미터 끌어오기** (`import_from_parms`) — 이미 애니메이션된 파라미터를
   CHOP 채널로 가져온다. 여기서부터 필터를 걸고 분석한다.

채널 이름을 손으로 `name<i>` 에 써 넣으면 값이 전부 0 으로 나온다(실측).
`hou.Parm.appendClip` 이 올바른 경로이고, SideFX 자신의 choptoolutils 도
그것을 쓴다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from typing import Any, Sequence

import hou
import numpy

from houdini_mcp import tool, undoable

from . import _common as c

VERIFY_SAMPLES = 16
"""구운 뒤 CHOP 값과 파라미터 값을 몇 지점에서 맞춰 보는지."""


def channel_parm_path(node: hou.ChopNode, name: str) -> str:
    """CHOP 채널 이름을 파라미터 경로로 푼다. 익스포트 규칙과 같은 꼴을 받는다.

    실측한 규칙은 `/obj/box/tx`, `box:tx`, `box/tx` 셋 다 먹고 `tx` 는 안
    먹는다는 것이다. 상대 이름은 **CHOP 네트워크의 부모**를 기준으로 푼다 —
    /obj/shake_net/lag1 의 `box:tx` 는 /obj/box/tx 다.
    """
    reference = name.replace(":", "/")
    if reference.startswith("/"):
        return reference
    base = node.parent().parent()
    root = "" if base is None or base.path() == "/" else base.path()
    return f"{root}/{reference}"


@tool()
@undoable("Bake CHOP to keyframes")
def export_to_keyframes(
    path: str,
    targets: dict[str, str] | None = None,
    channels: Sequence[str] | None = None,
    interpolation: str = "linear",
    output_index: int = 0,
) -> dict[str, Any]:
    """CHOP 채널을 파라미터 키프레임으로 굽는다. **값이 맞는지 검증해서** 돌려준다.

    익스포트 플래그와 달리 CHOP 과 끊어진 사본이 된다. CHOP 네트워크를 지워도
    애니메이션이 남고, 사람이 키를 손으로 고칠 수 있다.

    채널 이름이 이미 파라미터를 가리키면(`/obj/box/tx`, `box:tx`) targets 를
    생략해도 된다. 아니면 채널 이름 -> 파라미터 경로로 짚어 준다.

    돌려주는 `verified` 를 보면 구운 결과가 원본과 맞는지 알 수 있다.
    `max_error` 가 0 에 가깝지 않으면 보간이 원본을 따라가지 못한 것이다 —
    linear 로 바꾸거나 샘플레이트를 올린다.

    Args:
        path: CHOP 경로.
        targets: 채널 이름 -> 파라미터 경로. 예: {"shake": "/obj/cam/tx"}
        channels: 구울 채널 이름들. 생략하면 전부(또는 targets 의 키).
        interpolation: constant / linear / cubic / bezier / ease. 기본 linear.
        output_index: 출력이 여러 개인 CHOP 의 출력 번호.
    """
    if interpolation not in c.INTERPOLATIONS:
        raise ValueError(
            f"interpolation 은 {', '.join(c.INTERPOLATIONS)} 중 하나여야 합니다: "
            f"{interpolation!r}"
        )

    node = c.require_chop(path)
    wanted = list(targets) if (targets and channels is None) else channels
    tracks = c.pick_tracks(node, wanted, output_index)
    start, step = c.frame_axis(node, tracks[0].numSamples())

    baked = []
    for track in tracks:
        reference = (targets or {}).get(track.name()) or channel_parm_path(
            node, track.name()
        )
        parm = c.resolve_parm(reference)
        values = c.track_values(track)
        if values.size == 0:
            raise ValueError(
                f"채널 {track.name()!r} 에 샘플이 없습니다. "
                f"list_channels 로 CHOP 이 실제로 값을 내는지 확인하세요."
            )

        keys = []
        for index in range(values.size):
            key = hou.Keyframe()
            key.setFrame(c.frame_of(index, start, step))
            key.setValue(float(values[index]))
            key.setExpression(f"{interpolation}()", hou.exprLanguage.Hscript)
            keys.append(key)

        try:
            parm.deleteAllKeyframes()
            # setKeyframes 는 한 번의 업데이트로 전체를 건다. setKeyframe 을
            # 샘플마다 부르는 것보다 빠르다고 HOM 문서가 명시한다.
            parm.setKeyframes(keys)
        except hou.PermissionError as exc:
            raise ValueError(
                f"{parm.path()} 에 키를 걸 수 없습니다: {exc} "
                f"파라미터 잠금(lock_parm)이나 HDA 잠금을 먼저 푸세요."
            ) from exc

        # 구운 값이 원본과 맞는지 몇 지점에서 확인한다. 전 샘플을 다시 평가하면
        # 그것 자체가 파이썬 루프라 검증이 굽기보다 비싸진다.
        probe = numpy.linspace(0, values.size - 1, min(VERIFY_SAMPLES, values.size))
        probe = probe.round().astype(numpy.int64)
        errors = [
            abs(parm.evalAtFrame(c.frame_of(index, start, step)) - float(values[index]))
            for index in probe
        ]
        baked.append(
            {
                "channel": track.name(),
                "parm": parm.path(),
                "keyframes": len(parm.keyframes()),
                "frame_range": [
                    c.frame_of(0, start, step),
                    c.frame_of(values.size - 1, start, step),
                ],
                "verified": {
                    "probes": len(errors),
                    "max_error": round(max(errors), 9),
                    "matches": max(errors) < 1e-6,
                },
            }
        )

    mismatched = [entry["channel"] for entry in baked if not entry["verified"]["matches"]]
    return {
        "path": node.path(),
        "interpolation": interpolation,
        "count": len(baked),
        "baked": baked,
        "all_match": not mismatched,
        "mismatched_channels": mismatched,
        "hint": (
            "구운 값이 원본과 다릅니다. interpolation 을 linear 로 바꾸거나 "
            "resample 필터로 샘플레이트를 올리세요."
            if mismatched
            else None
        ),
    }


@tool()
@undoable("Import parameters into CHOP")
def import_from_parms(
    parent: str,
    parms: Sequence[str],
    comment: str,
    name: str | None = None,
) -> dict[str, Any]:
    """애니메이션된 파라미터를 Channel CHOP 으로 가져온다.

    이미 키가 찍힌 파라미터를 CHOP 으로 끌어와야 필터를 걸거나 분석할 수 있다.
    `hou.Parm.appendClip` 을 쓴다 — Channel CHOP 의 채널 이름만 손으로 채우면
    값이 전부 0 으로 나온다(실측).

    가져온 뒤 channel_stats 로 분석하거나 apply_chop_filter 로 고른다.

    Args:
        parent: CHOP 네트워크 경로. create_chop_network 가 돌려준 것.
        parms: 가져올 파라미터 경로들. 예: ["/obj/cam/tx", "/obj/cam/ty"]
        comment: 무엇을 가져오는지. 영어로 적는다.
        name: 노드 이름. 생략하면 Houdini 가 정한다.
    """
    if not parms:
        raise ValueError(
            "parms 가 비어 있습니다. 가져올 파라미터 경로를 주세요. "
            "어느 파라미터에 애니메이션이 있는지는 list_animated_parms 가 알려 줍니다."
        )

    net = c.require_chop_parent(parent)
    resolved = [c.resolve_parm(ref) for ref in parms]
    node = c.build(net, "channel", comment, name)

    # Channel CHOP 은 만들자마자 기본 채널 하나를 갖고 있다. appendClip 이
    # 그 뒤에 붙으므로 미리 비운다.
    node.parm("numchannels").set(0)
    for parm in resolved:
        try:
            parm.appendClip(node, False, False)
        except hou.Error as exc:
            raise ValueError(
                f"{parm.path()} 를 CHOP 으로 가져오지 못했습니다: {exc} "
                f"문자열이나 메뉴 파라미터는 채널이 될 수 없습니다."
            ) from exc

    report = c.node_report(node)
    report["imported"] = [parm.path() for parm in resolved]
    report["static_channels"] = [
        channel["name"]
        for channel in report["channels"]
        if channel.get("std") == 0.0
    ]
    if report["static_channels"]:
        report["hint"] = (
            "값이 변하지 않는 채널이 있습니다. 그 파라미터에는 애니메이션이 "
            "없습니다 — list_animated_parms 로 확인하세요."
        )
    return report


@tool()
@undoable("Set CHOP export")
def set_chop_export(path: str, enable: bool = True) -> dict[str, Any]:
    """CHOP 의 익스포트 플래그를 켜고 끈다. 파라미터를 **살아 있는 채로** 몬다.

    키로 굽는 것(export_to_keyframes)과 달리 CHOP 을 고치면 파라미터가 바로
    따라온다. 대신 CHOP 네트워크를 지우면 애니메이션도 사라진다.

    채널 이름이 어느 파라미터를 가리키는지가 전부다. 실측한 규칙:

        tx                  안 먹는다 — 어느 노드인지 모른다
        camera:tx           먹는다
        camera/tx           먹는다
        /obj/camera/tx      먹는다

    켠 뒤 실제로 값이 실렸는지 `targets` 로 확인해 준다. `resolved: false` 인
    채널은 이름이 파라미터를 가리키지 못한 것이다.

    Args:
        path: CHOP 경로.
        enable: True 면 켜고 False 면 끈다.
    """
    node = c.require_chop(path)
    tracks = c.cooked_tracks(node)
    node.setExportFlag(bool(enable))

    targets = []
    unresolved = []
    for track in tracks:
        reference = channel_parm_path(node, track.name())
        parm = hou.parm(reference)
        if parm is None:
            unresolved.append(track.name())
            targets.append({"channel": track.name(), "resolved": False})
            continue
        targets.append(
            {
                "channel": track.name(),
                "resolved": True,
                "parm": parm.path(),
                "value": parm.eval(),
            }
        )

    return {
        "path": node.path(),
        "export": node.isExportFlagSet(),
        "count": len(targets),
        "targets": targets,
        "unresolved_channels": unresolved,
        "hint": (
            "이름이 파라미터를 가리키지 못하는 채널이 있습니다. rename CHOP 으로 "
            "/obj/노드/파라미터 꼴로 바꾸세요."
            if unresolved and enable
            else None
        ),
    }
