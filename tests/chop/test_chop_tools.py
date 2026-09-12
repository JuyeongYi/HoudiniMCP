"""houdini_mcp_chop 회귀 테스트.

hython 을 서브프로세스로 띄워 scenario.py 를 돌리고, **분석 결과가 정답과
맞는지** 검사한다. tests/sop 와 같은 방식이다 — 시스템 python 으로도 돌아간다.

여기서 못 박는 것:

  - 일부러 넣은 튐을 find_spikes 가 그 프레임에서 집어낸다는 것 (오검출 없이)
  - 한 주기 사인파는 루프로 판정하고 난수는 아니라는 것
  - 정지 채널의 정지 구간이 전 구간이라는 것
  - lag 필터가 표준편차를 실제로 줄인다는 것 (제2원칙)
  - 키로 굽고 파일로 오간 값이 원본과 같다는 것
  - 실패 메시지가 다음에 무엇을 할지 알려 준다는 것

실행:
    python -m pytest tests/chop -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "package_order"))

from harness import HoudiniNotFound, find_hfs, hython_path, python_tag  # noqa: E402


def _load_scenario():
    """시나리오를 **고유한 모듈 이름**으로 읽는다.

    팩마다 tests/<팩>/scenario.py 를 두므로 `from scenario import ...` 로 읽으면
    먼저 읽힌 팩의 것이 sys.modules["scenario"] 를 차지하고, 나중에 읽는 팩이
    남의 상수를 받아 간다. pytest 가 tests 전체를 한 프로세스에서 모을 때
    실제로 깨진다 — 경로로 직접 읽어 이름 충돌을 없앤다.
    """
    path = Path(__file__).with_name("scenario.py")
    spec = importlib.util.spec_from_file_location("houdini_mcp_chop_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scenario = _load_scenario()
MARKER = _scenario.MARKER
SPIKE_FRAME = _scenario.SPIKE_FRAME

REPO = Path(__file__).resolve().parents[2]

PACKAGES = ("houdini_mcp", "houdini_mcp_base", "houdini_mcp_chop")
"""PYTHONPATH 에 올릴 패키지들. CHOP 팩은 서버 레지스트리가 있어야 돈다."""

TIMEOUT = 600


def _run_scenario() -> dict:
    hfs = find_hfs()
    tag = python_tag(hfs)

    env = dict(os.environ)
    # Git Bash 의 HOME 이 남아 있으면 pref 디렉토리가 빗나간다(harness 주석 참고).
    env.pop("HOME", None)
    lib_dirs = [str(REPO / name / f"python{tag}libs") for name in PACKAGES]
    existing = env.get("PYTHONPATH")
    if existing:
        lib_dirs.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(lib_dirs)

    proc = subprocess.run(
        [str(hython_path(hfs)), str(Path(__file__).with_name("scenario.py"))],
        env=env,
        capture_output=True,
        text=True,
        # 시나리오가 한국어 에러 메시지를 찍는다. 로케일 기본 코덱(Windows 한국어
        # 환경은 cp949)으로 읽으면 디코딩에서 깨진다.
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
    )
    for line in proc.stdout.splitlines():
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    raise AssertionError(
        f"시나리오가 결과를 내지 않았습니다 (exit {proc.returncode}).\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n{proc.stderr[-4000:]}"
    )


class ChopToolsTest(unittest.TestCase):
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        try:
            find_hfs()
        except HoudiniNotFound as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.result = _run_scenario()

    def test_no_step_failed(self) -> None:
        self.assertEqual(self.result["errors"], {})

    def test_every_module_registers(self) -> None:
        names = set(self.result["registered"])
        # 모듈 하나가 깨지면 register_pack 이 그 모듈만 건너뛰므로, 모듈별로
        # 대표 툴이 하나씩 들어 있는지 본다.
        for expected in (
            "create_chop_network",   # build
            "channel_stats",         # data
            "find_spikes",           # check
            "export_to_keyframes",   # transfer
            "export_channels",       # files
            "bake_channels",         # bake
            "load_audio",            # audio
        ):
            self.assertIn(expected, names)

    def test_every_registered_tool_was_called(self) -> None:
        """등록만 되고 한 번도 불리지 않은 툴이 없어야 한다.

        툴을 추가하고 시나리오에 넣는 것을 잊으면 그 툴은 미검증인 채로
        배포된다. 정적 분석으로는 잡히지 않는 종류의 구멍이라 여기서 막는다.
        """
        self.assertEqual(
            self.result["uncalled"], [],
            "시나리오에서 한 번도 호출되지 않은 툴이 있습니다. "
            "tests/chop/scenario.py 에 호출을 추가하세요.",
        )
        self.assertEqual(
            sorted(self.result["called"]), sorted(self.result["registered"])
        )

    # ---- 분석이 맞는가 ---------------------------------------------------

    def test_find_spikes_catches_the_injected_spike(self) -> None:
        """프레임 60 에 심은 튐을 집어내고, 매끄러운 채널은 건드리지 않는다."""
        channels = {entry["name"]: entry["frames"] for entry in self.result["spikes"]["channels"]}
        ramp = next(frames for name, frames in channels.items() if name.endswith("tx"))
        smooth = next(frames for name, frames in channels.items() if name.endswith("ty"))
        # 값이 뛴 프레임과 되돌아온 프레임 둘 다 잡힌다.
        self.assertEqual(ramp, [float(SPIKE_FRAME), float(SPIKE_FRAME + 1)])
        # 선형 램프의 부동소수점 오차를 튐으로 잡으면 안 된다.
        self.assertEqual(smooth, [])
        self.assertEqual(self.result["spikes"]["total"], 2)

    def test_loop_verdict_separates_cycle_from_noise(self) -> None:
        """한 주기 사인파는 루프, 난수는 루프 아님."""
        sine = self.result["sine_loop"]
        self.assertTrue(sine["loops"])
        self.assertTrue(sine["channel"]["value_continuous"])
        self.assertTrue(sine["channel"]["slope_continuous"])
        self.assertAlmostEqual(sine["channel"]["value_gap"], 0.0, places=9)
        self.assertAlmostEqual(sine["channel"]["slope_gap"], 0.0, places=9)
        self.assertFalse(self.result["noise_loop"])
        self.assertFalse(self.result["noise_stats"]["loops"])

    def test_loop_verdict_catches_a_slope_only_seam(self) -> None:
        """톱니파는 첫 값과 끝 값이 둘 다 0 이라 값만 보면 루프로 보인다.

        하지만 끝에서 1 -> 0 으로 떨어지므로 이어 붙이면 그 자리에서 튄다.
        첫·끝 값만 비교하는 판정이라면 통과시켜 버리는 경우다 — 기울기 항이
        실제로 일하는지를 여기서 못 박는다.
        """
        saw = self.result["saw_loop"]
        self.assertTrue(saw["value_continuous"])
        self.assertFalse(saw["slope_continuous"])
        self.assertFalse(saw["loops"])
        # 천천히 올라가다가 한 번에 떨어진다 — 부호가 반대여야 한다.
        self.assertGreater(saw["slope_in"], 0.0)
        self.assertLess(saw["slope_out"], 0.0)
        self.assertIn("기울기", saw["reason"])

    def test_sine_is_not_a_constant(self) -> None:
        """루프 판정이 상수 채널로 통과해 버리면 시험이 되지 않는다."""
        self.assertGreater(self.result["sine"]["std"], 0.5)
        self.assertEqual(self.result["sine"]["samples"], 121)

    def test_still_ranges_cover_a_constant_channel(self) -> None:
        still = self.result["still"]
        self.assertEqual(still["std"], 0.0)
        self.assertEqual(still["fraction"], 1.0)
        self.assertEqual(len(still["ranges"]), 1)
        self.assertEqual(still["ranges"][0], [1.0, float(still["samples"])])

    def test_lag_filter_reduces_deviation(self) -> None:
        """제2원칙 — 필터가 실제로 무엇을 했는지 툴이 알려 준다."""
        comparison = self.result["lag"]["comparison"][0]
        self.assertEqual(self.result["lag"]["type"], "lag")
        self.assertLess(comparison["std_after"], comparison["std_before"])
        self.assertLess(comparison["std_delta"], 0.0)

    def test_limit_filter_clamps_the_range(self) -> None:
        before = self.result["limit"]["range_before"]
        after = self.result["limit"]["range_after"]
        self.assertLess(before[0], -0.1)
        self.assertGreaterEqual(after[0], -0.1 - 1e-6)
        self.assertLessEqual(after[1], 0.1 + 1e-6)

    def test_create_chop_node_wires_multiple_inputs(self) -> None:
        merge = self.result["merge"]
        self.assertEqual(merge["channel_count"], 2)
        self.assertEqual(sorted(merge["channels"]), ["cycle", "shake"])

    def test_stats_report_sparkline_and_clean_data(self) -> None:
        stats = self.result["noise_stats"]
        self.assertEqual(stats["sparkline_points"], 48)
        self.assertEqual(stats["non_finite"], 0)
        self.assertGreater(stats["std"], 0.0)

    # ---- 벌크 경로와 상한 -------------------------------------------------

    def test_channel_samples_windows_and_caps(self) -> None:
        window = self.result["channel_samples"]
        self.assertFalse(window["downsampled"])
        self.assertEqual(window["returned"], 11)
        self.assertEqual(window["frame_range"], [10.0, 20.0])

        capped = self.result["channel_samples_capped"]
        self.assertTrue(capped["downsampled"])
        self.assertEqual(capped["returned"], 10)
        self.assertEqual(capped["total"], 121)

    def test_network_reports_the_sampling_grid(self) -> None:
        network = self.result["network"]
        self.assertEqual(network["fps"], 24.0)
        self.assertEqual(network["frame_range"], [1.0, 121.0])
        self.assertEqual(network["expected_samples"], 121)
        self.assertEqual(self.result["list_channels"]["frame_step"], 1.0)
        self.assertEqual(self.result["noise"]["samples"], 121)

    # ---- 값이 보존되는가 --------------------------------------------------

    def test_export_to_keyframes_matches_the_source(self) -> None:
        baked = self.result["export_to_keyframes"]
        self.assertTrue(baked["all_match"])
        self.assertEqual(baked["keyframes"], 121)
        self.assertLess(baked["max_error"], 1e-6)

    def test_bake_channels_preserves_expression_values(self) -> None:
        oven = self.result["bake_channels"]
        self.assertTrue(oven["all_match"])
        self.assertEqual(oven["keyframes"], [121, 121])
        self.assertEqual(oven["expressions"], ["$F*0.25", "sin($F*0.2)*30"])
        for error in oven["max_error"]:
            self.assertLess(error, 1e-6)

    def test_import_from_parms_pulls_real_animation(self) -> None:
        """appendClip 경로가 아니면 값이 전부 0 으로 나온다(실측)."""
        grabbed = self.result["import_from_parms"]
        self.assertEqual(grabbed["samples"], 121)
        self.assertEqual(len(grabbed["channels"]), 2)
        self.assertEqual(grabbed["static"], [])

    def test_export_flag_resolves_channel_names_to_parms(self) -> None:
        exported = self.result["set_chop_export"]
        self.assertTrue(exported["export"])
        self.assertEqual(exported["unresolved"], [])
        self.assertIn("/obj/spike_rig/tx", exported["targets"])

    # ---- 파일 포맷 --------------------------------------------------------

    def test_clip_roundtrip_preserves_names_and_values(self) -> None:
        written = self.result["export_channels"]
        reread = self.result["import_channels"]
        self.assertEqual(written["format"], ".bclip")
        self.assertGreater(written["bytes"], 0)
        self.assertEqual(written["channels"], ["cycle"])
        # .clip 은 .chan 과 달리 채널 이름을 보존한다.
        self.assertEqual(reread["channels"], ["cycle"])
        self.assertEqual(reread["samples"], 121)
        self.assertAlmostEqual(reread["first"], 0.0, places=6)

    def test_chan_roundtrip_returns_the_same_values(self) -> None:
        written = self.result["export_parm_channels"]
        read = self.result["import_parm_channels"]
        self.assertEqual(written["format"], ".chan")
        self.assertGreater(written["bytes"], 0)
        self.assertEqual(read["keyframes"], [121, 121])
        self.assertEqual(read["empty"], [])
        self.assertAlmostEqual(read["tx_at_60"], read["source_tx_at_60"], places=6)

    def test_audio_reports_rate_duration_and_envelope(self) -> None:
        audio = self.result["audio"]
        self.assertEqual(audio["sample_rate"], 22050.0)
        self.assertAlmostEqual(audio["duration"], 0.5, places=4)
        self.assertEqual(audio["channel_count"], 1)
        self.assertEqual(audio["envelope_points"], 64)
        self.assertGreater(audio["peak"], 0.5)
        # 앞 절반은 무음, 뒤 절반은 톤. 포락선이 그것을 보여야 한다.
        self.assertEqual(audio["envelope_head"], [0.0, 0.0, 0.0, 0.0])
        for value in audio["envelope_tail"]:
            self.assertGreater(value, 0.5)
        # 오디오 샘플레이트가 씬 FPS 와 달라 resample 안내가 붙어야 한다.
        self.assertTrue(audio["has_hint"])

    # ---- 실패가 다음에 무엇을 할지 알려 주는가 ----------------------------

    def test_not_a_chop_message_says_what_to_do(self) -> None:
        message = self.result["not_a_chop_message"]
        self.assertIn("CHOP 이 아니라", message)
        self.assertIn("create_chop_network", message)

    def test_wrong_format_message_points_at_the_other_tool(self) -> None:
        message = self.result["wrong_format_message"]
        self.assertIn(".bclip", message)
        self.assertIn("export_parm_channels", message)

    def test_filter_messages_list_what_is_usable(self) -> None:
        """쓸 수 없는 값을 주면 쓸 수 있는 값을 알려 줘야 한다."""
        self.assertIn("parms", self.result["no_strength_message"])
        bad = self.result["bad_filter_message"]
        self.assertIn("lag", bad)
        self.assertIn("smooth", bad)


if __name__ == "__main__":
    unittest.main()
