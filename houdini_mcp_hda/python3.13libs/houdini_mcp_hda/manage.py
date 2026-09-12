"""HDA 라이브러리를 세션에 설치·해제·리로드하고 무엇이 들어 있는지 읽는다.

기존 구현들은 `installFile` 을 부르고 끝냈다. 여기서는 **설치하기 전에 파일 안을
읽어**, 어떤 타입이 들어오는지와 이미 있는 타입을 덮어쓰는지를 함께 돌려준다.
해제할 때는 살아 있는 인스턴스를 먼저 센다 — 쓰고 있는 에셋을 해제하면 그
노드들이 정의 없는 껍데기가 되기 때문이다(실측으로 확인했다).

hou API 레퍼런스: https://www.sidefx.com/docs/houdini/hom/hou/hda.html
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import hou

from houdini_mcp import tool, undoable

from ._common import (
    definition_summary,
    instance_paths,
    interface_parm_count,
    require_definition,
    require_hda_file,
    type_components,
)


def _file_definitions(path: Path) -> list[hou.HDADefinition]:
    try:
        return list(hou.hda.definitionsInFile(str(path)))
    except hou.OperationFailed as exc:
        raise ValueError(
            f"{path} 를 HDA 라이브러리로 읽지 못했습니다: {exc} "
            f"올바른 .hda/.otl 파일인지 확인하세요."
        ) from exc


def _brief(definition: hou.HDADefinition) -> dict[str, Any]:
    return {
        "type_name": definition.nodeTypeName(),
        "category": definition.nodeTypeCategory().name(),
        "components": type_components(definition),
        "description": definition.description(),
        "comment": definition.comment(),
        "installed": definition.isInstalled(),
        "preferred": definition.isPreferred(),
    }


def _existing_type(definition: hou.HDADefinition) -> str | None:
    """같은 타입 이름이 이미 다른 파일에서 오고 있으면 그 파일 경로."""
    category = definition.nodeTypeCategory()
    node_type = category.nodeTypes().get(definition.nodeTypeName())
    if node_type is None:
        return None
    current = node_type.definition()
    if current is None:
        return None
    return current.libraryFilePath()


@tool()
@undoable("Install HDA library")
def install_hda(file_path: str) -> dict[str, Any]:
    """.hda 라이브러리를 이 세션에 설치한다. 무엇이 들어오는지 함께 돌려준다.

    설치 전에 파일 안의 정의를 읽어, 같은 타입 이름이 이미 다른 파일에서 오고
    있으면 `replaces` 로 알려 준다. 모르고 남의 에셋을 덮는 일을 막기 위해서다.

    이 설치는 세션에만 남는다. Houdini 를 다시 띄우면 사라지므로, 계속 쓰려면
    패키지 JSON 이나 `$HOUDINI_OTLSCAN_PATH` 로 붙인다.

    Args:
        file_path: .hda 또는 .otl 파일 경로.
    """
    path = require_hda_file(file_path)
    definitions = _file_definitions(path)
    if not definitions:
        raise ValueError(
            f"{path} 안에 디지털 에셋 정의가 없습니다. 빈 라이브러리입니다."
        )

    replaces = [
        {"type_name": d.nodeTypeName(), "was_from": source}
        for d in definitions
        if (source := _existing_type(d)) and Path(source) != path
    ]

    try:
        hou.hda.installFile(str(path))
    except hou.OperationFailed as exc:
        raise ValueError(f"{path} 를 설치하지 못했습니다: {exc}") from exc

    return {
        "file": str(path),
        "count": len(definitions),
        "definitions": [_brief(d) for d in _file_definitions(path)],
        "replaces": replaces,
        "loaded_files": len(hou.hda.loadedFiles()),
    }


@tool()
@undoable("Uninstall HDA library")
def uninstall_hda(file_path: str, force: bool = False) -> dict[str, Any]:
    """.hda 라이브러리를 이 세션에서 뺀다. 파일은 그대로 둔다.

    씬에 그 에셋 인스턴스가 남아 있으면 정의 없는 껍데기가 된다. 그래서 기본적
    으로는 인스턴스가 있으면 거부하고 어느 노드가 걸리는지 알려 준다. 그래도
    빼야 하면 `force=True` 를 준다.

    hip 파일 안에 박힌 정의를 빼려면 file_path 에 "Embedded" 를 준다.

    Args:
        file_path: .hda 파일 경로. 또는 "Embedded".
        force: True 면 인스턴스가 있어도 해제한다.
    """
    embedded = file_path.strip() == "Embedded"
    path = Path("Embedded") if embedded else require_hda_file(file_path)

    definitions = _file_definitions(path) if not embedded else []
    blocking: list[dict[str, Any]] = []
    for definition in definitions:
        if not definition.isInstalled():
            continue
        instances = instance_paths(definition)
        if instances["count"]:
            blocking.append({"type_name": definition.nodeTypeName(), **instances})

    if blocking and not force:
        where = "; ".join(
            f"{item['type_name']}: {', '.join(item['paths'][:5])}" for item in blocking
        )
        raise ValueError(
            f"{path} 를 해제하면 씬에 있는 인스턴스가 깨집니다. {where}. "
            f"그 노드들을 먼저 지우거나 force=True 로 다시 부르세요."
        )

    try:
        hou.hda.uninstallFile(str(path))
    except hou.OperationFailed as exc:
        raise ValueError(f"{path} 를 해제하지 못했습니다: {exc}") from exc

    return {
        "file": str(path),
        "uninstalled": [d.nodeTypeName() for d in definitions],
        "broken_instances": blocking,
        "forced": bool(blocking and force),
        "loaded_files": len(hou.hda.loadedFiles()),
    }


@tool()
@undoable("Reload HDA library")
def reload_hda(file_path: str) -> dict[str, Any]:
    """.hda 파일을 디스크에서 다시 읽는다. 씬의 인스턴스가 새 정의로 갱신된다.

    이 세션 밖에서 파일이 바뀌었을 때 쓴다 — 다른 사람이 고쳤거나,
    `collapse_hda` 로 디렉토리에서 다시 접었을 때다. 이 세션 안에서 툴로 고친
    것은 이미 반영돼 있으므로 부를 필요가 없다.

    Args:
        file_path: .hda 파일 경로.
    """
    path = require_hda_file(file_path)
    try:
        hou.hda.reloadFile(str(path))
    except hou.OperationFailed as exc:
        raise ValueError(f"{path} 를 리로드하지 못했습니다: {exc}") from exc

    definitions = _file_definitions(path)
    return {
        "file": str(path),
        "count": len(definitions),
        "definitions": [
            {**_brief(d), **{"instances": instance_paths(d)["count"]}}
            for d in definitions
        ],
    }


@tool()
def list_installed_hdas(
    pattern: str | None = None, category: str | None = None, limit: int = 60
) -> dict[str, Any]:
    """이 세션에 설치된 HDA 라이브러리와 그 안의 에셋들을 나열한다.

    번들 에셋까지 수백 개가 나올 수 있으므로 pattern 으로 좁힌다. 패턴은 타입
    이름과 파일 경로 양쪽에 글롭으로 맞춰 본다.

    Args:
        pattern: 글롭 패턴. 예: "*brick*", "*/castle/*"
        category: 노드 카테고리로 거른다. 예: Sop, Object, Lop
        limit: 돌려줄 라이브러리 최대 개수.
    """
    matched: list[dict[str, Any]] = []
    total_files = 0
    total_defs = 0

    for file_path in sorted(hou.hda.loadedFiles()):
        total_files += 1
        try:
            definitions = list(hou.hda.definitionsInFile(file_path))
        except hou.OperationFailed:
            # 읽을 수 없는 라이브러리가 목록 전체를 막지 않게 한다.
            continue

        entries = []
        for definition in definitions:
            total_defs += 1
            if category and definition.nodeTypeCategory().name() != category:
                continue
            if pattern and not (
                fnmatch.fnmatch(definition.nodeTypeName(), pattern)
                or fnmatch.fnmatch(file_path.replace("\\", "/"), pattern)
            ):
                continue
            entries.append(_brief(definition))

        if entries:
            matched.append({"file": file_path, "count": len(entries), "definitions": entries})

    return {
        "loaded_files": total_files,
        "total_definitions": total_defs,
        "matched_files": len(matched),
        "libraries": matched[:limit],
        "truncated": len(matched) > limit,
        "filter": {"pattern": pattern, "category": category},
    }


@tool()
def hda_info(target: str) -> dict[str, Any]:
    """HDA 정의 하나를 자세히 읽는다 — 메타데이터·옵션·섹션·인스턴스까지.

    `node_info` 는 인스턴스 노드를 설명하고, 이것은 그 노드가 어느 **정의**에서
    왔는지를 설명한다. 고치기 전에 여기서 라이브러리 경로와 버전을 확인한다.

    타입 이름의 버전(`::1.0`)과 정의 메타데이터의 `version` 은 별개다. 둘 다
    돌려주므로 어긋나 있으면 바로 보인다.

    Args:
        target: HDA 인스턴스의 노드 경로거나 노드 타입 이름
            (Sop/ns::brick_maker::1.0).
    """
    definition = require_definition(target)
    options = definition.options()
    group = definition.parmTemplateGroup()

    return {
        "definition": definition_summary(definition),
        "version": definition.version(),
        "icon": definition.icon(),
        "preferred": definition.isPreferred(),
        "modified": definition.modificationTime(),
        "inputs": {
            "min": definition.minNumInputs(),
            "max": definition.maxNumInputs(),
        },
        "max_outputs": definition.maxNumOutputs(),
        "interface_parm_count": interface_parm_count(group),
        "top_level": [template.name() for template in group.parmTemplates()],
        "sections": sorted(definition.sections()),
        "options": {
            "compress_contents": options.compressContents(),
            "lock_contents": options.lockContents(),
            "unlock_new_instances": options.unlockNewInstances(),
            "save_cached_code": options.saveCachedCode(),
            "save_spare_parms": options.saveSpareParms(),
            "forbid_outside_parms": options.forbidOutsideParms(),
            "check_for_external_links": options.checkForExternalLinks(),
        },
        "instances": instance_paths(definition),
    }
