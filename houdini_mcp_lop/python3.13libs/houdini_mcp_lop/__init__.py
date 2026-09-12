"""LOPs / Solaris / USD 전문 툴 팩.

이 팩은 USD 를 **LOP 노드의 파라미터가 아니라 컴포지션이 끝난 스테이지로**
다룬다. `hou.LopNode.stage()` 가 주는 `pxr.Usd.Stage` 를 직접 질의하므로,
서브레이어·레퍼런스·페이로드·배리언트·인헤릿이 겹친 뒤의 **실제 값**을 본다.
노드 파라미터를 읽는 방식은 컴포지션을 무시하기 때문에 틀린 답을 준다.

    stage        스테이지 조회 - 요약, 계층, 검색, 프림 상세
    attrs        USD 어트리뷰트 읽기·쓰기
    layers       레이어 스택과 값의 출처 추적 (prim_origin)
    composition  컴포지션 아크 - 레퍼런스·페이로드·서브레이어·배리언트
    lights       UsdLux 라이트
    check        스테이지 검증

usdcommon 은 툴이 없는 공용 헬퍼라 TOOL_MODULES 에 넣지 않는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = (
    "stage",
    "attrs",
    "layers",
    "composition",
    "lights",
    "check",
)
