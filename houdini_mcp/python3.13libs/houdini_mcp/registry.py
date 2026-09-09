"""MCP 툴 레지스트리.

이 모듈은 `hou` 에도 `mcp` 에도 의존하지 않는 순수 파이썬이다. 덕분에 Houdini
없이 단위 테스트할 수 있고, 툴 패키지가 서버의 구현 세부를 몰라도 된다.

툴 패키지는 pythonrc.py 에서 여기에 등록만 하고, 서버 패키지는 uiready.py 에서
등록된 것을 읽어 MCP 툴로 노출한다. 두 단계 사이의 경계는 Houdini 가 보장하므로
(tests/package_order 참고) 패키지들의 로드 순서를 신경 쓸 필요가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

Affinity = str
"""툴이 어느 스레드에서 실행돼야 하는지.

"main" - Houdini 메인 스레드에서 실행해야 한다. `hou` 를 건드리면 전부 이쪽이다.
"any"  - 아무 스레드에서나 안전하다. 순수 계산이나 파일 I/O 정도.
"""

AFFINITY_MAIN: Affinity = "main"
AFFINITY_ANY: Affinity = "any"


@dataclass(frozen=True)
class ToolSpec:
    """등록된 툴 하나."""

    name: str
    fn: Callable[..., Any]
    description: str = ""
    affinity: Affinity = AFFINITY_MAIN
    title: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    package: str = ""
    """이 툴이 어느 툴 팩에서 왔는지. 로그를 팩별로 가르는 데 쓴다.

    데코레이터가 함수의 __module__ 최상위 이름으로 자동으로 채운다.
    """

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("툴 이름이 비어 있습니다.")
        if self.affinity not in (AFFINITY_MAIN, AFFINITY_ANY):
            raise ValueError(
                f"affinity 는 {AFFINITY_MAIN!r} 또는 {AFFINITY_ANY!r} 여야 합니다: "
                f"{self.affinity!r}"
            )


Listener = Callable[[], None]


class ToolRegistry:
    """툴 등록소. 변경을 구독할 수 있다.

    서버가 이미 떠 있는 뒤에 툴이 추가돼도 구독자가 반영할 수 있게 한다.
    로드 순서에 기대지 않기 위한 장치다.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._listeners: list[Listener] = []

    # ---- 등록 --------------------------------------------------------

    def register(self, spec: ToolSpec, *, replace: bool = False) -> None:
        if spec.name in self._tools and not replace:
            raise ValueError(
                f"이미 등록된 툴입니다: {spec.name!r}. "
                f"의도한 교체라면 replace=True 를 쓰세요."
            )
        self._tools[spec.name] = spec
        self._notify()

    def unregister(self, name: str) -> bool:
        """등록을 해제한다. 실제로 지워졌으면 True."""
        if self._tools.pop(name, None) is None:
            return False
        self._notify()
        return True

    # ---- 조회 --------------------------------------------------------

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        """등록된 툴을 이름 순으로. 반환 리스트는 스냅샷이다."""
        return [self._tools[name] for name in sorted(self._tools)]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(self.all())

    # ---- 변경 구독 ---------------------------------------------------

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """변경 알림을 구독한다. 구독 해제 함수를 돌려준다."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def _notify(self) -> None:
        # 구독자 하나가 실패해도 나머지는 알림을 받아야 한다.
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 - 구독자 오류가 등록을 깨면 안 된다
                import traceback

                traceback.print_exc()


_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    """프로세스 전역 레지스트리."""
    return _REGISTRY


def tool(
    name: str | None = None,
    *,
    description: str | None = None,
    affinity: Affinity = AFFINITY_MAIN,
    title: str | None = None,
    replace: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """함수를 툴로 등록하는 데코레이터.

    이름은 기본적으로 함수 이름을, 설명은 docstring 첫 문단을 쓴다.

        from houdini_mcp.registry import tool

        @tool(description="현재 씬 경로를 돌려준다.")
        def scene_path() -> str:
            import hou
            return hou.hipFile.path()

    `hou` 를 건드리는 툴은 affinity 를 건드리지 마라 - 기본값이 "main" 이라
    서버가 알아서 메인 스레드로 넘긴다.
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        doc = (fn.__doc__ or "").strip()
        summary = doc.split("\n\n", 1)[0].strip() if doc else ""
        get_registry().register(
            ToolSpec(
                name=name or fn.__name__,
                fn=fn,
                description=description if description is not None else summary,
                affinity=affinity,
                title=title,
                package=infer_package(fn),
            ),
            replace=replace,
        )
        return fn

    return decorate


def infer_package(fn: Callable[..., Any]) -> str:
    """함수가 속한 툴 팩 이름을 추론한다.

    `houdini_mcp_tools_demo.scene` 같은 모듈 이름에서 최상위 `houdini_mcp_tools_demo`
    를 뽑는다. 로그를 툴 팩별로 가를 때 쓴다.
    """
    module = getattr(fn, "__module__", "") or ""
    return module.split(".", 1)[0] if module else "unknown"
