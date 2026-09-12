"""스테이지 검증 - 렌더를 걸기 전에 무엇이 빠졌는지 찾는다.

USD 에서 가장 흔한 실수들을 한 번에 훑는다. 전부 컴포지션이 끝난 스테이지에서
확인하므로, "노드 파라미터는 맞는데 결과가 이상하다"는 경우를 잡을 수 있다.

각 항목은 무엇이 잘못됐는지와 **어떻게 고치는지**를 함께 준다. 심각도는 셋이다.

    error    이대로면 렌더가 실패하거나 빈 화면이 나온다
    warning  의도한 것일 수도 있지만 대개 실수다
    info     알아 두면 좋은 것
"""

from __future__ import annotations

from typing import Any

from houdini_mcp import tool

from .usdcommon import HOUDINI_LAYER_INFO, resolve_lop, stage_of

DEFAULT_LOP = "/stage"

PER_CATEGORY = 20
"""항목 하나당 보고할 프림 수 상한. 수십만 개가 같은 문제를 가질 수 있다."""


def _issue(severity: str, kind: str, message: str, fix: str, paths: list[str]):
    return {
        "severity": severity,
        "kind": kind,
        "message": message,
        "fix": fix,
        "count": len(paths),
        "paths": paths[:PER_CATEGORY],
        "truncated": len(paths) > PER_CATEGORY,
    }


@tool()
def validate_stage(
    lop: str = DEFAULT_LOP,
    check_materials: bool = True,
    check_render: bool = True,
) -> dict[str, Any]:
    """스테이지를 훑어 흔한 문제를 찾는다 - 깨진 에셋 경로, 빈 프림, 바인딩 누락.

    렌더를 걸기 전이나 결과가 비어 나올 때 여기서 시작한다. 각 항목에 고치는
    방법이 붙어 있다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        check_materials: 머티리얼 바인딩이 없는 지오메트리를 찾는다.
            머티리얼 자체를 만들고 고치는 것은 houdini_mcp_mat 의 일이다.
        check_render: 렌더 설정과 카메라가 있는지 본다. 렌더를 실제로 거는 것은
            houdini_mcp_render 의 일이다.
    """
    from pxr import Usd, UsdGeom, UsdLux, UsdRender, UsdShade

    node = resolve_lop(lop)
    stage = stage_of(node)

    unresolved: list[str] = []
    empty: list[str] = []
    unbound: list[str] = []
    no_extent: list[str] = []
    inactive: list[str] = []
    invisible: list[str] = []
    lights: list[str] = []
    cameras: list[str] = []
    render_settings: list[str] = []
    total = 0

    # 비활성 프림까지 봐야 "왜 안 보이지"를 답할 수 있다.
    predicate = Usd.PrimIsDefined & ~Usd.PrimIsAbstract
    for prim in Usd.PrimRange(stage.GetPseudoRoot(), predicate):
        if prim.IsPseudoRoot() or prim.GetTypeName() == HOUDINI_LAYER_INFO:
            continue
        total += 1
        path = str(prim.GetPath())

        if not prim.IsActive():
            inactive.append(path)
            continue

        if prim.IsA(UsdLux.BoundableLightBase) or prim.IsA(
            UsdLux.NonboundableLightBase
        ):
            lights.append(path)
        if prim.IsA(UsdGeom.Camera):
            cameras.append(path)
        if prim.IsA(UsdRender.Settings):
            render_settings.append(path)

        # 에셋 경로가 풀리지 않으면 텍스처도 레퍼런스도 조용히 사라진다.
        for attr in prim.GetAttributes():
            if not attr.HasAuthoredValue():
                continue
            value = attr.Get()
            if hasattr(value, "path") and hasattr(value, "resolvedPath"):
                if value.path and not value.resolvedPath:
                    unresolved.append(f"{path}.{attr.GetName()} -> {value.path}")

        imageable = UsdGeom.Imageable(prim)
        if imageable and imageable.ComputeVisibility() == UsdGeom.Tokens.invisible:
            invisible.append(path)

        boundable = UsdGeom.Boundable(prim)
        if boundable and not boundable.GetExtentAttr().HasAuthoredValue():
            no_extent.append(path)

        if check_materials and prim.IsA(UsdGeom.Gprim):
            bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            if not bound:
                unbound.append(path)

        type_name = str(prim.GetTypeName())
        if (
            type_name in ("", "Xform", "Scope")
            and not prim.GetChildren()
            and not any(a.HasAuthoredValue() for a in prim.GetAttributes())
        ):
            empty.append(path)

    issues: list[dict[str, Any]] = []

    if node.errors():
        issues.append(
            _issue(
                "error",
                "cook_error",
                f"{node.path()} 가 쿡 에러를 내고 있습니다.",
                "에러 메시지를 읽고 해당 노드를 고치세요. 아래 errors 를 봅니다.",
                list(node.errors()),
            )
        )

    if unresolved:
        issues.append(
            _issue(
                "error",
                "unresolved_asset",
                "풀리지 않는 에셋 경로가 있습니다. 텍스처나 레퍼런스가 조용히 빠집니다.",
                "파일이 실제로 있는지 확인하고, 상대 경로면 레이어 기준으로 맞는지 "
                "보세요. prim_origin 으로 어느 레이어가 그 경로를 썼는지 찾습니다.",
                unresolved,
            )
        )

    if not stage.GetDefaultPrim():
        issues.append(
            _issue(
                "warning",
                "no_default_prim",
                "defaultPrim 이 없습니다. 이 스테이지를 다른 씬이 레퍼런스로 "
                "끌어갈 때 어느 프림을 쓸지 알 수 없습니다.",
                "configurelayer LOP 의 Default Primitive 를 설정하거나, "
                "에셋으로 쓸 최상위 프림을 정하세요.",
                [],
            )
        )

    if empty:
        issues.append(
            _issue(
                "warning",
                "empty_prim",
                "자식도 값도 없는 빈 프림이 있습니다.",
                "만들다 만 것인지 확인하세요. 의도한 그룹이면 무시해도 됩니다.",
                empty,
            )
        )

    if no_extent:
        issues.append(
            _issue(
                "warning",
                "no_extent",
                "extent 가 없는 지오메트리가 있습니다. 뷰포트 프레이밍과 바운드 "
                "컬링이 어긋납니다.",
                "설정하려면 UsdGeom 계열 LOP 이 extent 를 계산하게 두거나 "
                "set_usd_attribute 로 extent 를 직접 거세요.",
                no_extent,
            )
        )

    if check_materials and unbound:
        issues.append(
            _issue(
                "warning",
                "unbound_geometry",
                "머티리얼이 바인딩되지 않은 지오메트리가 있습니다. 렌더러 기본 "
                "셰이더로 나옵니다.",
                "houdini_mcp_mat 의 툴로 머티리얼을 만들고 바인딩하세요.",
                unbound,
            )
        )

    if not lights:
        issues.append(
            _issue(
                "error" if check_render else "warning",
                "no_lights",
                "라이트가 하나도 없습니다. 대부분의 렌더러에서 검은 화면이 나옵니다.",
                "create_light_rig 으로 3점 조명과 환경 돔을 한 번에 만들 수 있습니다.",
                [],
            )
        )

    if check_render:
        if not cameras:
            issues.append(
                _issue(
                    "warning",
                    "no_camera",
                    "카메라 프림이 없습니다.",
                    "camera LOP 으로 만들거나, 뷰포트 뷰를 카메라로 저장하세요.",
                    [],
                )
            )
        if not render_settings:
            issues.append(
                _issue(
                    "info",
                    "no_render_settings",
                    "UsdRender.Settings 프림이 없습니다. 렌더러 기본값으로 갑니다.",
                    "houdini_mcp_render 의 툴이나 karmarendersettings LOP 으로 "
                    "해상도·AOV·카메라를 정하세요.",
                    [],
                )
            )

    if invisible:
        issues.append(
            _issue(
                "info",
                "invisible",
                "보이지 않게 설정된 프림이 있습니다.",
                "의도한 것이 아니면 visibility 어트리뷰트를 inherited 로 되돌리세요.",
                invisible,
            )
        )

    if inactive:
        issues.append(
            _issue(
                "info",
                "inactive",
                "비활성 프림이 있습니다. 자식까지 통째로 스테이지에서 빠집니다.",
                "의도한 것이 아니면 prune LOP 이나 activate 설정을 확인하세요.",
                inactive,
            )
        )

    severity_counts: dict[str, int] = {}
    for issue in issues:
        severity_counts[issue["severity"]] = severity_counts.get(issue["severity"], 0) + 1

    return {
        "lop": node.path(),
        "prims_checked": total,
        "light_count": len(lights),
        "camera_count": len(cameras),
        "render_settings_count": len(render_settings),
        "issue_count": len(issues),
        "by_severity": severity_counts,
        "issues": issues,
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
    }
