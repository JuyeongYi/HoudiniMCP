"""머티리얼·룩데브 전문 툴 팩.

셰이더를 만들고, 잇고, 할당하고, 텍스처를 붙이는 것을 담는다. 노드를 만들고
잇는 데서 끝내지 않고 Houdini 22 에 번들된 전문 라이브러리로 결과를 확인한다.

    MaterialX 1.39.5   셰이더 그래프 검증과 프리셋 저장 포맷
    OpenImageIO 2.5    텍스처 파일을 실제로 열어 해상도·채널·통계 확인
    pxr (OpenUSD)      UsdShade 로 실제 바인딩 질의
    PyOpenColorIO 2.5  컬러스페이스 목록을 OCIO 설정에서

    build      머티리얼·셰이더 노드 저작과 연결
    query      머티리얼 조회·그래프 구조·MaterialX 검증
    assign     머티리얼 할당과 실제 바인딩 확인 (SOP 어트리뷰트 / LOP UsdShade)
    texture    텍스처 부착과 OIIO 검사
    color      OCIO 컬러스페이스 조회와 지정
    preset     MaterialX 문서로 저장·불러오기

`houdini_mcp_lop` 와의 경계: **머티리얼 자체는 이 팩, 스테이지 일반은 lop.**
이 팩이 USD 를 건드리는 것은 UsdShade(머티리얼·바인딩)에 한정한다. 프림 조회,
레이어 스택, 컴포지션, 라이트, 배리언트는 lop 팩이 맡는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "build",
    "query",
    "assign",
    "texture",
    "color",
    "preset",
)
