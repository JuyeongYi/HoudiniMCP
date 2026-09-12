"""houdini_mcp_chop 회귀 시나리오. hython 안에서 돈다.

시스템 python 에서 직접 import 할 수 없으므로(`hou` 가 없다) 테스트는 이 파일을
hython 서브프로세스로 띄우고, 마지막에 찍는 JSON 한 줄을 읽어 검사한다.
tests/sop 가 쓰는 방식과 같다.

여기서 확인하는 것은 "노드를 만들었다"가 아니라 **분석이 맞는가**다. 정답을
아는 신호를 만들어 넣는다.

  - 프레임 60 에 일부러 튐을 넣은 채널 -> find_spikes 가 프레임 60 을 집는가
    (선형 램프의 부동소수점 오차는 튐으로 잡지 않는가)
  - 정확히 한 주기인 사인파 -> check_loop 가 루프 가능 판정을 내리는가
  - 톱니파 -> 첫·끝 값은 같지만 기울기가 끊기므로 루프 불가 판정을 내리는가
  - 난수 채널 -> 루프 불가 판정을 내리는가
  - constant CHOP -> 정지 구간이 전 구간인가
  - lag 필터 -> 표준편차가 줄어드는가 / limit 필터 -> 범위가 잘리는가
  - 키로 굽고 채널 파일로 오간 값이 원본과 같은가

**등록된 툴을 하나도 빠짐없이 호출한다.** 호출되지 않은 툴은 `uncalled` 로
보고되고 테스트가 실패한다. 툴을 추가하고 시나리오에 넣는 것을 잊으면, 그 툴은
미검증인 채로 조용히 배포된다 — 그것을 막으려는 것이다.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import traceback
import wave
from pathlib import Path

MARKER = "CHOPTEST_JSON:"
"""이 접두사가 붙은 줄 하나만 테스트가 읽는다. Houdini 자체 출력과 섞이기 때문."""

FIRST, LAST = 1, 121
"""검증용 프레임 범위. 121 샘플이라 24fps 에서 5초 주기가 정확히 한 번 돈다."""

SPIKE_FRAME = 60
"""일부러 튐을 넣는 프레임. find_spikes 가 이 번호를 집어내야 한다."""


def make_wav(path: Path, seconds: float = 0.5, rate: int = 22050) -> None:
    """검증용 사인 톤. 앞 절반은 무음이라 포락선에 봉우리가 하나 선다."""
    count = int(rate * seconds)
    frames = b"".join(
        struct.pack(
            "<h",
            0 if index < count // 2 else int(20000 * math.sin(2 * math.pi * 440 * index / rate)),
        )
        for index in range(count)
    )
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)


def main() -> int:
    import hou

    from houdini_mcp import get_registry
    from houdini_mcp.pack import register_pack

    registered = set(register_pack("houdini_mcp_chop"))
    call = {spec.name: spec.fn for spec in get_registry().all()}

    called: set[str] = set()
    errors: dict[str, str] = {}

    def run(tool_name: str, **kwargs):
        """툴 하나를 부르고 호출 여부를 기록한다.

        툴들이 스스로 `name` 인자를 쓰므로 여기 파라미터는 tool_name 이어야 한다.
        """
        try:
            result = call[tool_name](**kwargs)
        except Exception as exc:  # 어느 툴이 왜 깨졌는지 테스트가 알아야 한다.
            errors[tool_name] = f"{type(exc).__name__}: {exc}"
            return None
        called.add(tool_name)
        return result

    hou.playbar.setFrameRange(FIRST, LAST)
    hou.playbar.setPlaybackRange(FIRST, LAST)

    out: dict[str, object] = {"registered": sorted(registered)}
    tmp = Path(tempfile.mkdtemp())

    # --- 네트워크 ---------------------------------------------------------
    net = run(
        "create_chop_network",
        parent="/obj",
        comment="Regression CHOP network",
        name="regression_chops",
    )
    out["network"] = {
        "fps": net["fps"],
        "frame_range": net["frame_range"],
        "expected_samples": net["expected_samples"],
    }
    net_path = net["path"]

    # --- 난수 채널: 루프가 아니어야 한다 ----------------------------------
    noise = run(
        "create_chop_node",
        parent=net_path,
        node_type="noise",
        comment="Handheld camera shake",
        name="handheld_shake",
        parms={"channelname": "shake", "amp": 0.5},
    )
    out["noise"] = {
        "samples": noise["samples"],
        "channels": [ch["name"] for ch in noise["channels"]],
        "sample_rate": noise["sample_rate"],
    }

    listed = run("list_channels", path=noise["path"])
    out["list_channels"] = {
        "count": listed["count"],
        "frame_range": listed["frame_range"],
        "frame_step": listed["frame_step"],
    }

    stats = run("channel_stats", path=noise["path"])
    shake = stats["channels"][0]
    out["noise_stats"] = {
        "std": shake["stats"]["std"],
        "sparkline_points": len(shake["sparkline"]),
        "non_finite": shake["non_finite"]["count"],
        "loops": shake["loop"]["loops"],
    }

    window = run(
        "channel_samples",
        path=noise["path"],
        channel="shake",
        start_frame=10,
        end_frame=20,
    )
    out["channel_samples"] = {
        "returned": window["returned"],
        "downsampled": window["downsampled"],
        "frame_range": window["frame_range"],
    }
    capped = run("channel_samples", path=noise["path"], channel="shake", max_points=10)
    out["channel_samples_capped"] = {
        "returned": capped["returned"],
        "downsampled": capped["downsampled"],
        "total": capped["total_samples"],
    }

    lagged = run(
        "apply_chop_filter",
        path=noise["path"],
        filter="lag",
        comment="Soften handheld shake",
        name="lag_shake",
        strength=0.3,
    )
    out["lag"] = {
        "type": lagged["type"],
        "comparison": lagged["comparison"],
    }

    out["noise_loop"] = run("check_loop", path=noise["path"])["loops"]

    # limit 필터는 값을 잘라야 한다. 자른 뒤 범위가 실제로 좁아지는가.
    clamped = run(
        "apply_chop_filter",
        path=noise["path"],
        filter="limit",
        comment="Clamp shake to a safe range",
        name="clamp_shake",
        parms={"type": 1, "min": -0.1, "max": 0.1},
    )
    out["limit"] = {
        "range_before": clamped["comparison"][0]["range_before"],
        "range_after": clamped["comparison"][0]["range_after"],
    }

    # strength 가 없는 필터에 strength 를 주면 무엇을 하라고 알려 줘야 한다.
    try:
        call["apply_chop_filter"](
            path=noise["path"], filter="limit", comment="bad", strength=1.0
        )
        out["no_strength_message"] = ""
    except Exception as exc:
        out["no_strength_message"] = str(exc)
    try:
        call["apply_chop_filter"](path=noise["path"], filter="smoooth", comment="bad")
        out["bad_filter_message"] = ""
    except Exception as exc:
        out["bad_filter_message"] = str(exc)

    # --- 정확히 한 주기인 사인파: 루프여야 한다 ---------------------------
    # 121 샘플, 24fps -> 5.0초. period 5 면 첫 샘플과 끝 샘플이 같은 위상이다.
    sine = run(
        "create_chop_node",
        parent=net_path,
        node_type="wave",
        comment="One full cycle for loop check",
        name="loop_cycle",
        parms={"channelname": "cycle", "wavetype": 1, "period": 5.0, "amp": 1.0},
    )
    out["sine"] = {"samples": sine["samples"], "std": sine["channels"][0]["std"]}
    sine_loop = run("check_loop", path=sine["path"])
    out["sine_loop"] = {
        "loops": sine_loop["loops"],
        "channel": sine_loop["channels"][0],
    }

    # 톱니파는 첫 값과 끝 값이 둘 다 0 이라 **값만 보면 루프처럼 보인다.**
    # 하지만 끝에서 1 -> 0 으로 떨어지므로 이어 붙이면 그 자리에서 튄다.
    # 기울기 항이 실제로 일하는지 여기서 갈린다.
    # (삼각파는 Houdini 에서 0 -> 1 -> -1 -> 0 이라 진짜로 이어진다 — 실측)
    saw = run(
        "create_chop_node",
        parent=net_path,
        node_type="wave",
        comment="Sawtooth that pops at the seam",
        name="sawtooth_seam",
        parms={"channelname": "seam", "wavetype": 4, "period": 5.0, "amp": 1.0},
    )
    out["saw_loop"] = run("check_loop", path=saw["path"])["channels"][0]

    # --- 정지 채널: 전 구간이 정지여야 한다 -------------------------------
    still = run(
        "create_chop_node",
        parent=net_path,
        node_type="constant",
        comment="Flat reference channel",
        name="flat_reference",
        # constant CHOP 은 기본이 샘플 하나다. single 을 꺼야 전 구간이 나온다.
        parms={"value0": 2.5, "single": 0},
    )
    still_stats = run("channel_stats", path=still["path"])
    out["still"] = {
        "samples": still_stats["channels"][0]["samples"],
        "std": still_stats["channels"][0]["stats"]["std"],
        "fraction": still_stats["channels"][0]["still"]["sample_fraction"],
        "ranges": still_stats["channels"][0]["still"]["ranges"],
    }

    # --- 입력 여러 개: merge 로 두 채널을 합친다 ---------------------------
    merged = run(
        "create_chop_node",
        parent=net_path,
        node_type="merge",
        comment="Combine shake and cycle",
        name="combine_motion",
        inputs=[noise["path"], sine["path"]],
    )
    out["merge"] = {
        "channels": [ch["name"] for ch in merged["channels"]],
        "channel_count": merged["channel_count"],
    }

    # --- 일부러 넣은 튐: find_spikes 가 그 프레임을 집어야 한다 ------------
    rig = hou.node("/obj").createNode("geo", node_name="spike_rig")
    ramp = rig.parm("tx")
    keys = []
    for frame in range(FIRST, LAST + 1):
        key = hou.Keyframe()
        key.setFrame(float(frame))
        key.setValue(50.0 if frame == SPIKE_FRAME else frame * 0.1)
        key.setExpression("linear()", hou.exprLanguage.Hscript)
        keys.append(key)
    ramp.setKeyframes(keys)
    rig.parm("ty").setExpression("sin($F*4)*2")

    grabbed = run(
        "import_from_parms",
        parent=net_path,
        parms=["/obj/spike_rig/tx", "/obj/spike_rig/ty"],
        comment="Pull rig animation for analysis",
        name="grab_rig_anim",
    )
    out["import_from_parms"] = {
        "channels": [ch["name"] for ch in grabbed["channels"]],
        "samples": grabbed["samples"],
        "static": grabbed["static_channels"],
    }

    spikes = run("find_spikes", path=grabbed["path"])
    out["spikes"] = {
        "total": spikes["total_spikes"],
        "channels": [
            {"name": ch["name"], "frames": [s["frame"] for s in ch["spikes"]]}
            for ch in spikes["channels"]
        ],
    }

    # --- CHOP -> 파라미터 -------------------------------------------------
    target = hou.node("/obj").createNode("geo", node_name="bake_target")
    baked = run(
        "export_to_keyframes",
        path=sine["path"],
        targets={"cycle": "/obj/bake_target/ty"},
    )
    out["export_to_keyframes"] = {
        "count": baked["count"],
        "all_match": baked["all_match"],
        "keyframes": baked["baked"][0]["keyframes"],
        "max_error": baked["baked"][0]["verified"]["max_error"],
    }

    exported = run("set_chop_export", path=grabbed["path"], enable=True)
    out["set_chop_export"] = {
        "export": exported["export"],
        "unresolved": exported["unresolved_channels"],
        "targets": [t["parm"] for t in exported["targets"] if t["resolved"]],
    }
    run("set_chop_export", path=grabbed["path"], enable=False)

    # --- 파라미터의 식을 키로 굽기 ----------------------------------------
    drift = hou.node("/obj").createNode("geo", node_name="drift_box")
    drift.parm("tx").setExpression("$F*0.25")
    drift.parm("rz").setExpression("sin($F*0.2)*30")
    oven = run(
        "bake_channels",
        parms=["/obj/drift_box/tx", "/obj/drift_box/rz"],
        start_frame=FIRST,
        end_frame=LAST,
    )
    out["bake_channels"] = {
        "all_match": oven["all_match"],
        "keyframes": [entry["keyframes"] for entry in oven["baked"]],
        "max_error": [entry["verified"]["max_error"] for entry in oven["baked"]],
        "expressions": [entry["expression_before"] for entry in oven["baked"]],
    }

    # --- 파일 입출력 ------------------------------------------------------
    clip_file = tmp / "cycle.bclip"
    written = run("export_channels", path=sine["path"], file_path=str(clip_file))
    out["export_channels"] = {
        "format": written["format"],
        "bytes": written["bytes"],
        "channels": written["channels"],
    }

    reread = run(
        "import_channels",
        parent=net_path,
        file_path=str(clip_file),
        comment="Read the cycle clip back",
        name="reread_cycle",
    )
    out["import_channels"] = {
        "channels": [ch["name"] for ch in reread["channels"]],
        "samples": reread["samples"],
        "first": reread["channels"][0]["first"],
    }

    chan_file = tmp / "rig.chan"
    parm_written = run(
        "export_parm_channels",
        parms=["/obj/drift_box/tx", "/obj/drift_box/rz"],
        file_path=str(chan_file),
        start_frame=FIRST,
        end_frame=LAST,
    )
    out["export_parm_channels"] = {
        "format": parm_written["format"],
        "bytes": parm_written["bytes"],
        "columns": parm_written["columns"],
    }

    sink = hou.node("/obj").createNode("geo", node_name="chan_sink")
    parm_read = run(
        "import_parm_channels",
        parms=["/obj/chan_sink/tx", "/obj/chan_sink/rz"],
        file_path=str(chan_file),
        start_frame=FIRST,
        end_frame=LAST,
    )
    out["import_parm_channels"] = {
        "keyframes": [entry["keyframes"] for entry in parm_read["loaded"]],
        "empty": parm_read["empty_parms"],
        "tx_at_60": sink.parm("tx").evalAtFrame(60),
        "source_tx_at_60": drift.parm("tx").evalAtFrame(60),
    }

    # --- 오디오 ------------------------------------------------------------
    wav = tmp / "tone.wav"
    make_wav(wav)
    audio = run(
        "load_audio",
        parent=net_path,
        file_path=str(wav),
        comment="Drive animation from tone",
        name="tone_source",
    )
    out["audio"] = {
        "sample_rate": audio["sample_rate"],
        "duration": audio["duration_seconds"],
        "channel_count": audio["channel_count"],
        "peak": audio["channels"][0]["peak"],
        "envelope_points": len(audio["channels"][0]["envelope"]),
        "envelope_head": audio["channels"][0]["envelope"][:4],
        "envelope_tail": audio["channels"][0]["envelope"][-4:],
        "has_hint": audio["hint"] is not None,
    }

    # --- 실패 메시지가 다음에 무엇을 할지 알려 주는지 ----------------------
    try:
        call["list_channels"](path="/obj/spike_rig")
        out["not_a_chop_message"] = ""
    except Exception as exc:
        out["not_a_chop_message"] = str(exc)
    try:
        call["export_channels"](path=sine["path"], file_path=str(tmp / "x.chan"))
        out["wrong_format_message"] = ""
    except Exception as exc:
        out["wrong_format_message"] = str(exc)

    out["called"] = sorted(called)
    out["uncalled"] = sorted(registered - called)
    out["errors"] = errors
    print(MARKER + json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
