"""UsdLux 라이트.

라이트를 **프림으로** 다룬다. 노드 파라미터로 찾지 않는다 - 레퍼런스로 들어온
라이트나 다른 DCC 가 만든 라이트는 LOP 노드가 아예 없기 때문이다.
`prim.HasAPI(UsdLux.LightAPI)` 가 출처와 무관하게 라이트를 찾아 준다.

값을 읽는 것도 `UsdLux.LightAPI` 로 한다. 값을 쓰는 것은 두 갈래다.

    create_light      라이트 LOP 노드를 만든다. 프림을 새로 만드는 일이라
                      노드가 맞다. USD 속성 이름을 hou.text.encode 로
                      파라미터 이름으로 바꿔 거므로 인코딩된 이름을
                      하드코딩하지 않는다.
    set_light         이미 있는 라이트 프림의 값을 바꾼다. attrs 와 같은
                      pythonscript 경로를 쓰므로 레퍼런스로 들어온 라이트도
                      고칠 수 있다.
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from .usdcommon import (
    attr_spec,
    author_attributes,
    insert_lop,
    jsonify,
    node_report,
    prim_at,
    resolve_lop,
    stage_of,
)

DEFAULT_LOP = "/stage"

LIGHT_TYPES: dict[str, tuple[str, str | None]] = {
    "distant": ("light::2.0", "UsdLuxDistantLight"),
    "sphere": ("light::2.0", "UsdLuxSphereLight"),
    "point": ("light::2.0", "point"),
    "disk": ("light::2.0", "UsdLuxDiskLight"),
    "rect": ("light::2.0", "UsdLuxRectLight"),
    "cylinder": ("light::2.0", "UsdLuxCylinderLight"),
    "dome": ("domelight::3.0", None),
}
"""라이트 종류 -> (LOP 노드 타입, lighttype 토큰). 실측으로 확인한 토큰이다.

돔은 `light::2.0` 의 lighttype 에 없고 전용 노드다. 22.0 의 `domelight::3.0` 은
`UsdLuxDomeLight_1` 프림을 만든다(새 돔 스키마).
"""

LIGHT_PROPERTIES: dict[str, tuple[str, str]] = {
    "intensity": ("inputs:intensity", "float"),
    "exposure": ("inputs:exposure", "float"),
    "color": ("inputs:color", "color3f"),
    "diffuse": ("inputs:diffuse", "float"),
    "specular": ("inputs:specular", "float"),
    "normalize": ("inputs:normalize", "bool"),
    "color_temperature": ("inputs:colorTemperature", "float"),
    "enable_color_temperature": ("inputs:enableColorTemperature", "bool"),
    "radius": ("inputs:radius", "float"),
    "width": ("inputs:width", "float"),
    "height": ("inputs:height", "float"),
    "length": ("inputs:length", "float"),
    "angle": ("inputs:angle", "float"),
    "cone_angle": ("inputs:shaping:cone:angle", "float"),
    "texture": ("inputs:texture:file", "asset"),
}
"""툴 인자 이름 -> (USD 속성 이름, USD 타입).

모양 관련 속성은 라이트 종류마다 의미가 있는 것이 다르다. 없는 속성을 걸면
USD 가 그냥 받아 두지만 렌더러는 무시하므로, 걸기 전에 프림 타입을 확인한다.
"""

_SHAPE_PROPERTIES: dict[str, set[str]] = {
    "SphereLight": {"radius"},
    "DiskLight": {"radius"},
    "RectLight": {"width", "height", "texture"},
    "CylinderLight": {"radius", "length"},
    "DistantLight": {"angle"},
    "DomeLight": {"texture"},
    "DomeLight_1": {"texture"},
}
"""프림 타입별로 의미가 있는 모양 속성. 나머지는 공통(intensity 등)이다."""


def _set_usd_parm(node: hou.Node, usd_name: str, value: Any) -> None:
    """USD 속성 이름으로 LOP 파라미터를 건다.

    Houdini 는 `inputs:intensity` 같은 이름을 punycode 로 인코딩해서 파라미터
    이름으로 쓴다(`xn__inputsintensity_i0a`). 인코딩된 이름을 하드코딩하면
    Houdini 가 스키마를 손볼 때 조용히 깨지므로 `hou.text.encode` 로 만든다.
    """
    encoded = hou.text.encode(usd_name)
    if isinstance(value, (list, tuple)):
        tuple_parm = node.parmTuple(encoded)
        if tuple_parm is None:
            raise ValueError(
                f"{node.type().name()} 에 {usd_name!r} 파라미터가 없습니다. "
                f"이 라이트 종류에는 없는 속성일 수 있습니다."
            )
        tuple_parm.set(tuple(value))
        return

    parm = node.parm(encoded)
    if parm is None:
        raise ValueError(
            f"{node.type().name()} 에 {usd_name!r} 파라미터가 없습니다. "
            f"이 라이트 종류에는 없는 속성일 수 있습니다."
        )
    parm.set(value)


def _light_brief(prim) -> dict[str, Any]:
    """라이트 프림 하나를 요약한다."""
    from pxr import UsdGeom, UsdLux

    light = UsdLux.LightAPI(prim)
    xformable = UsdGeom.Xformable(prim)
    matrix = xformable.ComputeLocalToWorldTransform(0) if xformable else None

    return {
        "path": str(prim.GetPath()),
        "name": prim.GetName(),
        "type": str(prim.GetTypeName()),
        "intensity": light.GetIntensityAttr().Get(),
        "exposure": light.GetExposureAttr().Get(),
        "color": jsonify(light.GetColorAttr().Get()),
        "visibility": str(UsdGeom.Imageable(prim).ComputeVisibility()),
        "active": prim.IsActive(),
        "translate": list(matrix.ExtractTranslation()) if matrix else None,
    }


@tool()
def list_lights(lop: str = DEFAULT_LOP, limit: int = 200) -> dict[str, Any]:
    """스테이지의 라이트 전부 - 타입, 세기, 색, 위치.

    `UsdLux.LightAPI` 가 붙은 프림을 찾는다. 그래서 LOP 노드로 만든 라이트뿐
    아니라 레퍼런스로 들어온 라이트, 다른 DCC 가 만든 라이트도 다 나온다.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        limit: 돌려줄 라이트 수 상한.
    """
    from pxr import Usd, UsdLux

    node = resolve_lop(lop)
    stage = stage_of(node)

    lights = []
    truncated = False
    for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.PrimDefaultPredicate):
        if not prim.HasAPI(UsdLux.LightAPI):
            continue
        if len(lights) >= limit:
            truncated = True
            break
        lights.append(_light_brief(prim))

    return {
        "lop": node.path(),
        "count": len(lights),
        "truncated": truncated,
        "lights": lights,
    }


@tool()
def light_info(lop: str = DEFAULT_LOP, primpath: str = "") -> dict[str, Any]:
    """라이트 하나의 전부 - 세기, 색, 모양, 셰이핑, 그림자, 변환.

    Args:
        lop: LOP 노드 또는 LOP 네트워크 경로.
        primpath: 라이트 프림 경로. list_lights 로 찾는다.
    """
    from pxr import UsdGeom, UsdLux

    if not primpath:
        raise ValueError(
            "라이트 프림 경로를 주세요. 경로를 모르면 list_lights 를 먼저 부릅니다."
        )

    node = resolve_lop(lop)
    prim = prim_at(stage_of(node), primpath)

    light = UsdLux.LightAPI(prim)
    if not light:
        raise ValueError(
            f"{primpath} 는 라이트가 아닙니다(타입 {prim.GetTypeName()}). "
            f"list_lights 로 실제 라이트 경로를 확인하세요."
        )

    info = _light_brief(prim)
    info["lop"] = node.path()

    # 스키마가 정의한 속성을 전부 훑는다. 라이트 종류마다 다르므로 프림에서 얻는다.
    properties: dict[str, Any] = {}
    for attr in prim.GetAttributes():
        name = attr.GetName()
        if name.startswith("inputs:"):
            properties[name] = jsonify(attr.Get())
    info["properties"] = properties

    shaping = UsdLux.ShapingAPI(prim)
    if shaping and prim.HasAPI(UsdLux.ShapingAPI):
        info["shaping"] = {
            "cone_angle": shaping.GetShapingConeAngleAttr().Get(),
            "cone_softness": shaping.GetShapingConeSoftnessAttr().Get(),
            "focus": shaping.GetShapingFocusAttr().Get(),
            "ies_file": jsonify(shaping.GetShapingIesFileAttr().Get()),
        }

    shadow = UsdLux.ShadowAPI(prim)
    if shadow and prim.HasAPI(UsdLux.ShadowAPI):
        info["shadow"] = {
            "enable": shadow.GetShadowEnableAttr().Get(),
            "color": jsonify(shadow.GetShadowColorAttr().Get()),
            "distance": shadow.GetShadowDistanceAttr().Get(),
        }

    xformable = UsdGeom.Xformable(prim)
    if xformable:
        info["xform_ops"] = [op.GetOpName() for op in xformable.GetOrderedXformOps()]
        info["world_transform"] = jsonify(
            xformable.ComputeLocalToWorldTransform(0)
        )

    return info


@tool()
@undoable("Create light")
def create_light(
    lop: str,
    light_type: str,
    primpath: str,
    comment: str,
    intensity: float | None = None,
    exposure: float | None = None,
    color: list[float] | None = None,
    translate: list[float] | None = None,
    rotate: list[float] | None = None,
    texture: str | None = None,
    node_name: str | None = None,
) -> dict[str, Any]:
    """UsdLux 라이트를 만든다.

    이름은 역할이 드러나게 짓는다 - `light1` 이 아니라 `key_light`,
    `rim_light`, `env_dome` 처럼. 프림 경로도 마찬가지다.

    만든 뒤 스테이지에서 실제 값을 읽어 돌려주므로, 세기가 걸렸는지 바로 알 수
    있다.

    Args:
        lop: 입력이 될 LOP 노드 경로. 네트워크를 주면 디스플레이 노드 뒤에 붙는다.
        light_type: distant, sphere, point, disk, rect, cylinder, dome 중 하나.
        primpath: 만들 라이트 프림 경로. 예: /world/lights/key
        comment: 이 라이트가 무엇을 하는지. 노드 코멘트로 남는다. 영어로 쓴다.
        intensity: 세기.
        exposure: 노출(스톱). 세기에 2^exposure 가 곱해진다.
        color: RGB. 예: [1.0, 0.95, 0.9]
        translate: 위치 [x, y, z].
        rotate: 회전 [rx, ry, rz] (도).
        texture: 돔/렉트 라이트의 텍스처(HDRI) 파일 경로.
        node_name: 만들 노드 이름. 생략하면 프림 이름에서 짓는다.
    """
    if light_type not in LIGHT_TYPES:
        raise ValueError(
            f"그런 라이트 종류가 없습니다: {light_type!r}. "
            f"{', '.join(sorted(LIGHT_TYPES))} 중 하나를 주세요."
        )

    node = resolve_lop(lop)
    node_type, token = LIGHT_TYPES[light_type]

    leaf = primpath.rstrip("/").rsplit("/", 1)[-1] or f"{light_type}_light"
    created, _ = insert_lop(node, node_type, node_name or leaf, comment)
    created.parm("primpath").set(primpath)
    if token is not None:
        created.parm("lighttype").set(token)

    if intensity is not None:
        _set_usd_parm(created, "inputs:intensity", intensity)
    if exposure is not None:
        _set_usd_parm(created, "inputs:exposure", exposure)
    if color is not None:
        _set_usd_parm(created, "inputs:color", color)
    if texture is not None:
        _set_usd_parm(created, "inputs:texture:file", texture)

    # 벡터 파라미터는 성분 이름으로 건다(t 가 아니라 tx/ty/tz).
    for values, parms in ((translate, ("tx", "ty", "tz")), (rotate, ("rx", "ry", "rz"))):
        if values is None:
            continue
        if len(values) != 3:
            raise ValueError(
                f"translate 와 rotate 는 값이 셋이어야 합니다: {values!r}"
            )
        for value, parm in zip(values, parms):
            created.parm(parm).set(value)

    prim = prim_at(stage_of(created), primpath)
    return node_report(created, {"light": _light_brief(prim)})


@tool()
@undoable("Create light rig")
def create_light_rig(
    lop: str,
    comment: str,
    root: str = "/lights",
    key_intensity: float = 3.0,
    fill_intensity: float = 1.0,
    rim_intensity: float = 2.0,
    dome_texture: str | None = None,
    dome_intensity: float = 0.3,
) -> dict[str, Any]:
    """3점 조명(key / fill / rim)과 환경 돔을 한 번에 만든다.

    셸프의 라이트 리그와 같은 배치다. 키는 앞 위 오른쪽, 필은 앞 왼쪽 약하게,
    림은 뒤에서. 전부 디스턴트 라이트라 씬 크기에 무관하게 작동한다.

    돔은 `dome_texture` 를 주면 HDRI 로, 주지 않으면 균일한 환경광으로 만든다.

    Args:
        lop: 입력이 될 LOP 노드 경로.
        comment: 이 리그가 무엇을 비추는지. 노드 코멘트로 남는다. 영어로 쓴다.
        root: 라이트를 담을 프림 경로. 예: /world/lights
        key_intensity: 키 라이트 세기.
        fill_intensity: 필 라이트 세기.
        rim_intensity: 림 라이트 세기.
        dome_texture: 환경 돔에 걸 HDRI 파일 경로. 없으면 균일한 색.
        dome_intensity: 환경 돔 세기.
    """
    node = resolve_lop(lop)
    base = root.rstrip("/")

    plan = [
        ("key_light", "distant", key_intensity, (-35.0, 40.0, 0.0), "Key light"),
        ("fill_light", "distant", fill_intensity, (-15.0, -50.0, 0.0), "Fill light"),
        ("rim_light", "distant", rim_intensity, (-25.0, 170.0, 0.0), "Rim light"),
    ]

    current = node
    created: list[str] = []
    for name, kind, intensity, rotate, label in plan:
        node_type, token = LIGHT_TYPES[kind]
        light, _ = insert_lop(current, node_type, name, f"{label} of the 3-point rig")
        light.parm("primpath").set(f"{base}/{name}")
        light.parm("lighttype").set(token)
        _set_usd_parm(light, "inputs:intensity", intensity)
        for value, parm in zip(rotate, ("rx", "ry", "rz")):
            light.parm(parm).set(value)
        created.append(light.path())
        current = light

    dome, _ = insert_lop(
        current, LIGHT_TYPES["dome"][0], "env_dome", "Environment dome of the rig"
    )
    dome.parm("primpath").set(f"{base}/env_dome")
    _set_usd_parm(dome, "inputs:intensity", dome_intensity)
    if dome_texture:
        _set_usd_parm(dome, "inputs:texture:file", dome_texture)
    created.append(dome.path())

    # 리그 전체를 설명하는 코멘트는 마지막 노드에 단다. 여기가 리그의 출력이다.
    dome.setComment(comment)
    dome.setGenericFlag(hou.nodeFlag.DisplayComment, True)

    stage = stage_of(dome)
    from pxr import Usd, UsdLux

    lights = [
        _light_brief(prim)
        for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.PrimDefaultPredicate)
        if prim.HasAPI(UsdLux.LightAPI)
    ]

    return node_report(dome, {"root": base, "nodes": created, "lights": lights})


@tool()
@undoable("Set light properties")
def set_light(
    lop: str,
    primpath: str,
    comment: str,
    properties: dict[str, Any] | None = None,
    node_name: str | None = None,
) -> dict[str, Any]:
    """이미 있는 라이트 프림의 속성을 바꾼다. `pythonscript` LOP 을 끼워 넣는다.

    라이트를 만든 LOP 노드를 찾아 파라미터를 고치는 방식이 아니다. 그래서
    레퍼런스로 들어온 라이트나 다른 DCC 가 만든 라이트도 그대로 고칠 수 있다.

    쓸 수 있는 속성 이름은 intensity, exposure, color, diffuse, specular,
    normalize, color_temperature, enable_color_temperature, radius, width,
    height, length, angle, cone_angle, texture 다.

    Args:
        lop: 입력이 될 LOP 노드 경로.
        primpath: 고칠 라이트 프림 경로.
        comment: 왜 이렇게 바꾸는지. 노드 코멘트로 남는다. 영어로 쓴다.
        properties: 속성 이름과 값. 예: {"intensity": 5.0, "color": [1, 0.9, 0.8]}
        node_name: 만들 노드 이름. 생략하면 프림 이름에서 짓는다.
    """
    from pxr import UsdLux

    if not properties:
        raise ValueError(
            "바꿀 속성을 주세요. 예: {\"intensity\": 5.0, \"exposure\": 1.0}. "
            f"쓸 수 있는 이름: {', '.join(sorted(LIGHT_PROPERTIES))}"
        )

    node = resolve_lop(lop)
    prim = prim_at(stage_of(node), primpath)
    if not UsdLux.LightAPI(prim):
        raise ValueError(
            f"{primpath} 는 라이트가 아닙니다(타입 {prim.GetTypeName()}). "
            f"list_lights 로 실제 라이트 경로를 확인하세요."
        )

    prim_type = str(prim.GetTypeName())
    shape_only = {name for names in _SHAPE_PROPERTIES.values() for name in names}
    meaningful = _SHAPE_PROPERTIES.get(prim_type, set())

    spec = []
    ignored = []
    for key, value in properties.items():
        if key not in LIGHT_PROPERTIES:
            raise ValueError(
                f"그런 라이트 속성이 없습니다: {key!r}. "
                f"쓸 수 있는 이름: {', '.join(sorted(LIGHT_PROPERTIES))}"
            )
        usd_name, type_name = LIGHT_PROPERTIES[key]
        if key in shape_only and key not in meaningful:
            # USD 는 받아 두지만 렌더러가 무시한다. 조용히 넘어가지 않고 알린다.
            ignored.append(key)
        spec.append(attr_spec(str(prim.GetPath()), usd_name, type_name, value))

    leaf = primpath.rstrip("/").rsplit("/", 1)[-1] or "light"
    created = author_attributes(node, node_name or f"tune_{leaf}", comment, spec)
    edited = created["node"]

    result = node_report(
        edited,
        {
            "path": primpath,
            "light": _light_brief(prim_at(stage_of(edited), primpath)),
            "rewired": created["rewired"],
        },
    )
    if ignored:
        result["warnings"] = list(result["warnings"]) + [
            f"{prim_type} ignores these shape properties: {', '.join(ignored)}"
        ]
    return result
