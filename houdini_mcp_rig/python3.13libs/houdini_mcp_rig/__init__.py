"""리깅 툴 팩 — 스켈레톤 · 스킨 웨이트 · APEX 리그 그래프 · 리그 검증.

    skeleton   조인트를 만들고 계층을 읽고 포즈를 건다
    skin       스킨 웨이트를 만들고 numpy 로 분석하고 디폼한다
    apexgraph  APEX 리그 그래프를 읽고 코드로 되돌린다. 콜백 2,286개를 질의한다
    check      validate_rig — 리그가 맞는지 검사한다

이 팩이 기존 구현과 갈라지는 지점은 둘이다.

1. **검증한다.** 조사한 기존 MCP 구현 다섯 중 리그가 맞는지 보는 것이 하나도
   없다. `validate_rig` 가 계층·이름·조인트 방향·웨이트 합·바인드 포즈를
   numpy 로 한 번에 검사하고, 지적마다 다음에 무엇을 할지 알려 준다.
2. **APEX 를 쓴다.** 기존 다섯은 전부 KineFX SOP 노드를 놓는 수준에 머문다.
   `apex_rig_script` 는 리그 그래프를 APEX 스크립트 코드로 디컴파일해서 돌려준다.

**경계** — 모션 데이터는 이 팩이 아니다. MotionClip·CHOP 채널·키프레임은
`houdini_mcp_chop` 이 맡는다. 여기는 **포즈 하나**(스켈레톤의 한 상태)까지만
다룬다. 시간축을 따라 흐르는 값이 나오면 chop 팩으로 넘어간다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "skeleton",
    "skin",
    "apexgraph",
    "check",
)
