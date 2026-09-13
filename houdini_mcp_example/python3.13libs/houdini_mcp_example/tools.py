"""툴 팩을 만드는 법을 보여주는 최소 예시.

새 팩을 만들 때 이 팩을 복사해서 시작하면 된다. 필요한 파일은 넷뿐이다.

    packages/houdini_mcp_<도메인>.json                     패키지 정의
    houdini_mcp_<도메인>/python3.13libs/pythonrc.py        등록 진입점
    houdini_mcp_<도메인>/python3.13libs/houdini_mcp_<도메인>/__init__.py
    houdini_mcp_<도메인>/python3.13libs/houdini_mcp_<도메인>/<모듈>.py   <- 이 파일

툴을 만드는 규칙은 셋뿐이다.

1. `@tool()` 을 붙인다. 이름은 함수 이름, 설명은 docstring 첫 문단이 된다.
2. 타입 힌트를 단다. MCP 입력 스키마가 시그니처에서 자동으로 만들어진다.
3. `hou` 를 건드리는 툴은 affinity 를 건드리지 않는다. 기본값 "main" 이면
   서버가 알아서 Houdini 메인 스레드로 넘겨 준다.

실패는 그냥 예외를 던지면 된다. 어느 팩에서 났는지와 함께 자동으로 로그에
남는다.
"""

from __future__ import annotations

from houdini_mcp import get_registry, tool


@tool(affinity="any")
def tool_catalog() -> list[dict[str, str]]:
    """등록된 모든 툴의 이름, 설명, 소속 팩.

    레지스트리만 읽고 `hou` 를 건드리지 않으므로 affinity="any" 다. 메인 스레드로
    넘기지 않아도 되는 툴이 어떻게 생겼는지 보여주는 예시이기도 하다.
    """
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "affinity": spec.affinity,
            "package": spec.package,
        }
        for spec in get_registry().all()
    ]
