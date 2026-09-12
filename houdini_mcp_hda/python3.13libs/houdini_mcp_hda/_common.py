"""팩 전체가 쓰는 헬퍼. 툴은 여기 없다.

네 가지를 모아 뒀다.

1. **정의 해석** — 노드 경로나 노드 타입 이름을 받아 `hou.HDADefinition` 을
   찾는다. 툴마다 같은 분기를 반복하지 않기 위해서다.
2. **저장** — 정의를 고친 뒤 원래 .hda 파일에 다시 쓴다. 안 하면 세션이 끝날 때
   변경이 사라진다.
3. **인터페이스 요약** — `hou.ParmTemplateGroup` 을 폴더까지 재귀로 편다.
   템플릿 하나의 요약은 base 의 `parmtemplate` 헬퍼를 그대로 쓴다.
4. **검증용 임시 컨테이너** — 카테고리별로 인스턴스를 놓을 수 있는 네트워크를
   만든다. `check` 모듈이 쓴다.

실측 메모 (Houdini 22.0.368):

- `createDigitalAsset` 은 `hou.Node` 가 아니라 `hou.OpNode` 에 있다.
- `definition.version()` 은 타입 이름의 `::1.0` 과 **다른** 별도 메타데이터다.
  타입 이름의 버전 성분은 `hou.hda.componentsFromFullNodeTypeName` 로 뽑는다.
- 설치되지 않은 정의(`isInstalled() == False`)에 `save()` 를 하면
  CreateScript/InternalFileOptions 같은 섹션이 **사라진다**. 그래서 저장 전에
  설치 여부를 확인한다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/HDADefinition.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hou

from houdini_mcp_base.parmtemplate import component_names, describe_parm_template

EMBEDDED = "Embedded"
"""hip 파일 안에 박힌 정의의 라이브러리 경로. 디스크 파일이 아니다."""

TEMP_PREFIX = "hdamcp_tmp"
"""검증용 임시 노드 이름 접두사. Houdini UI 에 뜨므로 영어로 둔다."""


# --------------------------------------------------------------------------
# 정의 해석
# --------------------------------------------------------------------------


def require_definition(target: str) -> hou.HDADefinition:
    """노드 경로나 노드 타입 이름으로 HDA 정의를 찾는다.

    `/` 로 시작하면 노드 경로로, 아니면 노드 타입 이름으로 본다.
    타입 이름은 `Sop/ns::name::1.0` 처럼 카테고리를 앞에 붙이거나, 이름만 줘도
    모든 카테고리를 뒤진다.
    """
    if not target or not target.strip():
        raise ValueError(
            "target 이 비어 있습니다. HDA 인스턴스의 노드 경로(/obj/geo1/brick_maker) "
            "나 노드 타입 이름(Sop/ns::brick_maker::1.0)을 주세요."
        )
    target = target.strip()

    if target.startswith("/"):
        node = hou.node(target)
        if node is None:
            raise ValueError(
                f"그런 노드가 없습니다: {target}. "
                f"list_children 으로 부모 네트워크 안을 먼저 확인하세요."
            )
        definition = node.type().definition()
        if definition is None:
            raise ValueError(
                f"{target} 는 {node.type().name()} 타입이라 HDA 가 아닙니다. "
                f"디지털 에셋 인스턴스의 경로를 주거나, create_hda 로 먼저 구우세요."
            )
        return definition

    node_type = resolve_node_type(target)
    definition = node_type.definition()
    if definition is None:
        raise ValueError(
            f"{node_type.name()} 는 HDA 가 아니라 내장 노드 타입입니다. "
            f"list_installed_hdas 로 설치된 에셋 목록을 확인하세요."
        )
    return definition


def resolve_node_type(name: str) -> hou.NodeType:
    """`Sop/ns::name::1.0` 또는 `ns::name::1.0` 을 `hou.NodeType` 으로.

    카테고리를 생략하면 모든 카테고리를 뒤진다. 여러 곳에 같은 이름이 있으면
    어느 것인지 골라 달라고 알려 준다.
    """
    categories = hou.nodeTypeCategories()
    head, sep, tail = name.partition("/")
    if sep and head in categories:
        types = categories[head].nodeTypes()
        if tail not in types:
            raise ValueError(
                f"{head} 카테고리에 {tail!r} 노드 타입이 없습니다. "
                f"list_installed_hdas 로 설치된 에셋 이름을 확인하세요."
            )
        return types[tail]

    found = [
        types[name]
        for category in categories.values()
        for types in (category.nodeTypes(),)
        if name in types
    ]
    if not found:
        raise ValueError(
            f"그런 노드 타입이 없습니다: {name!r}. "
            f"카테고리를 붙여 보세요(Sop/{name}). 설치된 에셋은 "
            f"list_installed_hdas 로 확인합니다."
        )
    if len(found) > 1:
        where = ", ".join(f"{t.category().name()}/{t.name()}" for t in found)
        raise ValueError(
            f"{name!r} 이 여러 카테고리에 있습니다. 카테고리를 붙여 주세요: {where}"
        )
    return found[0]


def type_components(definition: hou.HDADefinition) -> dict[str, str]:
    """타입 이름을 성분으로 쪼갠다. `::` 로 문자열을 자르지 않는다."""
    scope, namespace, core, version = hou.hda.componentsFromFullNodeTypeName(
        definition.nodeTypeName()
    )
    return {"scope": scope, "namespace": namespace, "name": core, "version": version}


def compose_type_name(
    name: str, namespace: str | None = None, version: str | None = None
) -> str:
    """성분으로 전체 타입 이름을 만든다. 문자열을 이어 붙이지 않는다."""
    if not name or not name.strip():
        raise ValueError(
            "name 이 비어 있습니다. 에셋이 무엇을 하는지 드러나는 이름을 주세요. "
            "brick_maker, merlon_array 처럼."
        )
    if "::" in name:
        raise ValueError(
            f"name 에 `::` 를 넣지 마세요: {name!r}. "
            f"namespace 와 version 을 따로 주면 여기서 조립합니다."
        )
    return hou.hda.fullNodeTypeNameFromComponents(
        "", (namespace or "").strip(), name.strip(), (version or "").strip()
    )


# --------------------------------------------------------------------------
# 저장
# --------------------------------------------------------------------------


def persist(definition: hou.HDADefinition, template_node: hou.Node | None = None) -> str:
    """고친 정의를 원래 라이브러리 파일에 다시 쓴다.

    `setParmTemplateGroup` 이나 `addSection` 은 메모리 안의 정의만 바꾼다.
    저장하지 않으면 Houdini 를 닫을 때 사라진다.

    template_node 를 주면 그 인스턴스의 **내용물**(내부 노드)까지 함께 굽는다.
    인터페이스만 고쳤으면 주지 않는다 — 엉뚱한 인스턴스의 내용이 정의를 덮는다.
    """
    path = definition.libraryFilePath()
    if not definition.isInstalled():
        raise ValueError(
            f"{definition.nodeTypeName()} 정의가 설치돼 있지 않아 저장하면 섹션이 "
            f"사라집니다. install_hda 로 {path} 를 먼저 설치하세요."
        )
    try:
        definition.save(path, template_node=template_node, create_backup=False)
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{path} 에 정의를 저장하지 못했습니다: {exc} "
            f"파일이 읽기 전용인지, 디렉토리가 있는지 확인하세요."
        ) from exc
    return path


def require_hda_file(file_path: str, must_exist: bool = True) -> Path:
    """.hda 파일 경로를 Path 로. 문자열을 손으로 조립하지 않는다."""
    if not file_path or not file_path.strip():
        raise ValueError("file_path 가 비어 있습니다. .hda 파일 경로를 주세요.")
    path = Path(hou.text.expandString(file_path.strip())).expanduser()
    if must_exist and not path.is_file():
        raise ValueError(
            f"그런 파일이 없습니다: {path}. "
            f"경로를 확인하거나 create_hda 로 먼저 에셋을 구우세요."
        )
    return path


def require_directory(directory: str, must_exist: bool = True) -> Path:
    """디렉토리 경로를 Path 로."""
    if not directory or not directory.strip():
        raise ValueError("directory 가 비어 있습니다. 디렉토리 경로를 주세요.")
    path = Path(hou.text.expandString(directory.strip())).expanduser()
    if must_exist and not path.is_dir():
        raise ValueError(
            f"그런 디렉토리가 없습니다: {path}. "
            f"expand_hda 로 먼저 펼쳤는지 확인하세요."
        )
    return path


# --------------------------------------------------------------------------
# 인터페이스 요약
# --------------------------------------------------------------------------


def describe_group(group: hou.ParmTemplateGroup) -> list[dict[str, Any]]:
    """파라미터 그룹을 폴더까지 재귀로 편다."""
    return [describe_entry(template) for template in group.parmTemplates()]


def describe_entry(template: hou.ParmTemplate) -> dict[str, Any]:
    """템플릿 하나를 요약한다. 폴더면 자식까지 내려간다."""
    children = getattr(template, "parmTemplates", None)
    if children is not None:
        entry: dict[str, Any] = {
            "kind": "folder",
            "name": template.name(),
            "label": template.label(),
            "children": [describe_entry(child) for child in children()],
        }
        folder_type = getattr(template, "folderType", None)
        if folder_type is not None:
            entry["folder_type"] = str(folder_type()).rsplit(".", 1)[-1]
        return entry

    entry = describe_parm_template(template)
    entry["component_names"] = component_names(template)
    return entry


def top_level_names(group: hou.ParmTemplateGroup) -> list[str]:
    return [template.name() for template in group.parmTemplates()]


def interface_parm_count(group: hou.ParmTemplateGroup) -> int:
    """폴더를 뺀 실제 파라미터 개수."""
    return sum(1 for _ in _walk(group.parmTemplates()))


def _walk(templates):
    for template in templates:
        children = getattr(template, "parmTemplates", None)
        if children is not None:
            yield from _walk(children())
        else:
            yield template


# --------------------------------------------------------------------------
# 정의 요약
# --------------------------------------------------------------------------


def definition_summary(definition: hou.HDADefinition) -> dict[str, Any]:
    """정의의 신원. 모든 툴이 결과에 이걸 붙여 무엇을 건드렸는지 알려 준다."""
    return {
        "type_name": definition.nodeTypeName(),
        "components": type_components(definition),
        "category": definition.nodeTypeCategory().name(),
        "library_file": definition.libraryFilePath(),
        "installed": definition.isInstalled(),
        "comment": definition.comment(),
        "description": definition.description(),
    }


def instance_paths(definition: hou.HDADefinition, limit: int = 50) -> dict[str, Any]:
    """이 정의를 쓰는 노드들. 지우거나 해제하기 전에 확인해야 한다."""
    node_type = definition.nodeType()
    if node_type is None:
        return {"count": 0, "paths": []}
    nodes = node_type.instances()
    return {
        "count": len(nodes),
        "paths": [node.path() for node in nodes[:limit]],
        "truncated": len(nodes) > limit,
    }


# --------------------------------------------------------------------------
# 검증용 임시 컨테이너
# --------------------------------------------------------------------------

# 카테고리 -> (임시 컨테이너를 만들 부모, 컨테이너 노드 타입).
# 컨테이너 타입이 None 이면 그 부모 아래에 인스턴스를 바로 놓는다.
CONTAINERS: dict[str, tuple[str, str | None]] = {
    "Sop": ("/obj", "geo"),
    "Dop": ("/obj", "dopnet"),
    "Cop": ("/obj", "copnet"),
    "Cop2": ("/obj", "cop2net"),
    "Vop": ("/obj", "matnet"),
    "Top": ("/obj", "topnet"),
    "Chop": ("/obj", "chopnet"),
    "Lop": ("/obj", "lopnet"),
    "Shop": ("/obj", "shopnet"),
    "Object": ("/obj", None),
    "Driver": ("/out", None),
}


def make_container(category: str) -> tuple[hou.Node, hou.Node | None]:
    """인스턴스를 놓을 자리를 만든다. (부모, 정리해야 할 임시 노드)를 준다.

    임시 노드가 None 이면 부모는 원래 있던 것이므로 지우면 안 된다 — 그 경우
    부른 쪽이 인스턴스만 지운다.
    """
    if category not in CONTAINERS:
        raise ValueError(
            f"{category} 카테고리의 에셋은 인스턴스화 검증을 할 수 없습니다. "
            f"할 수 있는 것: {', '.join(sorted(CONTAINERS))}"
        )
    root_path, container_type = CONTAINERS[category]
    root = hou.node(root_path)
    if root is None:
        raise ValueError(f"{root_path} 네트워크를 찾지 못했습니다.")
    if container_type is None:
        return root, None
    container = root.createNode(container_type, node_name=f"{TEMP_PREFIX}_{category.lower()}")
    return container, container


def set_comment(node: hou.Node, comment: str) -> None:
    """코멘트를 달고 네트워크 뷰에 보이게 한다."""
    node.setComment(comment.strip())
    node.setGenericFlag(hou.nodeFlag.DisplayComment, True)


def require_comment(comment: str) -> None:
    if not comment or not comment.strip():
        raise ValueError(
            "comment 가 비어 있습니다. 이 에셋이 무엇을 하는지 영어로 적어 주세요. "
            "Builds one crenellated wall segment 처럼 구체적으로."
        )
