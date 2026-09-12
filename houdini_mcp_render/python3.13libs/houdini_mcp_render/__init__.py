"""렌더를 걸고, 진행 상황을 알고, 결과 이미지를 실제로 읽어 확인하는 팩.

이 팩의 존재 이유는 마지막 한 줄이다. 렌더를 걸어 놓고 "끝났습니다" 로
돌려주면 새까만 프레임이 나와도 알 수 없다. 여기의 툴은 렌더가 끝나면
OpenImageIO 로 픽셀을 읽어 채널별 통계를 내고, 검거나 NaN 이 섞였으면
그렇다고 말한다.

모듈 구성:

    settings   UsdRender 스키마로 렌더 설정을 읽는다
    check      렌더를 걸기 전에 무엇이 빠졌는지 점검한다
    run        husk 백그라운드 렌더와 ROP 블로킹 렌더
    result     렌더 결과 이미지를 읽어 통계·썸네일·비교를 낸다

밑줄로 시작하는 모듈(_common, _usdrender, _image)은 헬퍼라 여기 적지 않는다.
TOOL_MODULES 에 적힌 것만 register_pack 이 격리해서 읽는다.
"""

TOOL_MODULES = ("settings", "check", "run", "result")
