"""Houdini 패키지 로드 순서 규칙을 실측으로 고정하는 회귀 테스트.

여기서 확정하는 규칙은 MCP 서버/툴 패키지 분리 설계의 전제다. Houdini 버전이
올라가면서 이 규칙이 바뀌면 설계가 조용히 깨지므로 테스트로 못 박는다.

실행:
    hython -m unittest discover tests/package_order
    또는 시스템 python 으로도 된다 (hython 을 서브프로세스로 띄우므로).

실제 사용자 pref 디렉토리(Documents/houdiniX.Y/packages)를 쓰는 테스트는
기본적으로 건너뛴다. 켜려면:
    HMCP_TEST_REAL_PREF=1
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from harness import (
    SLOT_PACKAGE_DIR,
    SLOT_USER_PREF,
    SLOT_USER_PREF_REAL,
    Package,
    PackageLab,
    make_gui_watchdog,
    real_user_pref_dir,
)

REAL_PREF_ENABLED = os.environ.get("HMCP_TEST_REAL_PREF") == "1"


class LoadOrderTest(unittest.TestCase):
    """스캔 순서 3번 슬롯(HOUDINI_PACKAGE_DIR)에서의 기본 규칙."""

    slot = SLOT_PACKAGE_DIR

    def lab(self, packages: list[Package]) -> PackageLab:
        return PackageLab(packages, slot=self.slot)

    def test_alphabetical_processing_reverses_execution(self) -> None:
        """파일명 알파벳순으로 처리되고, 실행 순서는 그 역순이 된다.

        hpath 가 기본 prepend 라서 HOUDINI_PATH 가 처리 순서의 역순이 되고,
        스크립트는 HOUDINI_PATH 순서로 실행되기 때문이다.
        """
        packages = [Package("A"), Package("B"), Package("C")]
        with self.lab(packages) as lab:
            result = lab.run()

        self.assertEqual(result.test_packages_on_path(), ["C", "B", "A"])
        self.assertEqual(result.order_of("pythonrc"), ["C", "B", "A"])
        self.assertEqual(result.order_of("ready"), ["C", "B", "A"])

    def test_process_order_controls_execution_order(self) -> None:
        """process_order 로 알파벳순을 덮어쓸 수 있다.

        process_order 가 작을수록 먼저 '처리'되고, 따라서 스크립트는 가장
        '나중에' 실행된다. 직관과 반대이므로 테스트로 고정한다.
        """
        packages = [
            Package("A", process_order=3),
            Package("B", process_order=2),
            Package("C", process_order=1),
        ]
        with self.lab(packages) as lab:
            result = lab.run()

        self.assertEqual(result.order_of("pythonrc"), ["A", "B", "C"])
        self.assertEqual(result.order_of("ready"), ["A", "B", "C"])

    def test_stages_do_not_interleave(self) -> None:
        """단계 간 순서는 보장된다: pythonrc 가 전부 끝난 뒤 ready 가 시작된다."""
        packages = [Package("A"), Package("B"), Package("C")]
        with self.lab(packages) as lab:
            result = lab.run()

        stages = [hook for hook, _ in result.events]
        first_ready = stages.index("ready")
        self.assertNotIn("pythonrc", stages[first_ready:])

    def test_123_runs_only_once_across_packages(self) -> None:
        """123.py 는 HOUDINI_PATH 최상위 하나만 실행된다.

        pythonrc/ready 와 달리 '전부 실행'이 아니다. 따라서 패키지가 123.py 로
        초기화를 하면 다른 패키지(그리고 사용자 개인 123.py)를 조용히 덮어친다.
        """
        packages = [Package("A"), Package("B"), Package("C")]
        with self.lab(packages) as lab:
            result = lab.run()

        self.assertEqual(result.order_of("123"), ["C"])

    def test_requires_blocks_package_when_target_missing(self) -> None:
        """requires 대상이 없으면 그 패키지는 통째로 처리되지 않는다."""
        packages = [
            Package("A", requires=["no_such_package"]),
            Package("B"),
        ]
        with self.lab(packages) as lab:
            result = lab.run()

        self.assertNotIn("A", result.test_packages_on_path())
        self.assertEqual(result.order_of("pythonrc"), ["B"])

    def test_requires_does_not_reorder_processing(self) -> None:
        """requires 는 존재 검사일 뿐 로드 순서를 바꾸지 않는다.

        B 가 C 를 requires 해도 처리 순서는 알파벳순 그대로다. 더 중요한 것은
        C 가 아직 처리되지 않은 시점에도 B 의 requires 가 통과한다는 점이다.
        즉 requires 는 '대상이 이미 로드됨'을 전혀 보장하지 않는다.
        """
        packages = [
            Package("A"),
            Package("B", requires=[f"{Package('C').json_name[:-len('.json')]}"]),
            Package("C"),
        ]
        with self.lab(packages) as lab:
            result = lab.run()

        # B 는 차단되지 않았다 (requires 통과).
        self.assertIn("B", result.test_packages_on_path())
        # 그리고 순서는 알파벳순 그대로 = 실행은 그 역순.
        self.assertEqual(result.order_of("pythonrc"), ["C", "B", "A"])


class UserPrefSlotTest(LoadOrderTest):
    """스캔 순서 1번 슬롯(HOUDINI_USER_PREF_DIR/packages)에서 같은 규칙이 성립하는지.

    HOUDINI_USER_PREF_DIR 을 임시 디렉토리로 돌려서 사용자 환경을 건드리지 않고
    1번 슬롯을 재현한다. 전통적인 패키지 배치 방식과 같은 경로 형태다.
    """

    slot = SLOT_USER_PREF


@unittest.skipUnless(
    REAL_PREF_ENABLED,
    "실제 pref 디렉토리를 건드리므로 기본 비활성. HMCP_TEST_REAL_PREF=1 로 활성화.",
)
class RealUserPrefSlotTest(LoadOrderTest):
    """사용자의 진짜 Documents/houdiniX.Y/packages 에 설치해서 검증한다.

    가장 현실에 가깝지만 부작용이 있다. 테스트가 만든 파일은 PREFIX 로 식별해
    반드시 정리한다.
    """

    slot = SLOT_USER_PREF_REAL

    def test_pref_dir_is_not_home_based(self) -> None:
        """pref 디렉토리가 $HOME 이 아니라 Documents 쪽으로 잡히는지 확인.

        Git Bash 처럼 HOME 이 설정된 셸에서 hython 을 돌리면 $HOME/houdiniX.Y 로
        빗나간다. 하네스가 HOME 을 제거하는 이유다.
        """
        pref = real_user_pref_dir()
        self.assertTrue(pref.is_dir(), f"pref 디렉토리가 없습니다: {pref}")
        self.assertNotEqual(
            pref,
            Path.home() / pref.name,
            "pref 디렉토리가 HOME 기준으로 잡혔습니다.",
        )


class RequiresSpellingTest(unittest.TestCase):
    """requires 대상을 어떻게 써야 하는지 고정한다.

    툴 패키지는 서버 패키지를 requires 로 가리키므로, 이 표기 규칙이 곧
    공개 인터페이스가 된다.
    """

    def _tools_loaded(self, requires: list[str] | None) -> bool:
        server = Package("SERVER")
        tools = Package("TOOLS", requires=requires or [])
        with PackageLab([server, tools]) as lab:
            result = lab.run()
        return "TOOLS" in result.test_packages_on_path()

    def test_bare_name_without_extension_passes(self) -> None:
        # Package("SERVER") 의 JSON 파일명에서 ".json" 을 뺀 이름.
        name = Package("SERVER").json_name[: -len(".json")]
        self.assertTrue(self._tools_loaded([name]))

    def test_name_with_json_extension_is_rejected(self) -> None:
        self.assertFalse(self._tools_loaded([Package("SERVER").json_name]))

    def test_name_is_case_sensitive(self) -> None:
        name = Package("SERVER").json_name[: -len(".json")]
        self.assertFalse(self._tools_loaded([name.upper()]))


class RequiresAcrossSlotsTest(unittest.TestCase):
    """서버와 툴 패키지가 다른 디렉토리 슬롯에 있어도 requires 가 성립하는지.

    툴이 먼저 스캔되는 슬롯에 있고 서버가 나중 슬롯에 있으면, 툴을 판정하는
    시점에 서버는 아직 스캔 전이다. 그래도 통과해야 사용자가 설치 위치를
    자유롭게 고를 수 있다.
    """

    def test_requires_finds_package_in_a_later_scanned_slot(self) -> None:
        server = Package("SERVER")
        tools = Package(
            "TOOLS", requires=[Package("SERVER").json_name[: -len(".json")]]
        )

        # 서버는 HOUDINI_PACKAGE_DIR(스캔 3번), 툴은 user pref(스캔 1번).
        server_lab = PackageLab([server], slot=SLOT_PACKAGE_DIR)
        tools_lab = PackageLab([tools], slot=SLOT_USER_PREF)
        server_lab.build()
        tools_lab.build()
        try:
            env_extra = {"HOUDINI_PACKAGE_DIR": str(server_lab.packages_dir)}
            result = tools_lab.run(env_extra=env_extra)
        finally:
            tools_lab.cleanup()
            server_lab.cleanup()

        self.assertIn("TOOLS", result.test_packages_on_path())
        self.assertIn("SERVER", result.test_packages_on_path())


@unittest.skipUnless(
    os.environ.get("HMCP_TEST_GUI") == "1",
    "Houdini GUI 를 실제로 띄우므로 기본 비활성. HMCP_TEST_GUI=1 로 활성화.",
)
class GuiHookTest(unittest.TestCase):
    """uiready.py 는 인터랙티브 세션에서만 실행되므로 GUI 로만 검증할 수 있다."""

    def test_uiready_runs_for_every_package_in_path_order(self) -> None:
        packages = [Package("A"), Package("B"), Package("C"), make_gui_watchdog()]
        with PackageLab(packages) as lab:
            result = lab.run_gui()

        uiready = [pkg for pkg in result.order_of("uiready") if pkg != "WATCHDOG"]

        # pythonrc/ready 와 같은 그룹이다: 전부 실행되고 순서도 같다.
        self.assertEqual(uiready, ["C", "B", "A"])
        self.assertEqual(uiready, result.order_of("pythonrc"))

    def test_123_still_runs_only_once_in_gui(self) -> None:
        packages = [Package("A"), Package("B"), Package("C"), make_gui_watchdog()]
        with PackageLab(packages) as lab:
            result = lab.run_gui()

        self.assertEqual(result.order_of("123"), ["C"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
