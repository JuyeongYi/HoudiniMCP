"""USD 스테이지에서 렌더 설정을 읽고, 렌더 전에 점검하는 헬퍼. 툴은 없다.

파라미터 이름을 하드코딩하지 않는 이유가 여기 있다. `karmarendersettings` 의
파라미터 이름은 버전이 올라가면 바뀌지만, 스테이지에 찍히는 `UsdRender`
스키마는 USD 표준이라 바뀌지 않는다. 노드가 아니라 결과물(스테이지)을 본다.

UsdRender 스키마: https://openusd.org/release/api/usd_render_page_front.html
"""

from __future__ import annotations

from typing import Any

from pxr import Sdf, UsdGeom, UsdLux, UsdRender, UsdShade

from houdini_mcp_base import paths

from ._common import writable_dir

MAX_LISTED = 20
"""예시로 보여줄 프림 개수. 전부 보내면 컨텍스트만 태운다."""


# ---- 스테이지 질의 ----------------------------------------------------


def find_settings_prims(stage) -> list[str]:
    """스테이지에 있는 RenderSettings 프림 전부."""
    return [
        prim.GetPath().pathString
        for prim in stage.TraverseAll()
        if prim.IsA(UsdRender.Settings)
    ]


def resolve_settings(stage, prim_path: str | None = None) -> UsdRender.Settings:
    """쓸 RenderSettings 를 정한다.

    prim_path 를 주면 그것을, 아니면 스테이지 메타데이터의 기본 설정을 쓴다.
    그것도 없고 후보가 여럿이면 고르라고 한다 - 아무거나 고르면 엉뚱한 것을
    렌더한다.
    """
    if prim_path:
        prim = stage.GetPrimAtPath(Sdf.Path(prim_path))
        if not prim or not prim.IsValid():
            found = find_settings_prims(stage)
            raise ValueError(
                f"스테이지에 그런 프림이 없습니다: {prim_path}. "
                f"RenderSettings 후보: {', '.join(found) or '없음'}"
            )
        settings = UsdRender.Settings(prim)
        if not settings:
            raise ValueError(
                f"{prim_path} 는 RenderSettings 프림이 아닙니다 "
                f"(type={prim.GetTypeName()}). "
                f"RenderSettings 후보: {', '.join(find_settings_prims(stage)) or '없음'}"
            )
        return settings

    default = UsdRender.Settings.GetStageRenderSettings(stage)
    if default:
        return default

    found = find_settings_prims(stage)
    if len(found) == 1:
        return UsdRender.Settings(stage.GetPrimAtPath(Sdf.Path(found[0])))
    if not found:
        raise ValueError(
            "스테이지에 RenderSettings 프림이 없습니다. karmarendersettings LOP 을 "
            "만들어 붙이세요 (create_node 로 /stage 에 karmarendersettings)."
        )
    raise ValueError(
        f"RenderSettings 가 여럿인데 스테이지 기본값이 없습니다: {', '.join(found)}. "
        f"settings_prim 으로 하나를 지정하세요."
    )


def _targets(rel) -> list[str]:
    if not rel:
        return []
    return [path.pathString for path in rel.GetTargets()]


def _get(attr) -> Any:
    """어트리뷰트 값을 JSON 으로 나갈 수 있는 형태로."""
    if not attr:
        return None
    value = attr.Get()
    return _plain(value)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Sdf.AssetPath):
        return value.path
    if hasattr(value, "__len__") and not isinstance(value, str):
        try:
            return [_plain(item) for item in value]
        except TypeError:
            pass
    return str(value)


def describe_var(prim) -> dict[str, Any]:
    """RenderVar(AOV) 하나."""
    var = UsdRender.Var(prim)
    return {
        "prim": prim.GetPath().pathString,
        "source_name": _get(var.GetSourceNameAttr()),
        "source_type": _get(var.GetSourceTypeAttr()),
        "data_type": _get(var.GetDataTypeAttr()),
    }


def describe_product(stage, path: str) -> dict[str, Any]:
    """RenderProduct 하나 - 어디에 무엇을 쓰는지."""
    prim = stage.GetPrimAtPath(Sdf.Path(path))
    if not prim or not prim.IsValid():
        return {"prim": path, "missing": True}
    product = UsdRender.Product(prim)
    var_paths = _targets(product.GetOrderedVarsRel())
    return {
        "prim": path,
        "product_type": _get(product.GetProductTypeAttr()),
        "product_name": _get(product.GetProductNameAttr()),
        "resolution": _get(product.GetResolutionAttr()),
        "camera": _targets(product.GetCameraRel()),
        "vars": [
            describe_var(stage.GetPrimAtPath(Sdf.Path(vp)))
            for vp in var_paths[:MAX_LISTED]
            if stage.GetPrimAtPath(Sdf.Path(vp))
        ],
        "var_count": len(var_paths),
    }


def describe_settings(stage, settings: UsdRender.Settings) -> dict[str, Any]:
    """RenderSettings 하나를 통째로. 스키마가 정의한 것만 이름으로 읽는다."""
    product_paths = _targets(settings.GetProductsRel())
    return {
        "prim": settings.GetPath().pathString,
        "resolution": _get(settings.GetResolutionAttr()),
        "camera": _targets(settings.GetCameraRel()),
        "pixel_aspect_ratio": _get(settings.GetPixelAspectRatioAttr()),
        "aspect_ratio_conform_policy": _get(
            settings.GetAspectRatioConformPolicyAttr()
        ),
        "data_window_ndc": _get(settings.GetDataWindowNDCAttr()),
        "included_purposes": _get(settings.GetIncludedPurposesAttr()),
        "material_binding_purposes": _get(settings.GetMaterialBindingPurposesAttr()),
        "disable_motion_blur": _get(settings.GetDisableMotionBlurAttr()),
        "disable_depth_of_field": _get(settings.GetDisableDepthOfFieldAttr()),
        "instantaneous_shutter": _get(settings.GetInstantaneousShutterAttr()),
        "rendering_color_space": _get(settings.GetRenderingColorSpaceAttr()),
        "products": [describe_product(stage, p) for p in product_paths[:MAX_LISTED]],
        "product_count": len(product_paths),
        "renderer_settings": _renderer_attrs(settings.GetPrim()),
    }


def _renderer_attrs(prim, limit: int = 40) -> dict[str, Any]:
    """스키마 밖의, 실제로 값을 써 넣은 어트리뷰트들.

    `karma:global:samplesperpixel` 처럼 델리게이트가 읽는 설정이 여기 들어온다.
    이름을 미리 알 필요 없이 "찍혀 있는 것"을 그대로 보여준다.
    """
    schema_names = set(UsdRender.Settings.GetSchemaAttributeNames(True))
    out: dict[str, Any] = {}
    for attr in prim.GetAttributes():
        name = attr.GetName()
        if name in schema_names or not attr.HasAuthoredValue():
            continue
        out[name] = _plain(attr.Get())
        if len(out) >= limit:
            out["…"] = "더 있습니다"
            break
    return out


def stage_frame_range(stage) -> dict[str, Any]:
    return {
        "start": stage.GetStartTimeCode() if stage.HasAuthoredTimeCodeRange() else None,
        "end": stage.GetEndTimeCode() if stage.HasAuthoredTimeCodeRange() else None,
        "fps": stage.GetFramesPerSecond(),
    }


# ---- 렌더 전 점검 ------------------------------------------------------


def render_checks(stage, settings_prim: str | None = None) -> dict[str, Any]:
    """렌더를 걸기 전에 무엇이 빠졌는지 전부 훑는다.

    렌더는 비싸다. 걸고 나서 새까만 것을 보고 알아차리는 대신, 걸기 전에
    안다. errors 가 하나라도 있으면 렌더해 봐야 소용이 없고, warnings 는
    나올 그림이 의도와 다를 수 있다는 뜻이다.
    """
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict[str, Any] = {}

    # 1. RenderSettings
    try:
        settings = resolve_settings(stage, settings_prim)
    except ValueError as exc:
        return {
            "ok": False,
            "errors": [str(exc)],
            "warnings": [],
            "checks": {"settings_prims": find_settings_prims(stage)},
        }
    facts["settings_prim"] = settings.GetPath().pathString

    # 2. 해상도
    resolution = settings.GetResolutionAttr().Get()
    facts["resolution"] = _plain(resolution)
    if not resolution or min(resolution) <= 0:
        errors.append(
            f"해상도가 잘못됐습니다: {_plain(resolution)}. RenderSettings 의 "
            f"resolution 을 1 이상으로 두세요."
        )

    # 3. 카메라
    camera_targets = _targets(settings.GetCameraRel())
    facts["camera"] = camera_targets
    cameras = [
        prim.GetPath().pathString
        for prim in stage.TraverseAll()
        if prim.IsA(UsdGeom.Camera)
    ]
    facts["cameras_on_stage"] = cameras[:MAX_LISTED]
    if not camera_targets:
        errors.append(
            "RenderSettings 가 카메라를 가리키지 않습니다. 스테이지의 카메라: "
            f"{', '.join(cameras) or '하나도 없습니다 - camera LOP 을 만드세요'}"
        )
    else:
        for target in camera_targets:
            prim = stage.GetPrimAtPath(Sdf.Path(target))
            if not prim or not prim.IsValid():
                errors.append(
                    f"RenderSettings 가 가리키는 카메라가 스테이지에 없습니다: {target}. "
                    f"쓸 수 있는 카메라: {', '.join(cameras) or '없음'}"
                )
            elif not prim.IsA(UsdGeom.Camera):
                errors.append(
                    f"{target} 는 카메라가 아닙니다 (type={prim.GetTypeName()}). "
                    f"쓸 수 있는 카메라: {', '.join(cameras) or '없음'}"
                )

    # 4. 라이트 - 없으면 husk 가 헤드라이트를 만들거나 새까맣게 나온다
    lights = [
        prim.GetPath().pathString
        for prim in stage.TraverseAll()
        if prim.HasAPI(UsdLux.LightAPI)
    ]
    facts["lights"] = lights[:MAX_LISTED]
    facts["light_count"] = len(lights)
    if not lights:
        warnings.append(
            "라이트가 하나도 없습니다. husk 는 기본값(--headlight distant)으로 "
            "임시 헤드라이트를 만들지만 의도한 그림은 아닙니다. domelight 나 "
            "distantlight LOP 을 붙이세요."
        )

    # 5. 렌더할 지오메트리
    gprims = [
        prim
        for prim in stage.TraverseAll()
        if prim.IsA(UsdGeom.Gprim) and prim.IsActive()
    ]
    facts["gprim_count"] = len(gprims)
    if not gprims:
        errors.append(
            "렌더할 지오메트리(Gprim)가 스테이지에 없습니다. sopimport 나 "
            "reference LOP 으로 무언가를 올리세요."
        )

    # 6. 머티리얼 바인딩
    unbound = []
    for prim in gprims:
        binding = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        if not binding or not binding[0] or not binding[0].GetPrim().IsValid():
            unbound.append(prim.GetPath().pathString)
    facts["unbound_gprims"] = unbound[:MAX_LISTED]
    facts["unbound_count"] = len(unbound)
    if unbound:
        warnings.append(
            f"머티리얼이 안 걸린 지오메트리가 {len(unbound)}개 있습니다 "
            f"(예: {', '.join(unbound[:3])}). Karma 는 기본 회색으로 렌더합니다. "
            f"assign_material 로 걸어 주세요."
        )

    # 7. 출력 경로
    products = []
    for path in _targets(settings.GetProductsRel()):
        info = describe_product(stage, path)
        name = info.get("product_name")
        if not name:
            errors.append(
                f"RenderProduct {path} 에 출력 경로(productName)가 없습니다. "
                f"karmarendersettings 의 picture 파라미터를 채우세요."
            )
        else:
            resolved = paths.to_path(str(name))
            ok, reason = writable_dir(resolved)
            info["output"] = resolved.as_posix()
            info["output_writable"] = ok
            info["output_note"] = reason
            if not ok:
                errors.append(f"출력 경로에 쓸 수 없습니다: {resolved} - {reason}")
            if not info.get("vars"):
                warnings.append(
                    f"RenderProduct {path} 에 RenderVar(AOV)가 없습니다. "
                    f"최소한 beauty 하나는 있어야 그림이 나옵니다."
                )
        products.append(info)
    facts["products"] = products
    if not products:
        errors.append(
            "RenderSettings 에 RenderProduct 가 없습니다. 어디에 쓸지가 정해지지 "
            "않았습니다. karmarendersettings 의 picture 를 설정하세요."
        )

    # 8. 프레임 범위
    facts["frame_range"] = stage_frame_range(stage)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": facts,
    }
