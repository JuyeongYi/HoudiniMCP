# houdini_mcp_example

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_example.json` |
| requires | `houdini_mcp` |
| 툴 | 1개 |
| 모듈 (`TOOL_MODULES`) | `tools` |

## 개요

```text
툴 팩을 만드는 법을 보여주는 최소 예시 팩.

TOOL_MODULES 에 툴이 든 모듈 이름을 적으면 register_pack 이 하나씩 읽는다.
모듈을 여기서 import 하지 않는 이유는, 하나가 깨져도 나머지가 등록되게 하기
위해서다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`tool_catalog`](#tool_catalog) | `tools` | 등록된 모든 툴의 이름, 설명, 소속 팩. |  |

## 모듈별 상세

### `tools`

툴 팩을 만드는 법을 보여주는 최소 예시.

#### tool_catalog

```python
tool_catalog()
```

등록된 모든 툴의 이름, 설명, 소속 팩.
