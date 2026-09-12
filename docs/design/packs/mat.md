# houdini_mcp_mat — 머티리얼·룩데브 전문

> 먼저 [README.md](README.md) 를 읽는다.

## 무엇을 담나

셰이더를 만들고, 잇고, 할당하고, 텍스처를 붙이는 것.

기존 구현이 가진 것: dcc material-library 12 + lookdev 12,
fx `create_material` / `assign_material`. 합쳐서 23개.

- 저작: `create_material`, `connect_shader`, `disconnect_shader`,
  `set_material_parms`, `set_material_attribute`
- 조회: `list_materials`, `get_material_parms`, `get_shader_connections`,
  `get_material_connections`, `list_assignments`, `get_shader_assignment`
- 텍스처: `assign_texture`, `list_images`, `reload_image`
- 컬러: `list_color_spaces`, `set_color_management`
- 프리셋: `save_preset` / `load_preset` / `list_presets` / `delete_preset`
  (material-library 와 lookdev 양쪽에 중복돼 있다 — 하나로 합친다)

## 기존 구현이 한 방식과 그 한계

전부 **VOP 노드를 만들고 잇는 수준**에 머문다. `connect_shader(a, b)` 는
`node.setInput()` 래퍼다.

이 방식이 놓치는 것:

- **셰이더가 유효한지 모른다.** 타입이 안 맞는 연결, 빠진 입력, 순환 참조를
  잡지 못한다.
- **머티리얼이 실제로 어떻게 보이는지 모른다.** 값만 던지고 끝난다.
- **컬러 스페이스를 문자열로 다룬다.** OCIO 설정을 읽지 않는다.
- **프리셋을 자체 JSON 포맷으로 저장한다.** 다른 도구에서 못 읽는다.

## 우리가 쓸 경로

### 1. MaterialX 1.39.5 가 번들돼 있다 (실측 확인)

```python
import MaterialX as mx
doc = mx.createDocument()
mx.readFromXmlFile(doc, path)
valid, message = doc.validate()      # 타입·연결 검증을 라이브러리가 해 준다
```

Houdini 22 의 MaterialX 빌더(`mtlxstandard_surface` 등)로 만든 것은 MaterialX
문서로 내보낼 수 있다. 검증·상호운용·프리셋 저장을 **자체 포맷이 아니라
MaterialX 로** 한다. 그러면 Blender·Maya·USD 어디서든 읽힌다.

먼저 확인한다: Houdini 22 에서 VOP 서브넷 → MaterialX 문서로 내보내는 경로가
무엇인지 (`hou.VopNode` 의 메서드, MaterialX ROP, 또는 `husd` 헬퍼).

### 2. USD 머티리얼은 `UsdShade` 로 읽는다

LOP 컨텍스트의 머티리얼은 노드 파라미터가 아니라 스테이지에서 읽는다.

```python
from pxr import UsdShade
stage = lop.stage()
mat = UsdShade.Material(stage.GetPrimAtPath("/materials/wood"))
surface = mat.GetSurfaceOutput()
for shader_input in UsdShade.Shader(...).GetInputs():
    ...
```

할당도 `UsdShade.MaterialBindingAPI` 로 **실제 바인딩을 질의**한다. Assign
노드가 무엇을 걸었는지 파라미터에서 추측하지 않는다.

`houdini_mcp_lop` 와 겹치는 지점이다. **머티리얼 자체는 이 팩, 스테이지 일반은
lop 팩.** 경계를 문서에 적어 두고 중복 툴을 만들지 않는다.

### 3. 텍스처는 OpenImageIO 로 실제로 읽는다 (2.5.18.0, 실측 확인)

```python
import OpenImageIO as oiio
inp = oiio.ImageInput.open(path)
spec = inp.spec()      # 해상도, 채널, 비트뎁스, 컬러스페이스 메타데이터
```

`assign_texture` 가 파일 경로만 받고 끝나지 않는다. 파일이 실제로 있는지,
해상도가 얼마인지, 채널이 맞는지(노멀맵에 3채널이 있는지), 컬러스페이스
메타데이터가 무엇인지 확인해 돌려준다. UDIM 타일도 `pathlib.glob` 으로 몇 장이
실제로 있는지 센다.

### 4. 컬러 매니지먼트는 OCIO 설정에서 읽는다

`list_color_spaces` 를 하드코딩된 목록으로 만들지 않는다. Houdini 의 OCIO
설정에서 얻는다 — `hou.Color` / `$OCIO` 환경변수 / `PyOpenColorIO` 가 번들에
있는지 먼저 확인한다.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `build` | `create_material` (principled / mtlx standard surface / usd preview), `connect_shader`, `disconnect_shader`, `set_material_parms` |
| `inspect` | `list_materials`, `material_info` (파라미터 + 연결 + 할당 전부), `shader_graph` (그래프 구조), `validate_material` (MaterialX 검증) |
| `assign` | `assign_material`, `list_assignments` — SOP 어트리뷰트 방식과 LOP 바인딩 방식 둘 다 |
| `texture` | `assign_texture` (OIIO 로 검사), `texture_info`, `list_textures` (씬이 참조하는 이미지 전부 + 존재 여부), `reload_textures` |
| `color` | `list_color_spaces`, `set_color_space` |
| `preset` | `save_material` / `load_material` — **MaterialX 문서로**. 자체 포맷 금지 |

`delete_preset` 같은 파일 삭제 툴은 만들지 않는다. 되돌릴 수 없고 MCP 툴로
노출할 이유가 없다.

## 먼저 확인할 것

1. Houdini 22 에서 VOP ↔ MaterialX 문서 왕복 경로
2. `PyOpenColorIO` 번들 여부
3. `hou.fileReferences()` 로 텍스처 참조를 긁는 방법 (실측 확인: 함수는 있다)
4. Karma / MaterialX / Principled 중 무엇을 기본으로 할지 — 22.0 의 권장 경로

## 검증

```
머티리얼 만들기 → validate_material 통과
→ 텍스처 붙이기 → texture_info 로 해상도·채널 확인
→ 지오메트리에 할당 → list_assignments 에 나오는가
→ MaterialX 로 저장 → 다시 읽어서 같은가
```
