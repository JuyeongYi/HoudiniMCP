"""Houdini MCP 기본 툴 팩 예시.

이 패키지를 import 하면 툴이 레지스트리에 등록된다. 등록은 모듈을 읽는 것만으로
일어나므로(데코레이터), pythonrc.py 는 import 만 하면 된다.
"""

from . import scene  # noqa: F401 - import 자체가 툴을 등록한다

__all__ = ["scene"]
