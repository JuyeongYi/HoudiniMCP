"""`hou.ParmTemplate` 을 만들고 읽는 공통 헬퍼. 툴 모듈이 아니다.

스페어 파라미터를 붙이는 일(`parmedit`)과 HDA 인터페이스를 짜는 일
(`houdini_mcp_hda`)은 같은 것을 필요로 한다 - 타입 이름을 받아 알맞은
`hou.ParmTemplate` 서브클래스를 만드는 것. 두 곳에서 각각 만들면 곧 갈라지므로
여기 한 번만 둔다.

**문자열 조립을 하지 않는다.** 기존 구현들은 파라미터를 붙일 때 `.ds` 파일
문법이나 HScript `opparm` 문자열을 짜 맞춘다. 그러면 이스케이프가 새고, 타입이
틀려도 실행하기 전까지 모른다. 여기서는 서브클래스 생성자만 쓴다.

TOOL_MODULES 에 넣지 않는다. 여기에는 툴이 없다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/ParmTemplate.html
"""

from __future__ import annotations

from typing import Any

import hou

# 툴에서 받는 종류 이름 -> 설명. 에러 메시지에 그대로 쓴다.
KINDS: dict[str, str] = {
    "float": "실수. size 로 벡터가 된다 (3 이면 tx/ty/tz 처럼 성분이 셋)",
    "int": "정수",
    "string": "문자열. string_type 으로 파일/노드 경로가 된다",
    "toggle": "체크박스. default 는 True/False",
    "menu": "고정 메뉴. menu_items 가 필요하다",
    "button": "누르면 script_callback 이 도는 버튼",
    "ramp_float": "값 램프",
    "ramp_color": "색 램프",
    "separator": "구분선. 값이 없다",
}

STRING_TYPES = {
    "regular": hou.stringParmType.Regular,
    "file": hou.stringParmType.FileReference,
    "node": hou.stringParmType.NodeReference,
    "node_list": hou.stringParmType.NodeReferenceList,
}


def _kind_error(kind: str) -> ValueError:
    lines = [f"  {name:<12} {desc}" for name, desc in KINDS.items()]
    return ValueError(
        f"쓸 수 없는 파라미터 종류입니다: {kind!r}\n"
        + "쓸 수 있는 것:\n"
        + "\n".join(lines)
    )


def _as_tuple(default: Any, size: int, cast) -> tuple:
    """default 를 성분 수에 맞춘 튜플로 편다.

    하나만 주면 모든 성분에 같은 값이 들어간다. 벡터 파라미터에 값을 하나만
    주는 일이 흔해서 그쪽을 편하게 한다.
    """
    if default is None:
        return ()
    if isinstance(default, (list, tuple)):
        values = list(default)
        if len(values) != size:
            raise ValueError(
                f"default 가 {len(values)}개인데 size 는 {size} 입니다. "
                f"성분 수를 맞추거나 값을 하나만 주세요(모든 성분에 같은 값이 들어갑니다)."
            )
        return tuple(cast(v) for v in values)
    return tuple(cast(default) for _ in range(size))


def build_parm_template(
    kind: str,
    name: str,
    label: str,
    size: int = 1,
    default: Any = None,
    min_value: float | None = None,
    max_value: float | None = None,
    menu_items: list[str] | None = None,
    menu_labels: list[str] | None = None,
    string_type: str = "regular",
    help_text: str | None = None,
    disable_when: str | None = None,
) -> hou.ParmTemplate:
    """종류 이름으로 `hou.ParmTemplate` 을 만든다.

    Args:
        kind: KINDS 의 키. float / int / string / toggle / menu / button /
            ramp_float / ramp_color / separator.
        name: 파라미터 내부 이름. 식과 set_parms 가 이걸 쓴다.
        label: UI 에 뜨는 이름. Houdini UI 에 그대로 나오므로 영어로 쓴다.
        size: 성분 수. float/int/string 에만 의미가 있다.
        default: 기본값. 벡터면 목록으로 주거나 값 하나로 전부 채운다.
        min_value: 슬라이더 최솟값 (float/int).
        max_value: 슬라이더 최댓값 (float/int).
        menu_items: menu 종류일 때 고를 값들.
        menu_labels: 그 값들의 표시 이름. 생략하면 값을 그대로 쓴다.
        string_type: string 종류일 때 regular / file / node / node_list.
        help_text: 파라미터 툴팁.
        disable_when: 비활성 조건식. 예: `{ usefile == 0 }`

    Returns:
        hou.ParmTemplate 서브클래스 인스턴스.
    """
    if kind not in KINDS:
        raise _kind_error(kind)
    if not name or not name.strip():
        raise ValueError("name 이 비어 있습니다. 식에서 쓸 내부 이름을 주세요.")
    if size < 1:
        raise ValueError(f"size 는 1 이상이어야 합니다: {size}")

    # 모든 서브클래스가 공통으로 받는 것만 여기 모은다.
    common: dict[str, Any] = {}
    if help_text:
        common["help"] = help_text
    if disable_when:
        common["disable_when"] = disable_when

    if kind == "separator":
        return hou.SeparatorParmTemplate(name, **common)

    if kind == "toggle":
        return hou.ToggleParmTemplate(
            name, label, default_value=bool(default), **common
        )

    if kind == "button":
        return hou.ButtonParmTemplate(name, label, **common)

    if kind in ("ramp_float", "ramp_color"):
        ramp_type = (
            hou.rampParmType.Float if kind == "ramp_float" else hou.rampParmType.Color
        )
        return hou.RampParmTemplate(name, label, ramp_type, **common)

    if kind == "menu":
        if not menu_items:
            raise ValueError(
                "menu 종류는 menu_items 가 필요합니다. 고를 값들을 목록으로 주세요."
            )
        return hou.MenuParmTemplate(
            name,
            label,
            tuple(menu_items),
            menu_labels=tuple(menu_labels or menu_items),
            default_value=int(default) if default is not None else 0,
            **common,
        )

    if kind == "string":
        if string_type not in STRING_TYPES:
            raise ValueError(
                f"string_type 은 {', '.join(STRING_TYPES)} 중 하나여야 합니다: "
                f"{string_type!r}"
            )
        return hou.StringParmTemplate(
            name,
            label,
            size,
            default_value=_as_tuple(default, size, str) or ("",) * size,
            string_type=STRING_TYPES[string_type],
            menu_items=tuple(menu_items or ()),
            menu_labels=tuple(menu_labels or menu_items or ()),
            **common,
        )

    # float / int - 범위는 주지 않으면 생성자 기본값을 그대로 둔다.
    cast = float if kind == "float" else int
    numeric: dict[str, Any] = dict(common)
    if min_value is not None:
        numeric["min"] = cast(min_value)
    if max_value is not None:
        numeric["max"] = cast(max_value)
    cls = hou.FloatParmTemplate if kind == "float" else hou.IntParmTemplate
    return cls(
        name,
        label,
        size,
        default_value=_as_tuple(default, size, cast),
        **numeric,
    )


def describe_parm_template(template: hou.ParmTemplate) -> dict[str, Any]:
    """템플릿을 사람이 읽을 수 있는 요약으로. 붙인 뒤 확인용으로 돌려준다."""
    entry: dict[str, Any] = {
        "name": template.name(),
        "label": template.label(),
        "kind": type(template).__name__.replace("ParmTemplate", "").lower(),
    }
    for key, getter in (
        ("size", "numComponents"),
        ("default", "defaultValue"),
        ("min", "minValue"),
        ("max", "maxValue"),
    ):
        method = getattr(template, getter, None)
        if method is None:
            continue
        try:
            value = method()
        except hou.OperationFailed:
            continue
        entry[key] = list(value) if isinstance(value, tuple) else value

    items = getattr(template, "menuItems", None)
    if items is not None:
        try:
            values = list(items())
        except hou.OperationFailed:
            values = []
        if values:
            entry["menu"] = values
    return entry


def component_names(template: hou.ParmTemplate) -> list[str]:
    """템플릿이 만들 실제 파라미터 이름들.

    성분이 여럿이면 `size1`/`size2` 처럼 이름이 갈라진다. set_parms 에 어떤
    이름을 줘야 하는지 알려 주려면 이게 필요하다. nodetypes 모듈이 같은 일을
    하지만 그쪽은 노드 타입에서, 여기는 템플릿에서 뽑는다.
    """
    getter = getattr(template, "numComponents", None)
    count = getter() if getter else 1
    if count <= 1:
        return [template.name()]
    scheme = str(template.namingScheme()).rsplit(".", 1)[-1]
    suffix = {
        "Base1": lambda i: str(i + 1),
        "XYZW": lambda i: "xyzw"[i],
        "XYWH": lambda i: "xywh"[i],
        "UVW": lambda i: "uvw"[i],
        "RGBA": lambda i: "rgba"[i],
        "MinMax": lambda i: ("min", "max")[i],
        "MaxMin": lambda i: ("max", "min")[i],
        "StartEnd": lambda i: ("start", "end")[i],
        "BeginEnd": lambda i: ("begin", "end")[i],
    }.get(scheme)
    if suffix is None:
        return [template.name()]
    return [template.name() + suffix(i) for i in range(count)]
