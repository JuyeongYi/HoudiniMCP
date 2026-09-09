"""Houdini 패키지 로드 순서 실측 하네스.

Houdini 패키지 시스템은 문서만으로는 실행 순서를 확정할 수 없는 구석이 많다.
이 하네스는 임시 패키지 트리를 만들어 실제 hython으로 돌리고, 각 시작 훅이
어떤 패키지에서 어떤 순서로 실행됐는지를 기록해서 규칙을 실측한다.

주의 (실측으로 확인된 함정):
  - Git Bash 등 HOME 이 설정된 셸에서 hython 을 돌리면 HOUDINI_USER_PREF_DIR 이
    $HOME/houdiniX.Y 로 빗나간다. Windows 정상 경로는 Documents/houdiniX.Y 다.
    그래서 이 하네스는 HOUDINI_USER_PREF_DIR 을 항상 명시적으로 지정한다.
  - hpath 는 기본이 prepend 라서 HOUDINI_PATH 는 패키지 처리 순서의 역순이 된다.
    스크립트 실행 순서는 HOUDINI_PATH 순서를 따르므로, 처리 순서와 반대다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# 훅 이름 -> 패키지 디렉토리 안에서의 상대 경로. {py} 는 "3.13" 같은 태그.
HOOKS: dict[str, str] = {
    "pythonrc": "python{py}libs/pythonrc.py",
    "ready": "python{py}libs/ready.py",
    "uiready": "python{py}libs/uiready.py",
    "123": "scripts/123.py",
    "456": "scripts/456.py",
}

# 테스트 패키지 파일명 접두사. 실제 사용자 pref 디렉토리에 설치할 때
# 우리가 만든 것만 지우기 위한 표식이다.
PREFIX = "zzhmcptest_"

LOG_ENV = "HMCP_PKGTEST_LOG"

SLOT_PACKAGE_DIR = "package_dir"
"""HOUDINI_PACKAGE_DIR 로 지정하는 슬롯. 디렉토리 스캔 순서 3번."""

SLOT_USER_PREF = "user_pref"
"""HOUDINI_USER_PREF_DIR 을 임시 디렉토리로 돌린 뒤 그 안의 packages. 스캔 순서 1번.

실제 사용자 환경을 건드리지 않으면서 1번 슬롯의 동작을 그대로 재현한다.
"""

SLOT_USER_PREF_REAL = "user_pref_real"
"""사용자의 진짜 pref 디렉토리(Documents/houdiniX.Y/packages)에 설치하는 슬롯.

전통적인 배치 방식 그대로를 검증할 때만 쓴다. 부작용이 있으므로 명시적으로
골라야 하고, 정리는 PREFIX 가 붙은 파일/디렉토리에 한해서만 수행한다.
"""


class HoudiniNotFound(RuntimeError):
    pass


def find_hfs() -> Path:
    """Houdini 설치 경로($HFS)를 찾는다."""
    env = os.environ.get("HFS")
    if env and Path(env).is_dir():
        return Path(env)

    # 플랫폼별 기본 설치 위치. 여기 없으면 HFS 환경변수로 알려줘야 한다.
    if sys.platform == "win32":
        roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Side Effects Software"]
    elif sys.platform == "darwin":
        roots = [Path("/Applications/Houdini"), Path("/Applications")]
    else:
        roots = [Path("/opt"), Path.home() / "houdini"]

    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            for pattern in ("Houdini *", "hfs*", "Houdini*"):
                candidates += [p for p in root.glob(pattern) if (p / "bin").is_dir()]
    if not candidates:
        raise HoudiniNotFound("Houdini 설치를 찾지 못했습니다. HFS 환경변수를 지정하세요.")

    def version_key(path: Path) -> tuple[int, ...]:
        nums = re.findall(r"\d+", path.name)
        return tuple(int(n) for n in nums)

    return sorted(candidates, key=version_key)[-1]


def hython_path(hfs: Path) -> Path:
    for name in ("hython.exe", "hython"):
        candidate = hfs / "bin" / name
        if candidate.exists():
            return candidate
    raise HoudiniNotFound(f"hython 을 찾지 못했습니다: {hfs / 'bin'}")


def houdini_gui_path(hfs: Path) -> Path:
    """인터랙티브 Houdini 실행 파일. uiready.py 검증에 필요하다."""
    for name in ("houdini.exe", "houdini"):
        candidate = hfs / "bin" / name
        if candidate.exists():
            return candidate
    raise HoudiniNotFound(f"houdini 실행 파일을 찾지 못했습니다: {hfs / 'bin'}")


def houdini_version(hfs: Path) -> str:
    """설치 경로에서 major.minor 를 뽑는다. 예: "22.0".

    "Houdini 22.0.368"(Windows) 과 "hfs22.0.368"(Linux) 둘 다 처리한다.
    """
    m = re.search(r"(\d+)\.(\d+)", hfs.name)
    if not m:
        raise HoudiniNotFound(f"버전을 유추하지 못했습니다: {hfs.name}")
    return f"{m.group(1)}.{m.group(2)}"


def python_tag(hfs: Path) -> str:
    """Houdini 가 쓰는 파이썬 태그를 설치본에서 유도한다. 예: "3.13"."""
    found = sorted(hfs.glob("houdini/python*libs"))
    for path in found:
        m = re.match(r"python(\d+\.\d+)libs", path.name)
        if m:
            return m.group(1)
    raise HoudiniNotFound(f"python*libs 디렉토리를 찾지 못했습니다: {hfs / 'houdini'}")


@dataclass
class Package:
    """테스트용 Houdini 패키지 하나."""

    name: str
    process_order: int | None = None
    requires: list[str] = field(default_factory=list)
    recommends: list[str] = field(default_factory=list)
    hooks: tuple[str, ...] = tuple(HOOKS)

    extra_source: dict[str, str] = field(default_factory=dict)
    """훅 이름 -> 로그 기록 뒤에 덧붙일 추가 소스. watchdog 같은 특수 패키지용."""

    @property
    def json_name(self) -> str:
        return f"{PREFIX}{self.name.lower()}.json"

    @property
    def dir_name(self) -> str:
        return f"{PREFIX}{self.name.lower()}"

    def to_json(self, hpath: Path) -> dict:
        # Houdini 패키지 JSON 은 플랫폼과 무관하게 슬래시 경로를 쓴다.
        doc: dict = {"hpath": hpath.as_posix()}
        if self.process_order is not None:
            doc["process_order"] = self.process_order
        if self.requires:
            doc["requires"] = list(self.requires)
        if self.recommends:
            doc["recommends"] = list(self.recommends)
        return doc


@dataclass
class RunResult:
    """hython 한 번 실행의 결과."""

    events: list[tuple[str, str]]
    """(훅 이름, 패키지 이름) 을 실행된 순서대로."""

    houdini_path: list[str]
    stdout: str
    stderr: str
    returncode: int

    def order_of(self, hook: str) -> list[str]:
        """특정 훅이 실행된 패키지 이름을 순서대로."""
        return [pkg for h, pkg in self.events if h == hook]

    def test_packages_on_path(self) -> list[str]:
        """HOUDINI_PATH 에 올라온 테스트 패키지를 순서대로."""
        names = []
        for entry in self.houdini_path:
            base = Path(entry).name
            if base.startswith(PREFIX):
                names.append(base[len(PREFIX):].upper())
        return names


_PROBE = """
import hou
import os
marker = 'HMCP_HPATH:'
for entry in hou.text.expandString('$HOUDINI_PATH').split(os.pathsep):
    print(marker + entry)
"""


class PackageLab:
    """임시 패키지 트리를 만들고 hython 으로 실행해 순서를 관찰한다.

    컨텍스트 매니저로 쓰면 종료 시 만든 것을 모두 정리한다.
    """

    def __init__(
        self,
        packages: list[Package],
        slot: str = SLOT_PACKAGE_DIR,
        hfs: Path | None = None,
    ) -> None:
        self.packages = packages
        self.slot = slot
        self.hfs = hfs or find_hfs()
        self.hython = hython_path(self.hfs)
        self.py_tag = python_tag(self.hfs)
        self.hou_version = houdini_version(self.hfs)

        self._tmp = Path(tempfile.mkdtemp(prefix="hmcp_pkgtest_"))
        self._installed: list[Path] = []

        self.pkg_root = self._tmp / "pkgs"
        self.log_path = self._tmp / "order.log"
        self.packages_dir = self._resolve_packages_dir()

    # ---- 설치 위치 ---------------------------------------------------

    @property
    def _sandbox_pref_dir(self) -> Path:
        """샌드박스 pref 디렉토리의 실제 경로 (__HVER__ 가 치환된 형태)."""
        return self._tmp / f"houdini{self.hou_version}"

    @property
    def _sandbox_pref_template(self) -> Path:
        """HOUDINI_USER_PREF_DIR 에 넣을 값.

        Houdini 는 이 값에 __HVER__ 토큰이 없으면
        "EnvControl: HOUDINI_USER_PREF_DIR missing __HVER__, ignored." 를 내고
        통째로 무시한다. 그러면 사용자의 진짜 pref 디렉토리가 쓰여서 격리가 샌다.
        """
        return self._tmp / "houdini__HVER__"

    def _resolve_packages_dir(self) -> Path:
        if self.slot == SLOT_PACKAGE_DIR:
            return self._tmp / "packages"
        if self.slot == SLOT_USER_PREF:
            return self._sandbox_pref_dir / "packages"
        if self.slot == SLOT_USER_PREF_REAL:
            return real_user_pref_dir(self.hfs) / "packages"
        raise ValueError(f"알 수 없는 슬롯: {self.slot}")

    # ---- 컨텍스트 ----------------------------------------------------

    def __enter__(self) -> "PackageLab":
        self.build()
        return self

    def __exit__(self, *_exc) -> None:
        self.cleanup()

    def build(self) -> None:
        self.packages_dir.mkdir(parents=True, exist_ok=True)
        for pkg in self.packages:
            pkg_dir = self.pkg_root / pkg.dir_name
            for hook in pkg.hooks:
                rel = HOOKS[hook].format(py=self.py_tag)
                target = pkg_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                source = _hook_source(hook, pkg.name) + pkg.extra_source.get(hook, "")
                target.write_text(source, encoding="utf-8")

            json_path = self.packages_dir / pkg.json_name
            json_path.write_text(
                json.dumps(pkg.to_json(pkg_dir), indent=2), encoding="utf-8"
            )
            self._installed.append(json_path)

    def cleanup(self) -> None:
        # 실제 사용자 pref 에 설치한 경우, 우리가 만든 파일만 지운다.
        for path in self._installed:
            if path.name.startswith(PREFIX) and path.exists():
                path.unlink()
        self._installed.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ---- 실행 --------------------------------------------------------

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["HFS"] = str(self.hfs)
        env[LOG_ENV] = str(self.log_path)

        # HOME 이 설정된 셸(Git Bash 등)에서 pref 디렉토리가 빗나가는 것을 막는다.
        env.pop("HOME", None)

        if self.slot == SLOT_PACKAGE_DIR:
            env["HOUDINI_PACKAGE_DIR"] = str(self.packages_dir)
            # pref 디렉토리도 샌드박스로 돌려야 사용자의 실제 packages 가 섞이지 않는다.
            env["HOUDINI_USER_PREF_DIR"] = str(self._sandbox_pref_template)
        elif self.slot == SLOT_USER_PREF:
            env.pop("HOUDINI_PACKAGE_DIR", None)
            env["HOUDINI_USER_PREF_DIR"] = str(self._sandbox_pref_template)
        elif self.slot == SLOT_USER_PREF_REAL:
            env.pop("HOUDINI_PACKAGE_DIR", None)
            env.pop("HOUDINI_USER_PREF_DIR", None)
        return env

    def run(
        self, snippet: str = "", env_extra: dict[str, str] | None = None
    ) -> RunResult:
        """hython 으로 한 번 실행한다.

        env_extra 는 슬롯이 정한 환경변수 위에 덧씌운다. 서로 다른 슬롯에
        설치된 패키지를 한 세션에서 함께 로드시킬 때 쓴다.
        """
        if self.log_path.exists():
            self.log_path.unlink()

        env = self.env()
        if env_extra:
            env.update(env_extra)

        proc = subprocess.run(
            [str(self.hython), "-c", _PROBE + snippet],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )

        events: list[tuple[str, str]] = []
        if self.log_path.exists():
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                if "|" in line:
                    hook, _, pkg = line.partition("|")
                    events.append((hook.strip(), pkg.strip()))

        houdini_path = [
            line[len("HMCP_HPATH:"):]
            for line in proc.stdout.splitlines()
            if line.startswith("HMCP_HPATH:")
        ]

        return RunResult(
            events=events,
            houdini_path=houdini_path,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )

    def run_gui(self, timeout: int = 600) -> RunResult:
        """실제 GUI 세션(houdini.exe)으로 실행한다.

        uiready.py 는 인터랙티브 세션에서만 실행되므로 hython 으로는 검증할 수
        없다. 종료는 watchdog 패키지가 담당하므로 packages 목록에
        make_gui_watchdog() 을 반드시 포함시켜야 한다. 없으면 timeout 까지
        Houdini 창이 떠 있게 된다.
        """
        if self.log_path.exists():
            self.log_path.unlink()

        env = self.env()
        env["HOUDINI_NO_SPLASH"] = "1"

        proc = subprocess.run(
            [str(houdini_gui_path(self.hfs))],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        events: list[tuple[str, str]] = []
        houdini_path: list[str] = []
        if self.log_path.exists():
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                if "|" not in line:
                    continue
                hook, _, value = line.partition("|")
                hook, value = hook.strip(), value.strip()
                if hook == "hpath":
                    houdini_path.append(value)
                else:
                    events.append((hook, value))

        return RunResult(
            events=events,
            houdini_path=houdini_path,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )


def real_user_pref_dir(hfs: Path | None = None) -> Path:
    """사용자의 진짜 HOUDINI_USER_PREF_DIR 을 Houdini 에게 직접 물어본다.

    HOME 을 제거한 환경에서 물어봐야 Windows 정상 경로(Documents/houdiniX.Y)가
    나온다. 셸이 HOME 을 설정해 두면 $HOME/houdiniX.Y 로 빗나간다.
    """
    hfs = hfs or find_hfs()
    env = dict(os.environ)
    env.pop("HOME", None)
    env.pop("HOUDINI_USER_PREF_DIR", None)
    proc = subprocess.run(
        [
            str(hython_path(hfs)),
            "-c",
            "import hou; print('HMCP_PREF:' + hou.text.expandString('$HOUDINI_USER_PREF_DIR'))",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("HMCP_PREF:"):
            return Path(line[len("HMCP_PREF:"):].strip())
    raise HoudiniNotFound(f"HOUDINI_USER_PREF_DIR 을 얻지 못했습니다.\n{proc.stderr}")


def make_gui_watchdog(quit_after_waits: int = 20) -> Package:
    """GUI 세션을 자동 종료시키고 HOUDINI_PATH 를 기록하는 감시 패키지.

    process_order 를 아주 작게 줘서 가장 먼저 '처리'되게 하고, 그 결과
    HOUDINI_PATH 에서는 맨 뒤에 놓여 uiready.py 가 가장 '나중에' 실행된다.
    따라서 다른 패키지의 uiready 가 모두 끝난 뒤에 종료를 예약한다.

    종료는 UI 이벤트 루프가 몇 번 돈 뒤에 일어나므로, uiready 단계가 끝나기 전에
    창이 닫히는 일은 없다.
    """
    source = (
        "import os\n"
        "import hou\n"
        "import hdefereval\n"
        f"with open(os.environ[{LOG_ENV!r}], 'a') as _f:\n"
        "    for _entry in hou.text.expandString('$HOUDINI_PATH').split(os.pathsep):\n"
        "        print('hpath | ' + _entry, file=_f)\n"
        "def _quit():\n"
        "    hou.exit(suppress_save_prompt=True)\n"
        f"hdefereval.executeDeferredAfterWaiting(_quit, {quit_after_waits})\n"
    )
    return Package(
        "WATCHDOG",
        process_order=-10_000,
        hooks=("uiready",),
        extra_source={"uiready": source},
    )


def _hook_source(hook: str, package_name: str) -> str:
    """훅 스크립트 본문. 백슬래시 이스케이프를 피하려고 print 를 쓴다."""
    payload = f"{hook} | {package_name}"
    return (
        "import os\n"
        f"with open(os.environ[{LOG_ENV!r}], 'a') as _f:\n"
        f"    print({payload!r}, file=_f)\n"
    )
