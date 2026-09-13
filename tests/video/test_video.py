"""houdini_mcp_base.video 회귀 테스트.

hython 을 서브프로세스로 띄워 scenario.py 를 돌리고 결과를 검사한다.
외부 ffmpeg(FFMPEG_BIN_PATH)이 없으면 건너뛴다.

실행:
    python -m pytest tests/video -q
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
    """scenario.py 를 이 테스트 전용 이름으로 읽는다(tests/paths 의 주석 참고)."""
    path = Path(__file__).with_name("scenario.py")
    spec = importlib.util.spec_from_file_location("houdini_mcp_video_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MARKER = _load_scenario().MARKER

REPO = Path(__file__).resolve().parents[2]

PACKAGES = ("houdini_mcp", "houdini_mcp_base")

TIMEOUT = 600


def _run_scenario() -> dict:
    hfs = find_hfs()
    tag = python_tag(hfs)

    env = dict(os.environ)
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


class VideoTest(unittest.TestCase):
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        if not os.environ.get("FFMPEG_BIN_PATH"):
            raise unittest.SkipTest("FFMPEG_BIN_PATH 가 없어 영상 테스트를 건너뜁니다.")
        try:
            data = _run_scenario()
        except HoudiniNotFound as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.result = data["results"]
        cls.errors = data["errors"]

    def test_no_check_raised(self) -> None:
        self.assertEqual(self.errors, {})

    def test_sequence_fills_missing_frame(self) -> None:
        """빠진 5번 프레임을 앞 프레임으로 채워 12프레임이 그대로 나온다."""
        entry = self.result["sequence_video"]
        self.assertEqual(entry["video"]["frames"], 12)
        self.assertEqual((entry["video"]["width"], entry["video"]["height"]), (320, 180))
        self.assertEqual(entry["source"]["missing_frames"], "5")
        self.assertIn("warnings", entry)

    def test_korean_label_uses_font(self) -> None:
        """한글 라벨은 폰트 파일 없이 그리면 네모가 되므로 폰트를 찾아 쓴다."""
        self.assertIn("font", self.result["sequence_video"])

    def test_video_source_relabel(self) -> None:
        """영상 파일 소스, webm 인코더, 콜론·따옴표·% 가 든 라벨."""
        entry = self.result["video_source"]
        self.assertEqual(entry["video"]["codec"], "vp9")
        self.assertEqual(entry["video"]["frames"], 12)

    def test_compare_horizontal_scales_to_smaller_height(self) -> None:
        """높이 180 과 360 을 작은 쪽 180 에 맞춰 나란히 붙인다. 길이가 다르면 경고."""
        entry = self.result["compare_horizontal"]
        self.assertEqual((entry["video"]["width"], entry["video"]["height"]), (640, 180))
        # start/end 없이 주면 있는 파일만 쓴다. EXR 은 5번이 빠진 11장이 긴 쪽이다.
        # 빠진 프레임을 채우는 것은 start/end 를 준 sequence_video 가 확인한다.
        self.assertEqual(entry["video"]["frames"], 11)
        self.assertTrue(any("길이" in w for w in entry["warnings"]))

    def test_compare_vertical_size(self) -> None:
        entry = self.result["compare_vertical"]
        self.assertEqual(entry["video"]["width"], 300)
        # 320x180 과 640x360 을 너비 300 에 맞추면 둘 다 168.75 -> 짝수 168.
        self.assertEqual(entry["video"]["height"], 168 + 168)
        self.assertEqual(entry["video"]["frames"], 12)

    def test_refuses_overwrite(self) -> None:
        self.assertIn("overwrite=True", self.result["overwrite_error"])

    def test_bad_extension(self) -> None:
        self.assertIn(".mp4", self.result["extension_error"])

    def test_not_sequence(self) -> None:
        self.assertIn("프레임 토큰", self.result["not_sequence_error"])

    def test_missing_env_exits_early(self) -> None:
        """FFMPEG_BIN_PATH 가 없으면 설정 방법을 알리고 아무것도 쓰지 않는다."""
        self.assertIn("FFMPEG_BIN_PATH", self.result["missing_env_error"])
        self.assertFalse(self.result["missing_env_wrote"])


if __name__ == "__main__":
    unittest.main()
