"""툴 팩마다 README.md 를 코드에서 만든다.

툴 정보(이름, 설명, 인자, Undo 여부)는 코드의 docstring 과 시그니처가 원본이다.
README 를 손으로 쓰면 코드와 금방 어긋나므로, 여기서 생성한다. 설명을 고치려면
README 가 아니라 docstring 을 고친 뒤 다시 생성한다.

Houdini 없이 돈다. 코드를 import 하지 않고 AST 로만 읽는다(hou 가 없어도 된다).

    python scripts/gen_pack_readmes.py          # 모든 팩의 README.md 를 쓴다
    python scripts/gen_pack_readmes.py --check  # 코드와 어긋난 README 가 있으면 실패
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER_PACKAGE = "houdini_mcp"
ARCHITECTURE_DOC = "docs/architecture.md"


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


def render(pack: PackInfo) -> str:
    lines = [
        f"# {pack.name}",
        "",
        "> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고",
        "> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는",
        f"> [{ARCHITECTURE_DOC}](../{ARCHITECTURE_DOC}) 를 본다.",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 패키지 JSON | `{pack.name}.json` |",
        f"| requires | {', '.join(f'`{r}`' for r in pack.requires) or '-'} |",
        f"| 툴 | {pack.tool_count}개 |",
        f"| 모듈 (`TOOL_MODULES`) | {', '.join(f'`{m.name}`' for m in pack.modules)} |",
        "",
        "## 개요",
        "",
        "```text",
        pack.doc.strip(),
        "```",
        "",
        "## 툴 목록",
        "",
        "Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).",
        "",
        "| 툴 | 모듈 | 설명 | Undo |",
        "|---|---|---|---|",
    ]
    for module in pack.modules:
        for tool in module.tools:
            lines.append(f"| [`{tool.name}`](#{tool.name}) | `{module.name}` | {_cell(tool.summary)} | {'✓' if tool.undoable else ''} |")
    lines += ["", "## 모듈별 상세", ""]
    for module in pack.modules:
        lines.append(f"### `{module.name}`")
        lines.append("")
        if module.summary:
            lines += [module.summary, ""]
        for tool in module.tools:
            lines += [f"#### {tool.name}", "", "```python", _signature(tool), "```", "", tool.summary or "(설명 없음)", ""]
            if tool.args:
                lines += ["| 인자 | 타입 | 기본값 | 설명 |", "|---|---|---|---|"]
                for arg in tool.args:
                    default = f"`{_cell(arg.default)}`" if arg.default is not None else "필수"
                    lines.append(f"| `{arg.name}` | `{_cell(arg.annotation) or '-'}` | {default} | {_cell(arg.doc)} |")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="툴 팩마다 README.md 를 코드에서 만든다.")
    parser.add_argument("--check", action="store_true", help="코드와 어긋난 README 가 있으면 1 로 끝낸다")
    options = parser.parse_args()

    stale = []
    for pack_json in sorted(REPO.glob(f"{SERVER_PACKAGE}_*.json")):
        pack = load_pack(pack_json)
        target = REPO / pack.name / "README.md"
        text = render(pack)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if options.check:
            if current != text:
                stale.append(target.relative_to(REPO).as_posix())
            continue
        if current != text:
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {target.relative_to(REPO).as_posix()} ({pack.tool_count} tools)")
        else:
            print(f"up to date {target.relative_to(REPO).as_posix()}")
    if stale:
        print("README 가 코드와 어긋났습니다. python scripts/gen_pack_readmes.py 로 다시 생성하세요:")
        for path in stale:
            print(f"  {path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
