"""houdini_mcp_base.paths 회귀 테스트.

hython 을 서브프로세스로 띄워 scenario.py 를 돌리고 결과를 검사한다.
tests/sop 와 같은 방식이라 시스템 python 으로도 돌아간다.

여기 있는 단정은 전부 실측으로 드러난 조용한 실패를 막는다. 이유는 각 테스트의
docstring 과 houdini_mcp_base/paths.py 의 모듈 docstring 에 있다.

실행:
    python -m pytest tests/paths -q
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
    MARKER 를 쓰게 된다. 이 파일을 더하면서 실제로 밟았다 -
    알파벳 순으로 paths 가 sop 보다 먼저 수집되어 sop 테스트 17개가 깨졌다.
    """
    path = Path(__file__).with_name("scenario.py")
    spec = importlib.util.spec_from_file_location("houdini_mcp_paths_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MARKER = _load_scenario().MARKER

REPO = Path(__file__).resolve().parents[2]

PACKAGES = ("houdini_mcp", "houdini_mcp_base")

TIMEOUT = 300


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


class PathsTest(unittest.TestCase):
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.result = _run_scenario()
        except HoudiniNotFound as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def test_no_check_raised(self) -> None:
        self.assertEqual(self.result["errors"], {})

    # --- 전개 ---------------------------------------------------------------

    def test_native_separator_does_not_eat_variables(self) -> None:
        """`C:\\tmp\\$F4.exr` 에서 `\\$` 가 이스케이프로 먹히면 변수가 안 풀린다."""
        entry = self.result["backslash_frame"]
        self.assertEqual(entry["expanded"], entry["expected"])

    def test_expand_at_frame(self) -> None:
        self.assertTrue(self.result["at_frame"].endswith("/r.0007.exr"))

    def test_tilde_is_houdini_home(self) -> None:
        """`~` 는 Houdini 의 `$HOME` 이다. 파이썬 Path.home() 과 다를 수 있다.

        Windows 에서 HOME 이 없으면 Houdini 가 Documents 로 잡는다(실측). 이
        테스트 하네스도 HOME 을 지우고 띄우므로 실제로 갈라지는 조건에서 돈다.
        """
        entry = self.result["tilde"]
        self.assertEqual(entry["expanded"], entry["houdini_home"] + "/x.exr")

    def test_unc_keeps_both_leading_slashes(self) -> None:
        if not self.result["windows"]:
            self.skipTest("UNC 는 Windows 에만 있다")
        self.assertTrue(self.result["unc"].startswith("//server/share"))

    def test_to_parm_uses_forward_slashes(self) -> None:
        """역슬래시가 든 경로를 ROP 파라미터에 넣으면 쓰기가 실패한다."""
        self.assertNotIn("\\", self.result["to_parm"])

    def test_collapse_accepts_native_separator(self) -> None:
        self.assertEqual(self.result["collapse_backslash"], "$HIP/geo/a.bgeo.sc")

    def test_portable_folds_absolute_but_keeps_user_variables(self) -> None:
        """전개했다 다시 접으면 `$HIP`/`$JOB` 이 아닌 사용자 변수를 잃는다."""
        self.assertEqual(self.result["portable"], {
            "absolute_inside_hip": "$HIP/geo/a.bgeo.sc",
            "keeps_user_variable": "$HMCP_USER_ROOT/tex/a.exr",
            "keeps_hip": "$HIP/geo/a.bgeo.sc",
            "outside": "D:/elsewhere/x.exr",
        })

    # --- 변수 ---------------------------------------------------------------

    def test_unknown_variable_is_reported(self) -> None:
        self.assertEqual(self.result["unresolved_unknown"], ["HMCP_NO_SUCH_VAR"])

    def test_known_and_context_variables_are_not_reported(self) -> None:
        """`$SF` 는 DOP 밖에서 비지만 모르는 변수가 아니다. `$FPS` 는 실재한다."""
        self.assertEqual(self.result["unresolved_known"], [])

    def test_glued_variable_name_is_reported(self) -> None:
        """Houdini 는 `$F_b` 를 한 변수로 읽어 지운다."""
        self.assertEqual(self.result["unresolved_glued"], ["F_b"])

    # --- 시퀀스 -------------------------------------------------------------

    def test_sequence_tokens(self) -> None:
        tokens = self.result["tokens"]
        for text in ("$HIP/x.$F4.exr", "$HIP/x.$F.exr", "$HIP/x.${F4}.exr",
                     "$HIP/x.$SF.sim", "$HIP/t.<UDIM>.exr", "$HIP/t.%(UDIM)d.exr",
                     "$HIP/t.<UVTILE>.exr", "$HIP/x.%04d.exr"):
            self.assertTrue(tokens[text], text)

    def test_frame_like_variables_are_not_sequences(self) -> None:
        """`$FPS` `$FSTART` 는 프레임마다 바뀌지 않는다."""
        tokens = self.result["tokens"]
        for text in ("$HIP/x.$FPS.txt", "$HIP/$FSTART.txt", "$HIP/x.exr"):
            self.assertFalse(tokens[text], text)

    def test_frame_sequence_counts_real_files(self) -> None:
        entry = self.result["frame_sequence"]
        self.assertTrue(entry["sequence"])
        self.assertEqual(entry["names"], ["wall.0001.exr", "wall.0002.exr", "wall.0003.exr"])

    def test_udim_matches_four_digits_only(self) -> None:
        self.assertEqual(self.result["udim_sequence"]["names"], ["tex.1001.exr", "tex.1002.exr"])

    def test_bracket_in_directory_is_not_a_glob(self) -> None:
        self.assertEqual(self.result["bracket_dir"]["names"], ["f.0001.exr"])

    def test_single_file(self) -> None:
        self.assertEqual(self.result["single_file"], {"names": ["wall.0002.exr"], "sequence": False})
        self.assertEqual(self.result["single_missing"], {"names": [], "sequence": False})

    # --- 응답 ---------------------------------------------------------------

    def test_describe_keeps_variable_form(self) -> None:
        entry = self.result["describe_file"]
        self.assertEqual(entry["path"], "$HIP/seq/wall.0001.exr")
        self.assertEqual(entry["resolved"], f"{self.result['hip']}/seq/wall.0001.exr")
        self.assertTrue(entry["exists"])
        self.assertNotIn("unresolved", entry)

    def test_describe_sequence(self) -> None:
        entry = self.result["describe_sequence"]
        self.assertEqual(entry["path"], "$HIP/seq/wall.$F4.exr")
        self.assertEqual(entry["file_count"], 3)
        self.assertTrue(entry["exists"])

    def test_describe_reports_unresolved(self) -> None:
        self.assertEqual(self.result["describe_unresolved"]["unresolved"], ["HMCP_NO_SUCH_VAR"])

    # --- 쓰기 준비 -----------------------------------------------------------

    def test_prepare_output_creates_real_directory_not_literal_variable(self) -> None:
        """원문을 Path 로 mkdir 하면 현재 디렉토리에 `$HIP` 폴더가 생겼다."""
        entry = self.result["prepare_output"]
        self.assertEqual(entry["target"], f"{self.result['hip']}/out/deep/a.bgeo.sc")
        self.assertTrue(entry["parent_exists"])
        self.assertEqual(entry["cwd_entries"], [])

    def test_prepare_output_refuses_unresolved_before_creating_anything(self) -> None:
        entry = self.result["prepare_unresolved"]
        self.assertIn("$HMCP_NO_SUCH_VAR", entry["message"])
        self.assertEqual(entry["cwd_entries"], [])

    def test_prepare_output_guards_overwrite(self) -> None:
        self.assertIn("overwrite=True", self.result["prepare_overwrite"])
        self.assertEqual(self.result["prepare_overwrite_ok"], "exists.bgeo.sc")

    def test_missing_file_lists_siblings(self) -> None:
        message = self.result["require_file_missing"]
        self.assertIn("wall.0001.exr", message)

    def test_require_file(self) -> None:
        self.assertEqual(self.result["require_file_ok"], "wall.0002.exr")
        self.assertIn("디렉토리", self.result["require_file_dir"])
        self.assertEqual(self.result["require_dir_ok"], "seq")

    def test_missing_messages_read_naturally(self) -> None:
        """조사를 틀리면("디렉토리이") 모델에게 가는 메시지가 어색해진다."""
        self.assertTrue(self.result["require_file_missing"].startswith("그런 파일이 없습니다"))
        self.assertTrue(self.result["require_dir_missing"].startswith("그런 디렉토리가 없습니다"))

    def test_file_stat(self) -> None:
        self.assertEqual(self.result["file_stat"]["present"], 1)
        self.assertEqual(self.result["file_stat"]["absent"], {"exists": False})

    def test_is_inside_handles_short_names(self) -> None:
        """$HFS 는 PROGRA~1 같은 짧은 이름으로 풀린다."""
        entry = self.result["is_inside"]
        self.assertEqual(entry, {"inside": True, "outside": False, "hfs_short_name": True})

    # --- $HFS ---------------------------------------------------------------

    def test_hfs_bin(self) -> None:
        self.assertEqual(self.result["hfs_bin"], {"vcc": True, "absent": None})
        self.assertIn("$HFS/bin", self.result["require_hfs_bin_missing"])

    def test_run_hfs_tool(self) -> None:
        self.assertEqual(self.result["run_hfs_tool"], {"ok": True, "has_cvex": True})
        self.assertFalse(self.result["run_hfs_tool_absent"]["available"])

    def test_env_paths(self) -> None:
        self.assertTrue(self.result["env_paths"])

    def test_nothing_leaked_into_working_directory(self) -> None:
        self.assertEqual(self.result["cwd_after"], [])


if __name__ == "__main__":
    unittest.main()
