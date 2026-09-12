"""서브넷을 디지털 에셋으로 굽고, 정의를 다른 파일로 옮긴다.

기존 구현들은 `createDigitalAsset` 을 부르고 `{"path": ...}` 만 돌려줬다.
여기서는 **구운 결과를 확인해서** 돌려준다 — 어떤 타입 이름으로 등록됐는지,
정의가 설치됐는지, 인터페이스에 무엇이 올라왔는지, 입력이 몇 개인지.
구운 다음 `validate_hda` 로 실제 인스턴스를 놓아 볼 수 있다.

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/OpNode.html
"""

from __future__ import annotations

from typing import Any

import hou

from houdini_mcp import tool, undoable

from ._common import (
    compose_type_name,
    definition_summary,
    describe_group,
    interface_parm_count,
    persist,
    require_comment,
    require_definition,
    require_hda_file,
    set_comment,
    type_components,
)


@tool()
@undoable("Create digital asset")
def create_hda(
    path: str,
    name: str,
    hda_file: str,
    comment: str,
    namespace: str | None = None,
    version: str | None = None,
    label: str | None = None,
    icon: str | None = None,
    min_inputs: int = 0,
    max_inputs: int = 0,
) -> dict[str, Any]:
    """서브넷을 디지털 에셋(HDA)으로 굽는다.

    서브넷 안의 노드들이 에셋의 내용물이 되고, 서브넷 노드 자체는 새 타입의
    인스턴스로 바뀐다(경로는 그대로다). .hda 파일이 만들어지고 이 세션에
    설치된다.

    굽기 전에 서브넷 안을 정리해 둔다 — SOP 이면 마지막에 `output` 노드를 두고,
    바깥으로 내보낼 파라미터는 구운 뒤 `promote_parm` 으로 올린다.

    이름은 역할이 드러나게 짓는다. `subnet1` 이 아니라 `brick_maker`,
    `merlon_array` 처럼. namespace 를 주면 다른 스튜디오의 같은 이름과 부딪히지
    않는다.

    Args:
        path: 구울 서브넷 노드 경로. 예: /obj/castle/wall_builder
        name: 노드 타입의 핵심 이름. `::` 를 넣지 않는다. 예: brick_maker
        hda_file: 저장할 .hda 파일 경로. 없으면 만든다.
        comment: 이 에셋이 무엇을 하는지. 영어로. 노드와 정의 양쪽에 달린다.
        namespace: 타입 이름의 네임스페이스. 예: krafton
        version: 타입 이름의 버전. 예: "1.0"
        label: Tab 메뉴에 뜨는 이름. 영어로. 생략하면 Houdini 가 정한다.
        icon: 아이콘 이름. 예: SOP_box
        min_inputs: 최소 입력 개수.
        max_inputs: 최대 입력 개수. 0 이면 입력이 없다.
    """
    require_comment(comment)
    node = hou.node(path)
    if node is None:
        raise ValueError(
            f"그런 노드가 없습니다: {path}. "
            f"list_children 으로 부모 네트워크 안을 먼저 확인하세요."
        )
    if not node.canCreateDigitalAsset():
        raise ValueError(
            f"{path} ({node.type().name()}) 는 디지털 에셋으로 구울 수 없습니다. "
            f"서브넷을 주세요. create_node 로 subnet 을 만들고 안에 노드를 넣은 "
            f"뒤 다시 부르세요."
        )

    type_name = compose_type_name(name, namespace, version)
    target = require_hda_file(hda_file, must_exist=False)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        asset = node.createDigitalAsset(
            name=type_name,
            hda_file_name=str(target),
            description=label,
            min_num_inputs=min_inputs,
            max_num_inputs=max_inputs,
            comment=comment.strip(),
            create_backup=False,
        )
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{path} 를 {type_name!r} 로 굽지 못했습니다: {exc} "
            f"같은 이름의 타입이 이미 있으면 version 을 올리거나 namespace 를 주세요."
        ) from exc

    definition = asset.type().definition()
    if icon:
        definition.setIcon(icon)
    if version:
        # 타입 이름의 버전 성분과 정의 메타데이터의 version 은 별개다. 둘이
        # 어긋나면 hda_info 를 읽는 쪽이 헷갈리므로 같이 맞춘다.
        definition.setVersion(version)
    if icon or version:
        persist(definition)

    set_comment(asset, comment)
    group = definition.parmTemplateGroup()
    return {
        "path": asset.path(),
        "comment": asset.comment(),
        "definition": definition_summary(definition),
        "version": definition.version(),
        "icon": definition.icon(),
        "inputs": {
            "min": definition.minNumInputs(),
            "max": definition.maxNumInputs(),
        },
        "interface": describe_group(group),
        "interface_parm_count": interface_parm_count(group),
        "next": (
            "promote_parm 으로 내부 파라미터를 올리고 validate_hda 로 인스턴스를 "
            "놓아 확인하세요."
        ),
    }


@tool()
@undoable("Copy digital asset definition")
def save_as_hda(
    target: str,
    hda_file: str,
    name: str | None = None,
    namespace: str | None = None,
    version: str | None = None,
    label: str | None = None,
    install: bool = True,
) -> dict[str, Any]:
    """이미 있는 HDA 정의를 다른 .hda 파일로 복사한다. 이름도 바꿀 수 있다.

    버전을 올릴 때 쓴다 — `version="2.0"` 으로 복사하면 1.0 인스턴스는 그대로
    두고 2.0 을 새로 만든다. 라이브러리를 배포용으로 한 파일에 모을 때도 쓴다
    (같은 hda_file 로 여러 번 부르면 한 파일에 쌓인다).

    원본 파일은 건드리지 않는다.

    Args:
        target: 원본. HDA 인스턴스의 노드 경로거나 노드 타입 이름
            (Sop/ns::brick_maker::1.0).
        hda_file: 복사해 넣을 .hda 파일 경로. 없으면 만든다.
        name: 새 핵심 이름. 생략하면 원본 이름 그대로.
        namespace: 새 네임스페이스. 생략하면 원본 그대로.
        version: 새 버전. 생략하면 원본 그대로.
        label: Tab 메뉴 이름. 영어로.
        install: True 면 복사한 뒤 그 파일을 이 세션에 설치한다.
    """
    definition = require_definition(target)
    source_file = definition.libraryFilePath()
    dest = require_hda_file(hda_file, must_exist=False)
    dest.parent.mkdir(parents=True, exist_ok=True)

    parts = type_components(definition)
    renaming = any(value is not None for value in (name, namespace, version))
    if renaming:
        new_name = compose_type_name(
            name or parts["name"],
            namespace if namespace is not None else parts["namespace"],
            version if version is not None else parts["version"],
        )
    else:
        new_name = definition.nodeTypeName()

    if new_name == definition.nodeTypeName() and dest.as_posix() == source_file.replace(
        "\\", "/"
    ):
        raise ValueError(
            f"원본과 같은 파일에 같은 이름으로 복사하려 합니다: {dest}. "
            f"name / namespace / version 중 하나를 바꾸거나 다른 파일을 주세요."
        )

    try:
        definition.copyToHDAFile(
            str(dest),
            new_name=new_name if renaming else None,
            new_menu_name=label,
        )
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{dest} 로 복사하지 못했습니다: {exc} "
            f"디렉토리가 쓰기 가능한지 확인하세요."
        ) from exc

    if install:
        hou.hda.installFile(str(dest))

    copied = [
        {
            "type_name": entry.nodeTypeName(),
            "category": entry.nodeTypeCategory().name(),
            "installed": entry.isInstalled(),
        }
        for entry in hou.hda.definitionsInFile(str(dest))
    ]
    return {
        "source": definition_summary(definition),
        "hda_file": str(dest),
        "new_type_name": new_name,
        "renamed": renaming,
        "installed": install,
        "definitions_in_file": copied,
    }
