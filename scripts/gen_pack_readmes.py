"""툴 팩마다 README.md(한국어)와 README.en.md(영어)를 코드에서 만든다.

툴 정보(이름, 설명, 인자, Undo 여부)는 코드의 docstring 과 시그니처가 원본이다.
README 를 손으로 쓰면 코드와 금방 어긋나므로, 여기서 생성한다. 설명을 고치려면
README 가 아니라 docstring 을 고친 뒤 다시 생성한다.

영어판은 docstring(한국어)을 번역한 카탈로그에서 만든다.

    docs/i18n/en/<팩>.json   팩 개요, 모듈 요약, 툴 설명, 인자 설명의 영어 번역

카탈로그 항목마다 원문(source)과 그 해시(source_hash)를 둔다. docstring 이 바뀌면
--sync-i18n 이 원문·해시를 새 것으로 바꾸고 `"stale": true` 를 단다. 영어를 고친 뒤
stale 을 지우면 최신 번역으로 본다. 해시가 원문과 다르거나 stale 이 남아 있으면
--check 가 실패한다. 번역이 없거나 낡은 항목은 README.en.md 에 원문을
그대로 싣고 표시한다.

Houdini 없이 돈다. 코드를 import 하지 않고 AST 로만 읽는다(hou 가 없어도 된다).

    python scripts/gen_pack_readmes.py              # README.md, README.en.md 를 쓴다
    python scripts/gen_pack_readmes.py --sync-i18n  # 카탈로그에 새 항목을 넣고 낡은 항목을 표시
    python scripts/gen_pack_readmes.py --check      # README 가 어긋났거나 번역이 비었으면 실패
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER_PACKAGE = "houdini_mcp"
PACKAGES_DIR = REPO / "packages"
I18N_DIR = REPO / "docs" / "i18n" / "en"


@dataclass
class ToolArg:
    name: str
    annotation: str
    default: str | None
    doc: str = ""


@dataclass
class ToolInfo:
    name: str
    summary: str
    args: list[ToolArg]
    undoable: bool

    def source(self) -> str:
        """번역 대상 원문 전체. 해시로 번역이 낡았는지 본다."""
        parts = [self.summary] + [f"{a.name}: {a.doc}" for a in self.args]
        return "\n".join(parts)


@dataclass
class ModuleInfo:
    name: str
    summary: str
    tools: list[ToolInfo] = field(default_factory=list)


@dataclass
class PackInfo:
    name: str
    requires: list[str]
    doc: str
    modules: list[ModuleInfo]

    @property
    def tool_count(self) -> int:
        return sum(len(m.tools) for m in self.modules)


# --------------------------------------------------------------------------
# 코드 읽기
# --------------------------------------------------------------------------


def _decorator_names(node: ast.FunctionDef) -> list[str]:
    names = []
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        names.append(getattr(target, "id", None) or getattr(target, "attr", None) or "")
    return names


def _tool_name(node: ast.FunctionDef) -> str:
    """@tool("이름") 이나 @tool(name="이름") 으로 바꾼 이름이 있으면 그것을 쓴다."""
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        target = dec.func
        if (getattr(target, "id", None) or getattr(target, "attr", None)) != "tool":
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            return dec.args[0].value
        for kw in dec.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return node.name


def _arg_docs(doc: str) -> dict[str, str]:
    """Google 스타일 Args: 절에서 인자별 설명을 뽑는다."""
    if "Args:" not in doc:
        return {}
    docs: dict[str, str] = {}
    current = None
    for line in doc.split("Args:", 1)[1].splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            break
        head, sep, rest = line.strip().partition(":")
        if sep and head.isidentifier() and indent <= 4:
            current = head
            docs[current] = rest.strip()
        elif current is not None:
            docs[current] = f"{docs[current]} {line.strip()}".strip()
    return docs


def _tools_in(tree: ast.Module) -> list[ToolInfo]:
    tools = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        decorators = _decorator_names(node)
        if "tool" not in decorators:
            continue
        doc = ast.get_docstring(node) or ""
        arg_docs = _arg_docs(doc)
        positional = node.args.posonlyargs + node.args.args
        defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
        pairs = list(zip(positional, defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))
        args = [
            ToolArg(
                name=arg.arg,
                annotation=ast.unparse(arg.annotation) if arg.annotation else "",
                default=ast.unparse(default) if default is not None else None,
                doc=arg_docs.get(arg.arg, ""),
            )
            for arg, default in pairs
        ]
        summary = doc.split("\n\n", 1)[0].strip().replace("\n", " ")
        tools.append(ToolInfo(_tool_name(node), summary, args, "undoable" in decorators))
    return tools


def load_pack(pack_json: Path) -> PackInfo:
    name = pack_json.stem
    libs = sorted((REPO / name).glob("python3.*libs"))
    if not libs:
        raise SystemExit(f"{name}: python3.*libs 디렉토리가 없습니다.")
    package_dir = libs[-1] / name
    init_tree = ast.parse((package_dir / "__init__.py").read_text(encoding="utf-8"))
    declared: list[str] = []
    for node in init_tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == "TOOL_MODULES" for t in node.targets)
            and isinstance(node.value, (ast.Tuple, ast.List))
        ):
            declared = [ast.literal_eval(element) for element in node.value.elts]
    if not declared:
        declared = sorted(p.stem for p in package_dir.glob("*.py") if not p.stem.startswith("_"))
    modules = []
    for module in declared:
        tree = ast.parse((package_dir / f"{module}.py").read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree) or ""
        modules.append(ModuleInfo(module, doc.split("\n\n", 1)[0].strip().replace("\n", " "), _tools_in(tree)))
    requires = json.loads(pack_json.read_text(encoding="utf-8")).get("requires", [])
    return PackInfo(name, requires, ast.get_docstring(init_tree) or "", modules)


def load_packs() -> list[PackInfo]:
    return [load_pack(p) for p in sorted(PACKAGES_DIR.glob(f"{SERVER_PACKAGE}_*.json"))]


# --------------------------------------------------------------------------
# 번역 카탈로그
# --------------------------------------------------------------------------


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def catalog_path(pack: PackInfo) -> Path:
    return I18N_DIR / f"{pack.name}.json"


def load_catalog(pack: PackInfo) -> dict:
    path = catalog_path(pack)
    if not path.exists():
        return {"pack": pack.name, "overview": {}, "modules": {}, "tools": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _entry_ok(entry: dict | None, source: str, keys: tuple[str, ...]) -> bool:
    if not entry or entry.get("stale") or entry.get("source_hash") != _hash(source):
        return False
    return all(str(entry.get(k, "")).strip() for k in keys)


def sync_catalog(pack: PackInfo) -> tuple[dict, list[str]]:
    """새 항목은 빈 번역으로 넣고, 원문이 바뀐 항목은 stale 로 표시한다."""
    catalog = load_catalog(pack)
    problems: list[str] = []

    def upsert(section: dict, key: str, source: str, fields: dict[str, str]) -> dict:
        entry = section.get(key)
        if entry is None:
            entry = {"source": source, "source_hash": _hash(source), **fields}
            section[key] = entry
        elif entry.get("source_hash") != _hash(source):
            # 해시는 바로 새 원문으로 옮기고 stale 로 표시한다. 번역을 고친 사람이
            # stale 을 지우면 최신 번역으로 본다.
            entry["source"] = source
            entry["source_hash"] = _hash(source)
            entry["stale"] = True
            for name, value in fields.items():
                entry.setdefault(name, value)
        return entry

    upsert(catalog.setdefault("overview", {}), "text", pack.doc.strip(), {"en": ""})
    modules = catalog.setdefault("modules", {})
    tools = catalog.setdefault("tools", {})
    for module in pack.modules:
        upsert(modules, module.name, module.summary, {"en": ""})
        for tool in module.tools:
            entry = upsert(tools, tool.name, tool.source(), {"summary": ""})
            args = entry.setdefault("args", {})
            for arg in tool.args:
                args.setdefault(arg.name, "")

    known_modules = {m.name for m in pack.modules}
    known_tools = {t.name for m in pack.modules for t in m.tools}
    for key in [k for k in modules if k not in known_modules]:
        del modules[key]
    for key in [k for k in tools if k not in known_tools]:
        del tools[key]

    for problem in translation_problems(pack, catalog):
        problems.append(problem)
    return catalog, problems


def translation_problems(pack: PackInfo, catalog: dict) -> list[str]:
    problems = []
    if not _entry_ok(catalog.get("overview", {}).get("text"), pack.doc.strip(), ("en",)):
        problems.append(f"{pack.name}: overview")
    for module in pack.modules:
        if not _entry_ok(catalog.get("modules", {}).get(module.name), module.summary, ("en",)) and module.summary:
            problems.append(f"{pack.name}: module {module.name}")
        for tool in module.tools:
            entry = catalog.get("tools", {}).get(tool.name)
            if not _entry_ok(entry, tool.source(), ("summary",)):
                problems.append(f"{pack.name}: tool {tool.name}")
                continue
            missing = [a.name for a in tool.args if a.doc and not str(entry.get("args", {}).get(a.name, "")).strip()]
            if missing:
                problems.append(f"{pack.name}: tool {tool.name} args {', '.join(missing)}")
    return problems


def write_catalog(pack: PackInfo, catalog: dict) -> None:
    I18N_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    catalog_path(pack).write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------
# 렌더
# --------------------------------------------------------------------------

LABELS = {
    "ko": {
        "banner": [
            "> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고",
            "> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는",
            "> [docs/architecture.md](../docs/architecture.md) 를 본다.",
        ],
        "other": "English: [README.en.md](README.en.md)",
        "item": "항목", "value": "값", "json": "패키지 JSON", "tools_count": "툴", "count_suffix": "개",
        "modules": "모듈 (`TOOL_MODULES`)", "overview": "개요", "tool_list": "툴 목록",
        "undo_note": "Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).",
        "tool": "툴", "module": "모듈", "description": "설명", "undo": "Undo",
        "details": "모듈별 상세", "no_description": "(설명 없음)",
        "arg": "인자", "type": "타입", "default": "기본값", "required": "필수",
        "untranslated": "",
    },
    "en": {
        "banner": [
            "> Generated from the code by `scripts/gen_pack_readmes.py`. Do not edit by hand: change",
            "> the tool docstrings (Korean) or the translation catalog `docs/i18n/en/` and regenerate.",
            "> For the server and pack structure see [docs/architecture.en.md](../docs/architecture.en.md).",
        ],
        "other": "한국어: [README.md](README.md)",
        "item": "Item", "value": "Value", "json": "Package JSON", "tools_count": "Tools", "count_suffix": "",
        "modules": "Modules (`TOOL_MODULES`)", "overview": "Overview", "tool_list": "Tools",
        "undo_note": "Tools marked ✓ in the Undo column change the scene; one call is one undo step (`@undoable`).",
        "tool": "Tool", "module": "Module", "description": "Description", "undo": "Undo",
        "details": "Details by module", "no_description": "(no description)",
        "arg": "Argument", "type": "Type", "default": "Default", "required": "required",
        "untranslated": " *(untranslated)*",
    },
}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _signature(tool: ToolInfo) -> str:
    parts = []
    for arg in tool.args:
        piece = arg.name
        if arg.annotation:
            piece += f": {arg.annotation}"
        if arg.default is not None:
            piece += f" = {arg.default}"
        parts.append(piece)
    return f"{tool.name}({', '.join(parts)})"


class Texts:
    """언어별로 설명 문구를 고른다. 영어 번역이 없거나 낡으면 원문에 표시를 붙인다."""

    def __init__(self, pack: PackInfo, lang: str, catalog: dict | None) -> None:
        self.pack = pack
        self.lang = lang
        self.catalog = catalog or {}
        self.mark = LABELS[lang]["untranslated"]

    def overview(self) -> tuple[str, bool]:
        source = self.pack.doc.strip()
        if self.lang == "ko":
            return source, True
        entry = self.catalog.get("overview", {}).get("text")
        if _entry_ok(entry, source, ("en",)):
            return entry["en"].strip(), True
        return source, False

    def module(self, module: ModuleInfo) -> str:
        if self.lang == "ko" or not module.summary:
            return module.summary
        entry = self.catalog.get("modules", {}).get(module.name)
        if _entry_ok(entry, module.summary, ("en",)):
            return entry["en"].strip()
        return module.summary + self.mark

    def tool(self, tool: ToolInfo) -> tuple[str, dict[str, str]]:
        arg_docs = {a.name: a.doc for a in tool.args}
        if self.lang == "ko":
            return tool.summary, arg_docs
        entry = self.catalog.get("tools", {}).get(tool.name)
        if _entry_ok(entry, tool.source(), ("summary",)):
            translated = entry.get("args", {})
            return entry["summary"].strip(), {
                a.name: (str(translated.get(a.name, "")).strip() or (a.doc + self.mark if a.doc else "")) for a in tool.args
            }
        return (tool.summary + self.mark if tool.summary else ""), {
            a.name: (a.doc + self.mark if a.doc else "") for a in tool.args
        }


def render(pack: PackInfo, lang: str = "ko", catalog: dict | None = None) -> str:
    label = LABELS[lang]
    texts = Texts(pack, lang, catalog)
    overview, overview_ok = texts.overview()
    count = f"{pack.tool_count}{label['count_suffix']}"
    lines = [
        f"# {pack.name}",
        "",
        label["other"],
        "",
        *label["banner"],
        "",
        f"| {label['item']} | {label['value']} |",
        "|---|---|",
        f"| {label['json']} | `packages/{pack.name}.json` |",
        f"| requires | {', '.join(f'`{r}`' for r in pack.requires) or '-'} |",
        f"| {label['tools_count']} | {count} |",
        f"| {label['modules']} | {', '.join(f'`{m.name}`' for m in pack.modules)} |",
        "",
        f"## {label['overview']}",
        "",
    ]
    if not overview_ok:
        lines += [label["untranslated"].strip(), ""]
    lines += ["```text", overview, "```", "", f"## {label['tool_list']}", "", label["undo_note"], ""]
    lines += [f"| {label['tool']} | {label['module']} | {label['description']} | {label['undo']} |", "|---|---|---|---|"]
    resolved = {}
    for module in pack.modules:
        for tool in module.tools:
            summary, arg_docs = texts.tool(tool)
            resolved[tool.name] = (summary, arg_docs)
            mark = "✓" if tool.undoable else ""
            lines.append(f"| [`{tool.name}`](#{tool.name}) | `{module.name}` | {_cell(summary)} | {mark} |")
    lines += ["", f"## {label['details']}", ""]
    for module in pack.modules:
        lines += [f"### `{module.name}`", ""]
        summary = texts.module(module)
        if summary:
            lines += [summary, ""]
        for tool in module.tools:
            tool_summary, arg_docs = resolved[tool.name]
            lines += [f"#### {tool.name}", "", "```python", _signature(tool), "```", "", tool_summary or label["no_description"], ""]
            if tool.args:
                lines += [f"| {label['arg']} | {label['type']} | {label['default']} | {label['description']} |", "|---|---|---|---|"]
                for arg in tool.args:
                    default = f"`{_cell(arg.default)}`" if arg.default is not None else label["required"]
                    annotation = _cell(arg.annotation) or "-"
                    lines.append(f"| `{arg.name}` | `{annotation}` | {default} | {_cell(arg_docs.get(arg.name, ''))} |")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="툴 팩마다 README.md / README.en.md 를 코드에서 만든다.")
    parser.add_argument("--check", action="store_true", help="README 가 어긋났거나 번역이 비었거나 낡았으면 1 로 끝낸다")
    parser.add_argument("--sync-i18n", action="store_true", help="번역 카탈로그에 새 항목을 넣고 낡은 항목을 표시한다")
    options = parser.parse_args()

    stale_files: list[str] = []
    problems: list[str] = []
    for pack in load_packs():
        if options.sync_i18n:
            catalog, pack_problems = sync_catalog(pack)
            write_catalog(pack, catalog)
            problems += pack_problems
            print(f"synced {catalog_path(pack).relative_to(REPO).as_posix()} ({len(pack_problems)} to translate)")
            continue
        catalog = load_catalog(pack)
        problems += translation_problems(pack, catalog)
        for lang, filename in (("ko", "README.md"), ("en", "README.en.md")):
            target = REPO / pack.name / filename
            text = render(pack, lang, catalog)
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if options.check:
                if current != text:
                    stale_files.append(target.relative_to(REPO).as_posix())
                continue
            if current != text:
                target.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {target.relative_to(REPO).as_posix()}")

    if options.sync_i18n:
        return 0
    if options.check:
        failed = False
        if stale_files:
            failed = True
            print("README 가 코드와 어긋났습니다. python scripts/gen_pack_readmes.py 로 다시 생성하세요:")
            for path in stale_files:
                print(f"  {path}")
        if problems:
            failed = True
            print(f"번역이 없거나 원문이 바뀐 항목 {len(problems)}개 (docs/i18n/en/). --sync-i18n 후 채우세요:")
            for problem in problems[:40]:
                print(f"  {problem}")
        return 1 if failed else 0
    if problems:
        print(f"주의: 번역이 없거나 낡은 항목 {len(problems)}개는 README.en.md 에 원문으로 실렸습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
