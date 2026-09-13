"""COP(Copernicus) 전문 팩 - 이미지 네트워크의 결과를 본다.

    preview  cop_preview(노드 출력을 그림으로), cop_layer_info(레이어 수치)

만든 계기(2026-09-13, 성 파괴 씬): COP 으로 석재·지면 텍스처를 만들었는데 결과를
볼 방법이 없어 파일로 내보낸 뒤 외부 도구로 PNG 를 만들어 봤다. 단일 채널 맵은
검게 나와 사실상 확인하지 못한 채 재질에 붙였고, 렌더에서 스펀지 같은 품질로
드러났다. COP 의 composite view 에 해당하는 것을 모델이 직접 볼 수 있어야 한다.

옛 COP2(cop2net)는 다루지 않는다. Houdini 20.5 부터의 Copernicus(copnet)만 받는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = ("preview",)
