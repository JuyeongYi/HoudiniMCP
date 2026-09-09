"""툴 팩을 만드는 법을 보여주는 최소 예시 팩.

TOOL_MODULES 에 툴이 든 모듈 이름을 적으면 register_pack 이 하나씩 읽는다.
모듈을 여기서 import 하지 않는 이유는, 하나가 깨져도 나머지가 등록되게 하기
위해서다.
"""

TOOL_MODULES = ("tools",)
