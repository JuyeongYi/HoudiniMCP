"""CHOP 전문 툴 팩 — 채널을 값이 아니라 **분석 결과**로 다룬다.

파라미터 하나에 키를 찍고 읽고 지우는 것은 `houdini_mcp_base` 의 anim 모듈에
있다. 프레임 범위는 base 의 `set_frame_range` 다. 여기는 채널을 시계열
데이터로 보고 그 성질을 판정하는 것을 담는다.

    build      CHOP 네트워크·노드 생성, 필터 적용 (전후 통계 비교)
    data       채널 목록·통계·샘플 — numpy 벌크 경로
    check      루프 가능 여부와 튐을 실제 값으로 판정
    transfer   CHOP <-> 파라미터 (키로 굽기, 파라미터 끌어오기, 익스포트 플래그)
    files      Houdini 채널 파일 입출력 (.clip/.bclip, .chan/.bchan)
    bake       파라미터의 식을 키프레임으로 굽고 값이 같은지 검증
    audio      오디오 파일을 읽어 파형을 분석

샘플을 하나씩 파지 않는다. `hou.Track.allSamples()` 가 범위를 통째로 주고,
numpy 가 그것을 압축한다. 실측으로 240샘플에 360배 차이가 난다
(docs/design/packs/chop.md 참고).

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "build",
    "data",
    "check",
    "transfer",
    "files",
    "bake",
    "audio",
)
