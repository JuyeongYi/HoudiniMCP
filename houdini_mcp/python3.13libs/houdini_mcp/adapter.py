"""레지스트리의 ToolSpec 을 MCP 툴로 바꿔 서버에 붙인다.

UE 의 FToolsetRegistryToolAdapter 와 같은 자리다. 레지스트리는 MCP 를 모르고,
MCP 서버는 개별 툴을 모른다. 둘을 아는 것은 이 모듈뿐이다.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from .logs import get_logger, get_tool_logger
from .mainthread import run_in_main_thread
from .registry import AFFINITY_MAIN, ToolRegistry, ToolSpec

_log = get_logger("adapter")


def bind(spec: ToolSpec) -> Callable[..., Any]:
    """ToolSpec 을 MCP 가 호출할 함수로 감싼다.

    두 가지를 씌운다.

      - affinity 가 "main" 이면 메인 스레드로 넘긴다.
      - 호출과 실패를 그 툴 팩의 로거로 남긴다. 어느 팩에서 난 문제인지 로그만
        보고 알 수 있어야 한다.

    functools.wraps 가 __wrapped__ 를 달아주므로 inspect.signature() 는 원래
    시그니처를 그대로 본다. MCPServer 가 시그니처로 입력 스키마를 만들기 때문에
    이게 중요하다.
    """
    logger = get_tool_logger(spec.package or "unknown")
    needs_main_thread = spec.affinity == AFFINITY_MAIN

    @functools.wraps(spec.fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.info("call %s", spec.name)
        try:
            if needs_main_thread:
                result = run_in_main_thread(spec.fn, *args, **kwargs)
            else:
                result = spec.fn(*args, **kwargs)
        except Exception:
            logger.exception("failed %s", spec.name)
            raise
        logger.debug("done %s", spec.name)
        return result

    return wrapper


class ToolSync:
    """레지스트리 내용을 MCP 서버에 반영하고, 이후 변경도 따라간다.

    서버가 뜨기 전에 등록된 툴은 첫 sync() 에서 붙고, 뜬 뒤에 등록된 툴은
    구독 콜백으로 붙는다. 덕분에 패키지 로드 순서를 신경 쓸 필요가 없다.
    """

    def __init__(self, server: Any, registry: ToolRegistry) -> None:
        self._server = server
        self._registry = registry
        self._bound: set[str] = set()
        self._unsubscribe: Callable[[], None] | None = None

    def sync(self) -> tuple[list[str], list[str]]:
        """레지스트리와 서버를 맞춘다. (추가된 이름, 제거된 이름)을 돌려준다."""
        current = {spec.name: spec for spec in self._registry.all()}

        removed = sorted(self._bound - set(current))
        for name in removed:
            try:
                self._server.remove_tool(name)
            except Exception:  # noqa: BLE001 - 이미 없으면 그만이다
                pass
            self._bound.discard(name)

        added = []
        for name in sorted(current):
            if name in self._bound:
                continue
            spec = current[name]
            self._server.add_tool(
                bind(spec),
                name=spec.name,
                title=spec.title,
                description=spec.description or None,
                meta=spec.meta or None,
            )
            self._bound.add(name)
            added.append(name)

        return added, removed

    def start(self) -> None:
        """첫 동기화를 하고 이후 변경을 구독한다."""
        if self._unsubscribe is None:
            self._unsubscribe = self._registry.subscribe(self._on_registry_changed)
        self.sync()

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _on_registry_changed(self) -> None:
        added, removed = self.sync()
        if added or removed:
            _log.info(
                "툴 갱신 +%d -%d (추가: %s)", len(added), len(removed), ", ".join(added)
            )
