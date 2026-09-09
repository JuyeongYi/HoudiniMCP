"""Houdini MCP - Houdini 안에서 도는 MCP 서버와 툴 레지스트리.

툴 패키지는 이 모듈에서 `tool` 데코레이터와 레지스트리만 가져다 쓰면 된다.
서버 구현을 알 필요는 없다.

    from houdini_mcp import tool

    @tool()
    def scene_path() -> str:
        "현재 씬 파일 경로."
        import hou
        return hou.hipFile.path()

서버 자체(`houdini_mcp.server`)는 여기서 import 하지 않는다. 툴 패키지가
pythonrc.py 에서 이 모듈을 건드릴 때 MCP SDK 까지 끌려오면, SDK 가 없는 환경에서
툴 등록이 통째로 실패해버린다. 서버는 uiready.py 가 따로 가져간다.
"""

from .media import image_result
from .registry import (
    AFFINITY_ANY,
    AFFINITY_MAIN,
    ToolRegistry,
    ToolSpec,
    get_registry,
    tool,
)
from .undo import undoable

__all__ = [
    "AFFINITY_ANY",
    "AFFINITY_MAIN",
    "ToolRegistry",
    "ToolSpec",
    "get_registry",
    "image_result",
    "tool",
    "undoable",
]

__version__ = "0.1.0"
