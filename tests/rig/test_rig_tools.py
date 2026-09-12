"""houdini_mcp_rig 회귀 테스트.

hython 을 서브프로세스로 띄워 scenario.py 를 돌리고, 쿡한 결과가 기대한 값인지
검사한다. tests/sop 과 같은 방식이다 — 시스템 python 으로도 돌아간다.

여기서 못 박는 것:

  - 스켈레톤을 코드로 만들 수 있다는 것 (Skeleton SOP 은 뷰포트 전용이다)
  - 계층을 parent_idx 로도, 폴리라인으로도 같은 값으로 읽는다는 것
  - boneCapture 의 인터리브 레이아웃 해석 (index, weight, index, weight, ...)
  - 조인트를 돌리면 자손과 스킨이 실제로 따라온다는 것
  - APEX 그래프가 지오메트리이고, 코드로 디컴파일된다는 것
  - **일부러 망가뜨린 리그를 validate_rig 가 실제로 잡는다는 것** — 이게 핵심이다.
    검증 툴이 아무것도 못 잡으면 없느니만 못하다.

실행:
    python -m pytest tests/rig -q
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
    """시나리오 모듈을 팩 전용 이름으로 읽는다.

    팩마다 tests/<팩>/scenario.py 를 두므로 `from scenario import ...` 로 읽으면
    먼저 읽힌 팩의 것이 sys.modules["scenario"] 를 차지하고, 나중에 읽는 팩이
    남의 MARKER 를 쓰게 된다. 실제로 밟았다 — sop 테스트 17개가 통째로 깨졌다.
    """
    path = Path(__file__).with_name("scenario.py")
    spec = importlib.util.spec_from_file_location("houdini_mcp_rig_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MARKER = _load_scenario().MARKER

REPO = Path(__file__).resolve().parents[2]

PACKAGES = ("houdini_mcp", "houdini_mcp_base", "houdini_mcp_rig")
"""PYTHONPATH 에 올릴 패키지들. 팩은 서버 레지스트리가 있어야 등록된다."""

TIMEOUT = 900


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


class RigToolsTest(unittest.TestCase):
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        try:
            find_hfs()
        except HoudiniNotFound as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.result = _run_scenario()

    # ---- 등록과 호출 -----------------------------------------------------

    def test_no_step_failed(self) -> None:
        self.assertEqual(self.result["errors"], {})

    def test_every_module_registers(self) -> None:
        names = set(self.result["registered"])
        # 모듈 하나가 깨지면 register_pack 이 그 모듈만 건너뛰므로, 모듈별로
        # 대표 툴이 하나씩 들어 있는지 본다.
        for expected in (
            "create_skeleton",   # skeleton
            "capture_skin",      # skin
            "apex_graph_info",   # apexgraph
            "validate_rig",      # check
        ):
            self.assertIn(expected, names)

    def test_every_registered_tool_was_called(self) -> None:
        """등록만 되고 한 번도 불리지 않은 툴이 없어야 한다."""
        self.assertEqual(
            self.result["uncalled"], [],
            "시나리오에서 한 번도 호출되지 않은 툴이 있습니다. "
            "tests/rig/scenario.py 에 호출을 추가하세요.",
        )
        self.assertEqual(
            sorted(self.result["called"]), sorted(self.result["registered"])
        )

    # ---- 스켈레톤 --------------------------------------------------------

    def test_skeleton_is_built_as_points_and_polylines(self) -> None:
        info = self.result["skeleton_info"]
        self.assertEqual(info["joints"], 3)
        self.assertEqual(info["bones"], 2)
        self.assertEqual(info["roots"], ["hips"])
        self.assertEqual(info["leaves"], ["chest"])
        self.assertEqual(info["max_depth"], 2)
        self.assertTrue(info["has_transform"])
        self.assertAlmostEqual(info["bone_length"]["total"], 2.0, places=5)

    def test_hierarchy_reads_from_parent_idx(self) -> None:
        """rigdoctor 를 거친 스켈레톤은 parent_idx 로 읽는다."""
        self.assertEqual(self.result["skeleton_info"]["hierarchy_source"], "parent_idx")
        joints = {j["name"]: j for j in self.result["list_joints"]["joints"]}
        self.assertIsNone(joints["hips"]["parent"])
        self.assertEqual(joints["spine"]["parent"], "hips")
        self.assertEqual(joints["chest"]["parent"], "spine")

    def test_hierarchy_falls_back_to_polylines(self) -> None:
        """parent_idx 가 없는 날 스켈레톤도 같은 계층으로 읽힌다.

        폴리라인 유도 경로가 rigdoctor 와 다른 답을 내면 리그 검증이 통째로
        틀어진다. validate_rig 가 루트를 하나로 읽는지로 확인한다.
        """
        raw = self.result["validate_raw"]
        self.assertEqual(raw["hierarchy_source"], "polyline prims")
        self.assertNotIn("multiple_roots", raw["checks"])

    def test_joint_info_gives_chain_and_children(self) -> None:
        joint = self.result["joint_info"]
        self.assertEqual(joint["parent"], "hips")
        self.assertEqual(joint["children"], ["chest"])
        self.assertEqual(joint["chain_to_root"], ["hips", "spine"])
        self.assertEqual(joint["descendants"], 1)
        self.assertAlmostEqual(joint["bone_length"], 1.0, places=5)
        self.assertAlmostEqual(joint["determinant"], 1.0, places=5)

    def test_joint_attributes_reports_kinefx_schema(self) -> None:
        names = self.result["joint_attributes"]["names"]
        for expected in ("P", "name", "transform", "parent_idx"):
            self.assertIn(expected, names)

    # ---- 스킨 ------------------------------------------------------------

    def test_capture_normalizes_weights_to_one(self) -> None:
        weights = self.result["capture_skin"]["weights"]
        self.assertEqual(weights["sum"]["not_one"], 0)
        self.assertAlmostEqual(weights["sum"]["min"], 1.0, places=4)
        self.assertAlmostEqual(weights["sum"]["max"], 1.0, places=4)
        self.assertEqual(weights["unweighted_points"], 0)
        self.assertEqual(self.result["capture_skin"]["captured_joints"], 3)

    def test_max_influences_is_respected(self) -> None:
        """max_influences=2 로 캡처했으니 어느 점도 3개 이상 붙지 않는다."""
        influences = self.result["weight_stats"]["weights"]["influences_per_point"]
        self.assertEqual(influences["max"], 2)
        self.assertEqual(self.result["capture_skin"]["max_influences"], 2)

    def test_per_joint_totals_add_up_to_point_count(self) -> None:
        """조인트별 웨이트 합계를 모두 더하면 점 수와 같다 (합이 전부 1이므로)."""
        stats = self.result["weight_stats"]
        total = sum(j["total_weight"] for j in stats["top_joints"])
        self.assertAlmostEqual(total, stats["points"], places=2)

    def test_joint_influence_stays_inside_mesh(self) -> None:
        influence = self.result["joint_influence"]
        self.assertGreater(influence["points"], 0)
        self.assertLessEqual(influence["weight"]["max"], 1.0)

    # ---- 포즈와 디폼 -----------------------------------------------------

    def test_posing_a_joint_moves_its_descendants_only(self) -> None:
        posed = self.result["pose_joints"]
        self.assertEqual(posed["applied"][0]["affected_joints"], 2)  # spine + chest
        self.assertEqual(posed["moved_joints"], 1)  # spine 은 피벗이라 제자리
        self.assertEqual(posed["joints_moved_most"][0]["name"], "chest")
        self.assertGreater(posed["max_joint_move"], 0.5)

    def test_compare_poses_measures_the_rotation(self) -> None:
        diff = self.result["compare_poses"]
        self.assertEqual(diff["shared_joints"], 3)
        self.assertAlmostEqual(diff["max_rotation_degrees"], 45.0, places=3)

    def test_deform_actually_moves_the_skin(self) -> None:
        """조인트를 돌렸으면 스킨이 따라와야 한다. 이것이 리그가 사는 곳이다."""
        deformed = self.result["deform_skin"]
        self.assertEqual(deformed["points"], 240)
        self.assertEqual(deformed["moved_points"], 240)
        self.assertGreater(deformed["movement"]["max"], 0.5)
        # 굽혔으니 X 로 퍼지고 Y 로 낮아진다.
        self.assertLess(
            deformed["bbox_after"]["min"][0], deformed["bbox_before"]["min"][0]
        )
        self.assertLess(
            deformed["bbox_after"]["size"][1], deformed["bbox_before"]["size"][1]
        )

    # ---- APEX ------------------------------------------------------------

    def test_fk_rig_graph_has_one_node_per_joint(self) -> None:
        rig = self.result["build_fk_rig"]
        self.assertEqual(rig["graph_nodes"], 3)
        self.assertEqual(rig["callbacks"], ["TransformObject"])
        self.assertEqual(rig["errors"], [])
        self.assertEqual(
            self.result["apex_graph_nodes"]["names"], ["hips", "spine", "chest"]
        )

    def test_rig_script_decompiles_to_readable_code(self) -> None:
        """APEX 그래프를 코드로 되돌리는 것이 이 팩의 차별점이다."""
        script = self.result["apex_rig_script"]["script"]
        self.assertIn("TransformObject(", script)
        self.assertIn("__name='hips'", script)
        self.assertIn("parent=spine_xform", script)

    def test_callback_registry_is_queryable(self) -> None:
        callbacks = self.result["apex_callbacks"]
        self.assertGreater(callbacks["total_registered"], 2000)
        self.assertGreater(callbacks["subgraphs"], 100)
        self.assertIn("fbik::SolveFABRIK", callbacks["names"])

    def test_callback_signature_resolves_types(self) -> None:
        info = self.result["apex_callback_info"]
        outputs = {p["name"]: p["type"] for p in info["outputs"]}
        self.assertEqual(outputs["skel"], "FBIKSkeleton")
        self.assertEqual(outputs["success"], "Bool")
        self.assertTrue(info["inputs"][0]["in_place"])

    # ---- 검증이 실제로 문제를 잡는가 -------------------------------------

    def test_a_correct_rig_passes_clean(self) -> None:
        """멀쩡한 리그에 지적이 뜨면 검증이 신뢰를 잃는다."""
        good = self.result["validate_good"]
        self.assertTrue(good["ok"])
        self.assertEqual(good["issues"], [])

    def test_detached_joint_is_caught(self) -> None:
        """일부러 계층을 끊으면 잡아야 한다."""
        broken = self.result["validate_broken_hierarchy"]
        self.assertIn("multiple_roots", broken["checks"])
        issue = next(i for i in broken["issues"] if i["check"] == "multiple_roots")
        self.assertEqual(sorted(issue["joints"]), ["chest", "hips"])

    def test_missing_transform_is_an_error(self) -> None:
        """transform 없이는 포즈도 캡처도 방향을 알 수 없다."""
        raw = self.result["validate_raw"]
        self.assertFalse(raw["ok"])
        self.assertIn("missing_transform", raw["checks"])

    def test_broken_weights_are_caught(self) -> None:
        """일부러 웨이트 합을 1이 아니게 만들면 잡아야 한다."""
        broken = self.result["validate_broken_weights"]
        self.assertFalse(broken["ok"])
        self.assertIn("weight_sum_not_one", broken["checks"])
        self.assertIn("unweighted_points", broken["checks"])
        self.assertIn("excess_influences", broken["checks"])

        sums = next(i for i in broken["issues"] if i["check"] == "weight_sum_not_one")
        self.assertEqual(sums["count"], 20)
        unweighted = next(
            i for i in broken["issues"] if i["check"] == "unweighted_points"
        )
        self.assertEqual(unweighted["count"], 10)

    def test_weight_stats_agrees_with_validate(self) -> None:
        """같은 데이터를 두 툴이 다르게 세면 둘 중 하나가 틀린 것이다."""
        stats = self.result["broken_weight_stats"]
        self.assertEqual(stats["unweighted_points"], 10)
        self.assertEqual(stats["sum"]["not_one"], 30)  # 반토막 20 + 0 짜리 10
        self.assertEqual(stats["influences_per_point"]["histogram"]["0"], 10)

    def test_bind_pose_drift_is_caught(self) -> None:
        """포즈가 걸린 스켈레톤을 바인드 포즈로 쓰면 알려 줘야 한다."""
        drifted = self.result["validate_bind_drift"]
        self.assertIn("bind_pose_drift", drifted["checks"])

    # ---- 실패 메시지가 다음에 무엇을 할지 알려 주는가 --------------------

    def test_missing_joint_message_lists_real_names(self) -> None:
        message = self.result["missing_joint_message"]
        self.assertIn("list_joints", message)
        self.assertIn("hips", message)

    def test_missing_capture_message_points_at_capture_skin(self) -> None:
        message = self.result["no_capture_message"]
        self.assertIn("capture_skin", message)
        self.assertIn("boneCapture", message)

    def test_not_a_graph_message_names_the_missing_attribs(self) -> None:
        message = self.result["not_a_graph_message"]
        self.assertIn("callback", message)
        self.assertIn("build_fk_rig", message)


if __name__ == "__main__":
    unittest.main()
