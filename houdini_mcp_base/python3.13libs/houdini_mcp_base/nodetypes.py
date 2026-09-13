"""노드 타입을 만들기 전에 알아보는 툴들.

노드를 만들어 봐야만 파라미터 이름을 알 수 있으면 작업이 느려진다. 실제로 성을
만들 때 `tube` 의 `rad1` 이 위쪽인지 아래쪽인지 몰라 원뿔을 거꾸로 붙였고,
Houdini 문서에는 `rad1`/`rad2` 가 아예 없다 - 라벨 "Radius" 하나뿐이다.

여기 있는 툴은 노드를 만들지 않고 타입 정의에서 직접 읽는다. 씬을 건드리지
않으므로 마음껏 조회해도 된다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/index.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool

from . import paths

MAX_TYPES = 200
"""한 번에 돌려줄 노드 타입 수 상한. Sop 만 1,690개라 전부 주면 읽히지 않는다."""

MAX_MENU = 40

# 벡터 파라미터의 성분 접미사. 템플릿은 튜플 이름(`rad`)만 주므로 실제 이름
# (`rad1`, `rad2`)을 이 규칙으로 편다. Sop 1,690개 전수로 검증했다.
SUFFIX = {
    "Base1": lambda i: str(i + 1),
    "XYZW": lambda i: "xyzw"[i],
    "XYWH": lambda i: "xywh"[i],
    "UVW": lambda i: "uvw"[i],
    "RGBA": lambda i: "rgba"[i],
    "MinMax": lambda i: ("min", "max")[i],
    "MaxMin": lambda i: ("max", "min")[i],
    "StartEnd": lambda i: ("start", "end")[i],
    "BeginEnd": lambda i: ("begin", "end")[i],
}

UI_ONLY = ("Separator", "Label", "FolderSet")
MULTIPARM_FOLDERS = ("MultiparmBlock", "ScrollingMultiparmBlock", "TabbedMultiparmBlock")


def _category(name: str) -> Any:
    cats = hou.nodeTypeCategories()
    if name not in cats:
        raise ValueError(
            f"그런 카테고리가 없습니다: {name}. 쓸 수 있는 것: {', '.join(sorted(cats))}"
        )
    return cats[name]


def _find_type(category: str, type_name: str) -> Any:
    types = _category(category).nodeTypes()
    if type_name in types:
        return types[type_name]
    # 버전 접미사를 붙인 이름(box::2.0)만 있는 경우를 짚어 준다.
    close = sorted(n for n in types if n.split("::")[0] == type_name)
    if close:
        raise ValueError(
            f"{category}/{type_name} 은 없고 버전이 붙은 것만 있습니다: {', '.join(close[:5])}"
        )
    raise ValueError(f"{category}/{type_name} 노드 타입이 없습니다.")


def _expand(template: Any) -> tuple[list[str], str | None]:
    count = template.numComponents()
    if count <= 1:
        return [template.name()], None
    getter = getattr(template, "namingScheme", None)
    if getter is None:
        return [template.name()], None
    scheme = str(getter()).rsplit(".", 1)[-1]
    maker = SUFFIX.get(scheme)
    return ([template.name() + maker(i) for i in range(count)], scheme) if maker else (
        [template.name()], scheme
    )


def _is_multiparm(entry: Any) -> bool:
    getter = getattr(entry, "folderType", None)
    if getter is None:
        return False
    try:
        return str(getter()).rsplit(".", 1)[-1] in MULTIPARM_FOLDERS
    except hou.OperationFailed:
        return False


def _walk(entries: Any, folder: tuple[str, ...] = (), multi: bool = False):
    for entry in entries:
        if entry.type() == hou.parmTemplateType.Folder:
            if _is_multiparm(entry):
                yield "/".join(folder), entry, False
            yield from _walk(entry.parmTemplates(), folder + (entry.label(),),
                             multi or _is_multiparm(entry))
        else:
            yield "/".join(folder), entry, multi


def _describe(template: Any, folder: str, multi: bool, detailed: bool) -> list[dict[str, Any]]:
    default_getter = getattr(template, "defaultValue", None)
    default = default_getter() if default_getter else None

    menu = None
    if detailed and hasattr(template, "menuItems"):
        try:
            items = list(template.menuItems() or [])
        except hou.OperationFailed:
            items = []
        if items:
            labels = list(template.menuLabels() or [])
            menu = [{"value": v, "label": labels[i] if i < len(labels) else v}
                    for i, v in enumerate(items[:MAX_MENU])]

    conditionals = None
    if detailed:
        getter = getattr(template, "conditionals", None)
        if getter:
            try:
                raw = getter()
            except hou.OperationFailed:
                raw = None
            if raw:
                conditionals = {str(k).rsplit(".", 1)[-1]: v for k, v in raw.items()}

    names, scheme = _expand(template)
    out = []
    for index, name in enumerate(names):
        record: dict[str, Any] = {
            "name": name,
            "label": template.label(),
            "type": type(template).__name__.replace("ParmTemplate", "").lower(),
        }
        if isinstance(default, (tuple, list)):
            record["default"] = default[index] if index < len(default) else None
        elif default is not None:
            record["default"] = default
        if len(names) > 1:
            record["tuple"] = template.name()
            record["component"] = index
            record["naming_scheme"] = scheme
        if folder:
            record["folder"] = folder
        if multi:
            record["multiparm"] = True
        if menu:
            record["menu"] = menu
        if conditionals:
            record["conditionals"] = conditionals
        out.append(record)
    return out


_LABEL_HOSTS = {
    "Sop": ("/obj", "geo"),
    "Object": ("/obj", None),
    "Dop": ("/obj", "dopnet"),
    "Chop": ("/obj", "chopnet"),
    "Top": ("/obj", "topnet"),
    "Lop": ("/stage", None),
    "Driver": ("/out", None),
}
"""컴파일 노드의 라벨을 읽으려고 임시 인스턴스를 놓을 자리. 카테고리 -> (부모, 감쌀 네트워크)."""


def _port_labels(node_type: Any) -> dict[str, Any]:
    """입출력 포트 라벨.

    노드 타입에는 라벨을 주는 API 가 없다(실측 - inputLabels 는 노드 인스턴스에만
    있다). HDA 는 DialogScript 의 inputlabel/outputlabel 줄에서 읽고, 컴파일 노드는
    Undo 를 끈 채 임시 노드를 놓아 읽은 뒤 지운다. DialogScript 에는 쓰이지 않는
    "Sub-Network Input #4" 같은 줄도 있어 최대 포트 수로 자른다.
    """
    definition = node_type.definition()
    if definition is not None:
        section = definition.sections().get("DialogScript")
        text = section.contents() if section is not None else ""
        inputs = _dialog_labels(text, "inputlabel", node_type.maxNumInputs())
        outputs = _dialog_labels(text, "outputlabel", node_type.maxNumOutputs())
        # 한쪽만 적힌 HDA 가 흔하다(connectadjacentpieces 는 inputlabel 만 있다).
        # 빈 쪽을 []로 두면 출력이 없는 노드로 읽히므로 임시 노드로 채운다.
        missing_in = not inputs and node_type.maxNumInputs() > 0
        missing_out = not outputs and node_type.maxNumOutputs() > 0
        if not missing_in and not missing_out:
            return {"input_labels": inputs, "output_labels": outputs}
        if inputs or outputs:
            placed = _placed_labels(node_type)
            return {
                "input_labels": inputs if not missing_in else placed["input_labels"],
                "output_labels": outputs if not missing_out else placed["output_labels"],
            }

    return _placed_labels(node_type)


def _placed_labels(node_type: Any) -> dict[str, Any]:
    """Undo 를 끈 채 임시 노드를 놓아 라벨을 읽고 지운다."""

    host = _LABEL_HOSTS.get(node_type.category().name())
    if host is None:
        return {"input_labels": None, "output_labels": None}
    root_path, wrapper = host
    root = hou.node(root_path)
    if root is None:
        return {"input_labels": None, "output_labels": None}
    container = None
    try:
        with hou.undos.disabler():
            if wrapper is not None:
                container = root.createNode(wrapper, "hmcp_labels_tmp")
                parent = container
            else:
                parent = root
            node = parent.createNode(node_type.name(), "hmcp_labels_tmp_node")
            labels = {
                "input_labels": list(node.inputLabels())[: max(node_type.maxNumInputs(), 0)][:16],
                "output_labels": list(node.outputLabels())[:16],
            }
            if container is None:
                node.destroy()
        return labels
    except hou.Error:
        return {"input_labels": None, "output_labels": None}
    finally:
        if container is not None:
            with hou.undos.disabler():
                container.destroy()


def _dialog_labels(text: str, keyword: str, count: int) -> list[str]:
    import re

    labels: dict[int, str] = {}
    for match in re.finditer(rf"^\s*{keyword}\s+(\d+)\s+(.+?)\s*$", text, re.M):
        index = int(match.group(1)) - 1
        if 0 <= index < count:
            labels[index] = match.group(2).strip().strip('"')
    if not labels:
        return []
    return [labels.get(i, "") for i in range(min(count, max(labels) + 1))]


def _origin(node_type: Any) -> dict[str, Any]:
    """배포 출처. definition() 이 None 이면 빌트인이라는 단순 분류로는 안 된다.

    SideFX 공식 노드 상당수가 $HFS 안의 HDA 로 배포되므로, 외부 패키지와
    구분하려면 라이브러리 경로를 봐야 한다.
    """
    definition = node_type.definition()
    if definition is None:
        return {"source": "builtin_compiled"}
    library = Path(definition.libraryFilePath())
    if any("sidefx_packages" in part for part in library.parts):
        source = "package_hda"
    elif paths.is_inside(library, paths.to_path("$HFS")):
        source = "builtin_hda"
    else:
        source = "user_hda"
    return {"source": source, "library": library.name}


@tool()
def list_node_types(
    category: str = "Sop", pattern: str = "*", include_hidden: bool = False
) -> dict[str, Any]:
    """카테고리에서 쓸 수 있는 노드 타입을 찾는다.

    무슨 노드를 써야 할지 모를 때 먼저 부른다. 이름만으로 찾지 못하면 라벨로도
    걸린다.

    Args:
        category: Sop / Object / Dop / Cop / Top / Chop / Driver / Lop / Vop 등.
        pattern: 이름이나 라벨에 대한 와일드카드. 예: "copy*", "*scatter*"
        include_hidden: 숨김·폐기 노드까지 포함한다.
    """
    import fnmatch

    types = _category(category).nodeTypes()
    matched = []
    for name, node_type in sorted(types.items()):
        if not include_hidden and (node_type.hidden() or node_type.deprecated()):
            continue
        label = node_type.description()
        if not (fnmatch.fnmatch(name, pattern) or fnmatch.fnmatchcase(label.lower(), pattern.lower())):
            continue
        entry = {"name": name, "label": label}
        if node_type.deprecated():
            entry["deprecated"] = True
        if node_type.hidden():
            entry["hidden"] = True
        matched.append(entry)

    total = len(matched)
    return {
        "category": category,
        "pattern": pattern,
        "total": total,
        "types": matched[:MAX_TYPES],
        "truncated": total > MAX_TYPES,
    }


@tool()
def node_type_info(
    category: str, type_name: str, parm_pattern: str = "*", detailed: bool = False
) -> dict[str, Any]:
    """노드를 만들기 전에 그 타입의 파라미터와 입출력을 본다.

    노드를 만들지 않으므로 씬을 건드리지 않는다. 벡터 파라미터는 성분 이름으로
    펼쳐서 준다 - `rad` 가 아니라 `rad1`/`rad2` 로 나오므로 set_parms 에 그대로
    쓸 수 있다.

    Args:
        category: Sop / Object / Dop 등.
        type_name: 노드 타입 이름. 예: tube, copytopoints::2.0
        parm_pattern: 파라미터 이름 와일드카드. 공백으로 여러 개를 줄 수 있다.
            예: "rad* height cols". 기본은 전부.
        detailed: True 면 메뉴 항목과 조건부 활성식(DisableWhen)까지 준다.

    입출력 포트 라벨도 준다. RBD Bullet Solver 처럼 입력이 여럿인 노드는 몇 번이
    제약이고 몇 번이 충돌체인지 모르고 이으면 조용히 틀린다.
    """
    import fnmatch

    patterns = parm_pattern.split() or ["*"]
    node_type = _find_type(category, type_name)
    parms: list[dict[str, Any]] = []
    for folder, template, multi in _walk(node_type.parmTemplateGroup().entries()):
        if type(template).__name__.replace("ParmTemplate", "") in UI_ONLY:
            continue
        for record in _describe(template, folder, multi, detailed):
            if any(fnmatch.fnmatch(record["name"], p) for p in patterns):
                parms.append(record)

    info: dict[str, Any] = {
        "node_type": f"{category}/{node_type.name()}",
        "label": node_type.description(),
        "inputs": {"min": node_type.minNumInputs(), "max": node_type.maxNumInputs()},
        "outputs": node_type.maxNumOutputs(),
        **_port_labels(node_type),
        "deprecated": bool(node_type.deprecated()),
        "hidden": bool(node_type.hidden()),
        "parm_count": len(parms),
        "parms": parms,
    }
    info.update(_origin(node_type))
    if node_type.deprecated():
        try:
            info["deprecation"] = node_type.deprecationInfo()
        except hou.OperationFailed:
            pass
    return info


@tool()
def node_type_help(category: str, type_name: str, max_chars: int = 4000) -> dict[str, Any]:
    """노드 타입에 딸린 내장 도움말 텍스트.

    Args:
        category: Sop / Object / Dop 등.
        type_name: 노드 타입 이름.
        max_chars: 잘라낼 길이.
    """
    node_type = _find_type(category, type_name)
    text = ""
    try:
        text = node_type.embeddedHelp() or ""
    except hou.OperationFailed:
        text = ""
    url = ""
    try:
        url = node_type.defaultHelpUrl() or ""
    except hou.OperationFailed:
        pass
    return {
        "node_type": f"{category}/{node_type.name()}",
        "label": node_type.description(),
        "help_url": url,
        "help": text[:max_chars],
        "truncated": len(text) > max_chars,
    }
