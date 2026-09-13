# houdini_mcp_cop

English: [README.en.md](README.en.md)

> 이 파일은 `scripts/gen_pack_readmes.py` 가 코드에서 생성한다. 손으로 고치지 말고
> 툴의 docstring 을 고친 뒤 다시 생성한다. 서버와 팩의 구조는
> [docs/architecture.md](../docs/architecture.md) 를 본다.

| 항목 | 값 |
|---|---|
| 패키지 JSON | `packages/houdini_mcp_cop.json` |
| requires | `houdini_mcp` |
| 툴 | 2개 |
| 모듈 (`TOOL_MODULES`) | `preview` |

## 개요

```text
COP(Copernicus) 전문 팩 - 이미지 네트워크의 결과를 본다.

    preview  cop_preview(노드 출력을 그림으로), cop_layer_info(레이어 수치)

만든 계기(2026-09-13, 성 파괴 씬): COP 으로 석재·지면 텍스처를 만들었는데 결과를
볼 방법이 없어 파일로 내보낸 뒤 외부 도구로 PNG 를 만들어 봤다. 단일 채널 맵은
검게 나와 사실상 확인하지 못한 채 재질에 붙였고, 렌더에서 스펀지 같은 품질로
드러났다. COP 의 composite view 에 해당하는 것을 모델이 직접 볼 수 있어야 한다.

옛 COP2(cop2net)는 다루지 않는다. Houdini 20.5 부터의 Copernicus(copnet)만 받는다.

여기서 모듈을 import 하지 않는다. register_pack 이 TOOL_MODULES 를 읽어 하나씩
격리해서 읽으므로, 모듈 하나가 깨져도 나머지 툴은 등록된다.
```

## 툴 목록

Undo 열이 ✓ 인 툴은 씬을 바꾸며, 호출 하나가 Undo 하나로 묶인다(`@undoable`).

| 툴 | 모듈 | 설명 | Undo |
|---|---|---|---|
| [`cop_preview`](#cop_preview) | `preview` | COP 노드가 만든 이미지를 그림으로 본다. composite view 를 대신한다. |  |
| [`cop_layer_info`](#cop_layer_info) | `preview` | COP 노드의 출력마다 레이어 정보를 수치로 돌려준다. |  |

## 모듈별 상세

### `preview`

COP 노드의 결과 이미지를 보고 수치로 읽는다.

#### cop_preview

```python
cop_preview(nodes: list[str], frame: float | None = None, tile_size: int = 384, columns: int = 4, normalize: str = 'auto')
```

COP 노드가 만든 이미지를 그림으로 본다. composite view 를 대신한다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `nodes` | `list[str]` | 필수 | COP 노드 경로들. 출력을 고르려면 ":" 뒤에 이름이나 번호를 붙인다. 최대 16개. 예: ["/img/tex/noise1", "/img/tex/worley1:dist2"] |
| `frame` | `float \| None` | `None` | 볼 프레임. 생략하면 현재 프레임. |
| `tile_size` | `int` | `384` | 칸 하나의 한 변 픽셀. 이미지 비율은 유지한다. |
| `columns` | `int` | `4` | 한 줄의 칸 수. |
| `normalize` | `str` | `'auto'` | "auto", "on"(항상 범위로 늘림), "off"(항상 0..1 로 자름). |

#### cop_layer_info

```python
cop_layer_info(path: str, frame: float | None = None)
```

COP 노드의 출력마다 레이어 정보를 수치로 돌려준다.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `path` | `str` | 필수 | COP 노드 경로. 예: "/img/tex/worley1" |
| `frame` | `float \| None` | `None` | 볼 프레임. 생략하면 현재 프레임. |
