"""Houdini 프로세스 안에서 MCP 서버를 띄운다.

Houdini 의 stdin/stdout 은 이미 Houdini 가 쓰고 있으므로 stdio 트랜스포트는
쓸 수 없다. streamable-http 로 로컬 포트를 연다.

서버는 별도 스레드의 asyncio 루프에서 돈다. 따라서 툴 함수는 워커 스레드에서
호출되고, `hou` 를 만지는 툴은 adapter 가 메인 스레드로 넘긴다.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
from typing import Any

from .adapter import ToolSync
from .logs import get_logger
from .registry import get_registry

_log = get_logger("server")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 22926
"""int("HOU", 36) - 알파벳을 36진수로 읽은 값이다.

기억하기 쉽고, 흔히 쓰이는 대역(8000/9000번대)을 피해 충돌 가능성이 낮다.
"""
DEFAULT_PATH = "/mcp"

SERVER_NAME = "houdini-mcp"
SERVER_VERSION = "0.1.0"


def _new_standard_loop() -> asyncio.AbstractEventLoop:
    """표준 asyncio 이벤트 루프를 만든다.

    Houdini 는 asyncio 를 자체 구현(haio)으로 대체하고 HoudiniEventLoopPolicy 를
    설치한다. 그 정책은

        - new_event_loop() 가 스레드와 무관하게 항상 같은 루프를 돌려주고
        - set_event_loop() 를 무시하며
        - 그 루프는 메인 스레드에서만 동작한다(check_thread)

    따라서 asyncio.new_event_loop() 를 쓰면 백그라운드 스레드에서
    "Current thread is not the main thread" 로 죽는다. 정책을 거치지 않고 표준
    루프 클래스를 직접 인스턴스화해야 한다.

    전역 정책은 건드리지 않는다. Houdini 자신이 그 정책에 의존하고 있다.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.SelectorEventLoop()


def port_in_use(host: str, port: int, timeout: float = 1.0) -> bool:
    """누군가 이미 그 포트에서 듣고 있는지."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _warn(message: str) -> None:
    """로그와 Houdini 상태바 양쪽에 경고를 남긴다.

    Houdini 는 stdout 을 자체 콘솔 창에 띄워주므로 로그만으로도 보이지만, 그 창을
    계속 보고 있지는 않으므로 상태바에도 남긴다.
    """
    _log.warning(message)
    try:
        import hou

        if hou.isUIAvailable():
            hou.ui.setStatusMessage(
                f"Houdini MCP: {message}", severity=hou.severityType.Warning
            )
    except Exception:  # noqa: BLE001 - 경고를 못 띄운다고 기동을 막을 이유는 없다
        pass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("%s=%r 를 정수로 읽지 못해 %d 를 씁니다.", name, raw, default)
        return default


class HoudiniMCPServer:
    """MCP 서버 하나의 수명주기를 관리한다."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        path: str | None = None,
    ) -> None:
        self.host = host or os.environ.get("HOUDINI_MCP_HOST", DEFAULT_HOST)
        self.port = port if port is not None else _env_int("HOUDINI_MCP_PORT", DEFAULT_PORT)
        self.path = path or os.environ.get("HOUDINI_MCP_PATH", DEFAULT_PATH)

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sync: ToolSync | None = None
        self._server: Any = None

        self.last_error: BaseException | None = None
        """서버 스레드가 죽은 원인. 로그를 뒤지지 않고 코드로 확인하려고 남긴다."""

        self.last_traceback: str = ""

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{self.path}"

    def start(self) -> None:
        if self.is_running:
            _log.info("이미 실행 중입니다: %s", self.url)
            return

        # 포트를 이미 누가 쓰고 있으면 이 인스턴스는 서버를 띄우지 않는다(first-wins).
        # 보통 다른 Houdini 인스턴스가 먼저 떠 있는 경우다. 이 인스턴스는 MCP 로
        # 제어되지 않으며, 클라이언트의 요청은 먼저 뜬 쪽으로 간다.
        if port_in_use(self.host, self.port):
            _warn(
                f"포트 {self.host}:{self.port} 를 이미 다른 프로세스가 쓰고 있어 "
                f"이 Houdini 인스턴스에서는 MCP 서버를 실행하지 않습니다. "
                f"먼저 실행된 Houdini 가 MCP 요청을 처리합니다. "
                f"이 인스턴스를 따로 붙이려면 HOUDINI_MCP_PORT 를 다르게 주고 "
                f"다시 시작하세요."
            )
            return

        # import 는 여기서 한다. SDK 가 없을 때 모듈 import 자체가 실패하면
        # 안내 메시지를 낼 기회조차 없어진다.
        from mcp.server.mcpserver import MCPServer

        self._server = MCPServer(
            name=SERVER_NAME,
            version=SERVER_VERSION,
            instructions=(
                "SideFX Houdini 를 조작하는 툴 모음이다. 툴은 Houdini 세션 안에서 "
                "실행되며, 씬을 바꾸는 툴은 되돌리기 어려우니 신중히 쓴다."
            ),
        )

        self._sync = ToolSync(self._server, get_registry())
        self._sync.start()

        self._thread = threading.Thread(
            target=self._serve, name="houdini-mcp-server", daemon=True
        )
        self._thread.start()

        count = len(get_registry())
        _log.info("서버 시작: %s (툴 %d개)", self.url, count)

    def _serve(self) -> None:
        loop = _new_standard_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self._server.run_streamable_http_async(
                    host=self.host,
                    port=self.port,
                    streamable_http_path=self.path,
                )
            )
        except BaseException as exc:  # noqa: BLE001 - 조용히 죽으면 진단이 어렵다
            import traceback

            self.last_error = exc
            self.last_traceback = traceback.format_exc()
            _log.error("서버 스레드가 예외로 종료했습니다:%s%s", os.linesep, self.last_traceback)
        finally:
            self._loop = None
            loop.close()

    def stop(self) -> None:
        if self._sync is not None:
            self._sync.stop()
            self._sync = None

        loop = self._loop
        if loop is not None:
            for task in asyncio.all_tasks(loop):
                loop.call_soon_threadsafe(task.cancel)

        self._thread = None
        _log.info("서버 중지를 요청했습니다.")


_SERVER: HoudiniMCPServer | None = None


def get_server() -> HoudiniMCPServer:
    global _SERVER
    if _SERVER is None:
        _SERVER = HoudiniMCPServer()
    return _SERVER


def start() -> HoudiniMCPServer:
    """서버를 띄운다. uiready.py 에서 부른다."""
    server = get_server()
    server.start()
    return server


def stop() -> None:
    if _SERVER is not None:
        _SERVER.stop()
