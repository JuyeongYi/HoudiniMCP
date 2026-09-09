"""Houdini 메인 스레드로 호출을 넘기는 유틸.

`hou` 는 스레드 안전하지 않다. MCP 서버는 백그라운드 스레드에서 도는 asyncio
루프 위에서 툴을 호출하므로, `hou` 를 만지는 코드는 반드시 메인 스레드로
넘겨야 한다. `hdefereval` 이 그 통로다.

조사한 기존 구현 5종 중 툴 수가 많은 둘(dcc-mcp-houdini 259개, fxhoudinimcp
188개)만 이 마샬링을 제대로 하고, 나머지는 워커 스레드에서 `hou` 를 직접
호출한다. 후자는 언제 터져도 이상하지 않다.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_TIMEOUT = 120.0
"""메인 스레드 응답을 기다리는 기본 한도(초).

Houdini 가 무거운 작업 중이면 이벤트 루프가 늦게 돈다. 무한정 기다리면 MCP
클라이언트 쪽이 먼저 죽으므로 여기서 끊는다.
"""


class MainThreadTimeout(RuntimeError):
    """메인 스레드가 제한 시간 안에 응답하지 않았다."""


def is_main_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


def ui_available() -> bool:
    """Houdini UI 이벤트 루프가 살아 있는지.

    hython/hbatch 처럼 UI 가 없으면 hdefereval 이 돌 이벤트 루프도 없다.
    """
    try:
        import hou
    except ImportError:
        return False
    try:
        return bool(hou.isUIAvailable())
    except Exception:  # noqa: BLE001 - 초기화 중이면 실패할 수 있다
        return False


def run_in_main_thread(
    fn: Callable[..., T],
    *args: Any,
    timeout: float | None = DEFAULT_TIMEOUT,
    **kwargs: Any,
) -> T:
    """fn 을 Houdini 메인 스레드에서 실행하고 결과를 돌려준다.

    다음 두 경우에는 마샬링 없이 그 자리에서 호출한다:
      - 이미 메인 스레드다. 자기 자신을 기다리면 데드락이므로 반드시 걸러야 한다.
      - UI 가 없다(hython/hbatch). 넘길 이벤트 루프가 없다.

    hdefereval.executeInMainThreadWithResult() 는 타임아웃을 받지 않아서, 대신
    executeDeferred() 로 넘기고 여기서 직접 기다린다. Houdini 가 긴 작업에 붙들려
    있을 때 워커 스레드가 영원히 매달리는 것을 막는다.

    Raises:
        MainThreadTimeout: 제한 시간 안에 메인 스레드가 실행하지 못했을 때.
    """
    if is_main_thread() or not ui_available():
        return fn(*args, **kwargs)

    import hdefereval

    done = threading.Event()
    result: dict[str, Any] = {}

    def call() -> None:
        try:
            result["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - 호출자에게 그대로 전달한다
            result["error"] = exc
        finally:
            done.set()

    hdefereval.executeDeferred(call)

    if not done.wait(timeout):
        raise MainThreadTimeout(
            f"메인 스레드가 {timeout}초 안에 {getattr(fn, '__name__', fn)!r} 을 "
            f"실행하지 못했습니다. Houdini 가 다른 작업에 붙들려 있을 수 있습니다."
        )

    if "error" in result:
        raise result["error"]
    return result["value"]
