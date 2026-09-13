"""houdini_mcp_sop 회귀 테스트.

hython 을 서브프로세스로 띄워 scenario.py 를 돌리고, 쿡한 결과가 기대한 값인지
검사한다. tests/package_order 와 같은 방식이다 — 시스템 python 으로도 돌아간다.

여기서 못 박는 것:

  - 노드 타입 해석 (bevel -> polybevel::3.0, lathe -> revolve::2.0)
  - 조작 툴이 전후 통계를 돌려주는 것 (제2원칙)
  - numpy 벌크 통계 경로가 실제 값을 낸다는 것 (제3원칙)
  - UVProject 가 바운딩 박스에 맞춰져 UV 가 0~1 에 들어온다는 것
  - 실패 메시지가 다음에 무엇을 할지 알려 준다는 것

실행:
    python -m pytest tests/sop -q
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
    """scenario.py 를 이 테스트 전용 이름으로 읽는다.

    팩마다 tests/<팩>/scenario.py 를 두므로 `from scenario import ...` 로 읽으면
    먼저 읽힌 쪽이 sys.modules["scenario"] 를 차지하고, 나중에 읽는 쪽이 남의
    MARKER 를 쓰게 된다. 이 파일이 두 번 당했다 - 한 번은 rig
    테스트가, 한 번은 paths 테스트가 먼저 수집되며 17개가 통째로 깨졌다.
    """
    path = Path(__file__).with_name("scenario.py")
    spec = importlib.util.spec_from_file_location("houdini_mcp_sop_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MARKER = _load_scenario().MARKER

REPO = Path(__file__).resolve().parents[2]

PACKAGES = ("houdini_mcp", "houdini_mcp_base", "houdini_mcp_sop")
"""PYTHONPATH 에 올릴 패키지들. SOP 팩은 base 와 서버 레지스트리가 있어야 돈다."""

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


class SopToolsTest(unittest.TestCase):
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
            "create_primitive",   # create
            "bevel",              # polyedit
            "triangulate",        # topology
            "attrib_stats",       # attribs
            "create_group",       # groups
            "uv_project",         # uv
            "nearest_point",      # query
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
            "tests/sop/scenario.py 에 호출을 추가하세요.",
        )
        self.assertEqual(
            sorted(self.result["called"]), sorted(self.result["registered"])
        )

    def test_copy_to_points_reports_both_inputs(self) -> None:
        """copy_to_points 가 report() 를 거쳐 전후와 입력 개수를 함께 준다."""
        copied = self.result["copy_to_points"]
        self.assertIn("source", copied["inputs"])
        self.assertIn("target", copied["inputs"])
        expected = (copied["inputs"]["source"]["prims"]
                    * copied["inputs"]["target"]["points"])
        self.assertEqual(copied["after"]["prims"], expected)

    def test_boolean_reports_open_edges(self) -> None:
        """닫힌 메시 둘이면 양쪽 열린 에지가 0 이어야 한다."""
        self.assertEqual(self.result["boolean_open_edges"], {"a": 0, "b": 0})

    def test_volume_info_reads_vdb(self) -> None:
        self.assertEqual(self.result["volume"]["count"], 1)
        self.assertTrue(self.result["volume"]["is_sdf"])

    def test_export_attribute_writes_numpy_shape(self) -> None:
        exported = self.result["export_attribute"]
        self.assertEqual(exported["shape"][1], 3)
        self.assertEqual(exported["dtype"], "float32")

    def test_box_is_eight_points(self) -> None:
        self.assertEqual(self.result["box"]["points"], 8)
        self.assertEqual(self.result["box"]["prims"], 6)

    def test_bevel_resolves_to_polybevel_and_adds_geometry(self) -> None:
        bevel = self.result["bevel"]
        self.assertTrue(bevel["type"].startswith("polybevel"))
        self.assertEqual(bevel["before"]["points"], 8)
        self.assertGreater(bevel["after"]["points"], bevel["before"]["points"])
        self.assertGreater(bevel["after"]["prims"], bevel["before"]["prims"])

    def test_uv_project_fits_unit_square(self) -> None:
        uv = self.result["uv"]
        self.assertEqual(uv["owner"], "vertex")
        self.assertEqual(uv["outside_unit_square"]["count"], 0)
        self.assertAlmostEqual(uv["bbox"]["min"][0], 0.0, places=5)
        self.assertAlmostEqual(uv["bbox"]["max"][0], 1.0, places=5)

    def test_attrib_stats_reads_bulk_values(self) -> None:
        stats = self.result["stats"]
        self.assertEqual(stats["size"], 3)
        self.assertEqual(stats["count"], self.result["bevel"]["after"]["points"])
        # 상자는 원점 중심 2x2x2 를 Y 로 1 올린 것이라 X 는 -1~1 이다.
        self.assertAlmostEqual(stats["components"][0]["min"], -1.0, places=5)
        self.assertAlmostEqual(stats["components"][0]["max"], 1.0, places=5)

    def test_group_reports_member_count(self) -> None:
        group = self.result["group"]
        self.assertEqual(group["type"], "prim")
        self.assertGreaterEqual(group["count"], 1)

    def test_triangulate_splits_quads(self) -> None:
        self.assertEqual(self.result["triangulate"], 12)

    def test_curve_is_built_from_points(self) -> None:
        self.assertEqual(self.result["curve"]["points"], 3)
        self.assertEqual(self.result["curve"]["prims"], 1)

    def test_revolve_replaces_lathe(self) -> None:
        self.assertGreater(self.result["revolve"]["prims"], 1)

    def test_nearest_point_uses_acceleration(self) -> None:
        self.assertEqual(self.result["nearest"]["found"], 3)
        self.assertGreater(self.result["nearest"]["first_distance"], 0.0)

    def test_edge_group_failure_says_what_to_do(self) -> None:
        message = self.result["edge_group_message"]
        self.assertIn("p0-1", message)
        self.assertIn("create_group", message)


if __name__ == "__main__":
    unittest.main()
