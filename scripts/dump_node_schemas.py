"""노드 타입 스키마를 실측해 JSONL 로 덤프한다.

khouwledge(Houdini 문서 지식베이스)와 합의한 "채널 A" 를 만드는 도구다. 문서에
없는 것 - 실제 파라미터 이름, 기본값, 조건부 활성 식, 배포 출처 - 을 살아 있는
Houdini 에서 뽑아 넘긴다.

실행:
    "$HFS/bin/hython" scripts/dump_node_schemas.py --category Sop --out dist

    --category  뽑을 카테고리. 여러 번 줄 수 있다. 생략하면 Sop 하나.
    --out       출력 디렉토리. <category>.jsonl.gz 와 manifest.json 이 생긴다.
    --limit     앞에서 N 개만. 검증용.
    --no-create 노드를 만들지 않는다. 빠르지만 성분 이름이 유도값이고 입출력
                라벨이 빠진다.

노드를 만드는 이유는 성분 이름 때문이다. 템플릿은 벡터를 튜플로만 주고(`rad`),
실제 이름(`rad1`, `rad2`)은 namingScheme 으로 유도해야 하는데 그건 휴리스틱이다.
틀리면 존재하지 않는 파라미터 이름을 자신 있게 알려주게 되므로, 실제로 만들어
확인하고 유도값과 어긋난 것을 매니페스트에 남긴다.

**GUI 세션에서 돌리지 마라.** 노드를 수천 개 만들었다 지우므로 사용자 장면과
Undo 스택이 망가진다. hython 으로 빈 씬에서만 쓴다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import hou

SCHEMA = "houdini-observed/1"

# 벡터 파라미터의 성분 접미사. namingScheme 이 이 중 하나를 돌려준다.
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

# 카테고리별로 노드를 만들 수 있는 부모 네트워크. (부모 경로, 만들 컨테이너 타입)
CONTAINERS = {
    "Sop": ("/obj", "geo"),
    "Object": ("/obj", None),
    "Dop": ("/obj", "dopnet"),
    "Top": ("/obj", "topnet"),
    "Chop": ("/obj", "chopnet"),
    "Cop": ("/obj", "cop2net"),
    "Cop2": ("/obj", "cop2net"),
    "Driver": ("/out", None),
    "Lop": ("/stage", None),
    "Vop": ("/mat", None),
    "Shop": ("/shop", None),
}


def expand_components(template: Any) -> tuple[list[str], str | None]:
    """템플릿에서 성분 이름을 유도한다. (이름들, 쓰인 스킴)."""
    count = template.numComponents()
    if count <= 1:
        return [template.name()], None
    getter = getattr(template, "namingScheme", None)
    if getter is None:
        return [template.name()], None
    scheme = str(getter()).rsplit(".", 1)[-1]
    maker = SUFFIX.get(scheme)
    if maker is None:
        return [template.name()], scheme
    return [template.name() + maker(i) for i in range(count)], scheme


def classify_origin(node_type: Any, hfs: str) -> dict[str, Any]:
    """배포 출처를 가른다.

    definition() 이 None 이면 빌트인이라는 단순 분류로는 안 된다. SideFX 공식
    노드 상당수가 $HFS 안의 HDA($HFS/houdini/otls/OPlib*.hda)로 배포되기 때문에,
    외부 패키지와 구분하려면 라이브러리 경로를 봐야 한다.
    """
    definition = node_type.definition()
    if definition is None:
        return {"source": "builtin_compiled", "library": None}

    path = definition.libraryFilePath().replace("\\", "/")
    if "sidefx_packages" in path:
        source = "package_hda"
    elif path.startswith(hfs):
        source = "builtin_hda"
    else:
        source = "user_hda"
    return {"source": source, "library": path, "library_name": path.rsplit("/", 1)[-1]}


# 값을 갖지 않는 UI 전용 템플릿. 실제 노드의 parms() 에 나타나지 않는다.
UI_ONLY = ("Separator", "Label", "FolderSet")

MULTIPARM_FOLDERS = (
    "MultiparmBlock",
    "ScrollingMultiparmBlock",
    "TabbedMultiparmBlock",
)


def is_multiparm(entry) -> bool:
    """멀티파라미터 블록인지. 그 안의 파라미터는 이름에 # 를 갖는다."""
    getter = getattr(entry, "folderType", None)
    if getter is None:
        return False
    try:
        return str(getter()).rsplit(".", 1)[-1] in MULTIPARM_FOLDERS
    except hou.OperationFailed:
        return False


def walk_templates(entries, folder: tuple[str, ...] = (), inside_multiparm: bool = False):
    """폴더 계층을 따라 내려가며 (폴더경로, 템플릿, 멀티파라미터여부) 를 낸다."""
    for entry in entries:
        if entry.type() == hou.parmTemplateType.Folder:
            if is_multiparm(entry):
                # 멀티파라미터 폴더 자체가 인스턴스 개수를 담는 실제 파라미터다.
                yield "/".join(folder), entry, False
            yield from walk_templates(
                entry.parmTemplates(),
                folder + (entry.label(),),
                inside_multiparm or is_multiparm(entry),
            )
        else:
            yield "/".join(folder), entry, inside_multiparm


def describe_template(
    template: Any, folder: str, order: int, multiparm: bool = False
) -> list[dict[str, Any]]:
    """파라미터 템플릿 하나를 성분 단위 레코드로 편다."""
    default_getter = getattr(template, "defaultValue", None)
    default = default_getter() if default_getter else None

    menu = None
    if hasattr(template, "menuItems"):
        try:
            items = list(template.menuItems() or [])
        except hou.OperationFailed:
            items = []
        if items:
            labels = list(template.menuLabels() or [])
            menu = [
                {"value": v, "label": labels[i] if i < len(labels) else v}
                for i, v in enumerate(items)
            ]

    conditionals = None
    getter = getattr(template, "conditionals", None)
    if getter:
        try:
            raw = getter()
        except hou.OperationFailed:
            raw = None
        if raw:
            conditionals = {str(k).rsplit(".", 1)[-1]: v for k, v in raw.items()}

    names, scheme = expand_components(template)
    records = []
    for index, name in enumerate(names):
        record: dict[str, Any] = {
            "name": name,
            "label": template.label(),
            "type": type(template).__name__.replace("ParmTemplate", "").lower(),
            "order": order,
        }
        if folder:
            record["folder"] = folder
        if isinstance(default, (tuple, list)):
            record["default"] = default[index] if index < len(default) else None
        elif default is not None:
            record["default"] = default
        if len(names) > 1:
            record["tuple"] = template.name()
            record["component"] = index
            record["naming_scheme"] = scheme
        if menu:
            record["menu"] = menu
        if conditionals:
            record["conditionals"] = conditionals
        if multiparm:
            # 이름의 # 는 인스턴스 번호로 치환된다. 실제 노드에는 인스턴스 수만큼
            # 생기므로, 블록이 비어 있으면 parms() 에 하나도 없다.
            record["multiparm"] = True
        records.append(record)
    return records


def dump_type(node_type: Any, category: str, hfs: str, parent: Any | None) -> dict[str, Any]:
    """노드 타입 하나의 스키마. parent 가 있으면 노드를 만들어 실측한다."""
    entry: dict[str, Any] = {
        "schema": SCHEMA,
        "node_type": f"{category}/{node_type.name()}",
        "label": node_type.description(),
        "deprecated": bool(node_type.deprecated()),
        "hidden": bool(node_type.hidden()),
        "impl": str(node_type.source()).rsplit(".", 1)[-1],
        "inputs": {"min": node_type.minNumInputs(), "max": node_type.maxNumInputs()},
        "outputs": node_type.maxNumOutputs(),
    }
    entry.update(classify_origin(node_type, hfs))

    templates: list[dict[str, Any]] = []
    for order, (folder, template, multiparm) in enumerate(
        walk_templates(node_type.parmTemplateGroup().entries())
    ):
        if type(template).__name__.replace("ParmTemplate", "") in UI_ONLY:
            continue  # 구분선/라벨은 값이 없어 실제 파라미터가 아니다
        templates.extend(describe_template(template, folder, order, multiparm))
    entry["parms"] = templates

    if parent is None:
        return entry

    # 실제로 만들어 성분 이름을 확인한다. 유도가 휴리스틱이기 때문이다.
    node = None
    try:
        node = parent.createNode(node_type.name())
    except hou.Error as exc:
        entry["create_failed"] = str(exc).splitlines()[0][:200]
        return entry

    try:
        actual = {p.name() for p in node.parms()}
        # 멀티파라미터는 인스턴스가 0개면 실제에 없는 게 정상이라 비교에서 뺀다.
        derived = {p["name"] for p in templates if not p.get("multiparm")}
        missing = sorted(derived - actual)
        # 실제에만 있는 것 중 폴더/스위처는 UI 구조물이라 잡음이다.
        # 멀티파라미터 인스턴스는 `closed#` -> `closed0` 식으로 파생된 것이라
        # 템플릿에 없는 게 정상이다. 접두사가 겹치면 잡음으로 보지 않는다.
        multi_stems = tuple(
            p["name"].split("#", 1)[0] for p in templates if p.get("multiparm") and "#" in p["name"]
        )
        extra = sorted(
            n for n in actual - derived
            if not n.startswith(("folder", "stdswitcher", "switcher"))
            and not (multi_stems and n.startswith(multi_stems))
        )
        if missing or extra:
            entry["name_mismatch"] = {"derived_only": missing[:40], "actual_only": extra[:40]}
        entry["parm_count_actual"] = len(actual)

        for attr, key in (("inputLabels", "input_labels"), ("outputLabels", "output_labels")):
            getter = getattr(node, attr, None)
            if getter:
                try:
                    labels = list(getter())
                except hou.OperationFailed:
                    labels = []
                if labels:
                    entry[key] = labels
    finally:
        if node is not None:
            node.destroy()
    return entry


def make_parent(category: str) -> Any | None:
    """카테고리에 맞는 부모 네트워크를 만든다. 모르면 None(= 노드 생성 생략)."""
    spec = CONTAINERS.get(category)
    if spec is None:
        return None
    parent_path, container_type = spec
    parent = hou.node(parent_path)
    if parent is None:
        return None
    if container_type is None:
        return parent
    try:
        return parent.createNode(container_type, f"hmcp_dump_{category.lower()}")
    except hou.Error:
        return None


def dump_category(category: str, out_dir: Path, limit: int | None, create: bool) -> dict[str, Any]:
    hfs = hou.text.expandString("$HFS").replace("\\", "/").rstrip("/")
    types = hou.nodeTypeCategories()[category].nodeTypes()
    names = sorted(types)
    if limit:
        names = names[:limit]

    parent = make_parent(category) if create else None
    if create and parent is None:
        print(f"  [{category}] 부모 네트워크를 만들지 못해 노드 생성을 건너뜁니다")

    path = out_dir / f"{category.lower()}.jsonl.gz"
    started = time.time()
    failed: list[dict[str, str]] = []
    mismatches: list[dict[str, Any]] = []
    parm_total = 0

    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for i, name in enumerate(names, 1):
            entry = dump_type(types[name], category, hfs, parent)
            parm_total += len(entry["parms"])
            if "create_failed" in entry:
                failed.append({"node_type": entry["node_type"], "error": entry["create_failed"]})
            if "name_mismatch" in entry:
                mismatches.append({"node_type": entry["node_type"], **entry["name_mismatch"]})
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if i % 200 == 0:
                print(f"  [{category}] {i}/{len(names)} ...", flush=True)

    if parent is not None and CONTAINERS[category][1] is not None:
        parent.destroy()

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "name": category,
        "file": path.name,
        "node_types": len(names),
        "parms": parm_total,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "seconds": round(time.time() - started, 1),
        "created_nodes": bool(parent is not None),
        "failed": failed,
        "name_mismatches": mismatches,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--category", action="append", default=None)
    ap.add_argument("--out", default="dist")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-create", action="store_true")
    args = ap.parse_args()

    categories = args.category or ["Sop"]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Houdini {hou.applicationVersionString()} / 카테고리 {', '.join(categories)}")
    results = []
    for category in categories:
        if category not in hou.nodeTypeCategories():
            print(f"  알 수 없는 카테고리: {category}")
            continue
        results.append(dump_category(category, out_dir, args.limit, not args.no_create))

    manifest = {
        "schema": SCHEMA,
        "houdini": hou.applicationVersionString(),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "categories": results,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    for r in results:
        print(f"  {r['name']:10s} 타입 {r['node_types']:5d}  파라미터 {r['parms']:7d}  "
              f"{r['bytes']/1024:7.0f}KB  {r['seconds']:6.1f}s  "
              f"실패 {len(r['failed']):3d}  불일치 {len(r['name_mismatches']):3d}")
    print(f"\n  -> {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
