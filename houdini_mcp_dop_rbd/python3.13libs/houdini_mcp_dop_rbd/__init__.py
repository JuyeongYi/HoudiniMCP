"""DOP 의 RBD 전문 팩 - 조각과 강체 시뮬을 진단한다.

    diagnose  rbd_piece_stats(시뮬 전 조각 점검), rbd_sim_report(프레임별 시뮬 읽기)

houdini_mcp_dop 은 솔버를 가리지 않는 것을 담고, RBD 에만 뜻이 있는 것은 여기에
둔다(프로젝트 CLAUDE.md 의 팩 분리 규칙). RBD Bullet Solver SOP 처럼 dopnet 없이
도는 RBD 도 받는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
"""

TOOL_MODULES = ("diagnose",)
