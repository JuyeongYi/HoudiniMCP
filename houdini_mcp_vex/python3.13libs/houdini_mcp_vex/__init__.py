"""VEX 전문 툴 팩.

VEX 코드를 쓰고, **컴파일해 보고**, 진단한다. 핵심은 검증에 노드를 쓰지 않는
것이다. Houdini 는 VEX 컴파일러를 `$HFS/bin/vcc` 에 실행 파일로 갖고 있으므로,
씬을 건드리지 않고 줄·열 번호까지 정확한 진단을 받을 수 있다.

    compiler   vcc 발견·호출·진단 파싱 (툴 없음)
    snippet    wrangle 의 @어트리뷰트 문법을 순수 VEX 로 옮기는 번역기 (툴 없음)
    validate   validate_vex, wrangle_attribs - 노드를 만들지 않는 검증
    wrangle    create_wrangle, update_wrangle, list_wrangles, diagnose_wrangle
    reference  list_vex_contexts, vex_function_info - VEX 언어 자체의 레퍼런스

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다. compiler 와
snippet 은 툴이 없으므로 목록에 없다 - 툴 모듈이 알아서 import 한다.
"""

TOOL_MODULES = (
    "validate",
    "wrangle",
    "reference",
)
