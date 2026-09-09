"""툴 팩을 만드는 법을 보여주는 최소 예시 팩.

이 패키지를 import 하면 툴이 레지스트리에 등록된다.
"""

from . import tools  # noqa: F401 - import 자체가 툴을 등록한다

__all__ = ["tools"]
