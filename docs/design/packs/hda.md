# houdini_mcp_hda — HDA 저작·관리

> 먼저 [README.md](README.md) 를 읽는다.

## 무엇을 담나

서브넷을 디지털 에셋으로 굽고, 인터페이스를 짓고, 설치·버전 관리하는 것.

기존 구현이 가진 것: fx HDAs 10 + dcc hda 10 + hda-automation 6 (중복 제거 후
~20). `create_hda`, `install_hda`, `reload_hda`, `uninstall_hda`,
`list_installed_hdas`, `get_hda_info`, `get/set_hda_section_content`,
`author_hda_interface`, `promote_hda_parameters`, `publish_hda_library`,
`save_node_as_hda`, `sync_hda_instance`, `validate_hda_contract`,
`inspect_hda_definition`, `scan_hda_libraries`, `instantiate_hda`.

## 기존 구현이 한 방식과 그 한계

- **파라미터 인터페이스를 문자열로 만든다.** `.hda` 안의 `DialogScript` 를
  텍스트로 조립하는 곳이 있다. 포맷이 바뀌면 깨지고, 검증이 안 된다.
- **HDA 가 유효한지 모른다.** 만들고 나서 인스턴스화해 보지 않는다.
- **`hotl` 을 안 쓴다.** 실측 확인: `$HFS/bin/hotl.exe` 가 있다.
  (다만 아래 "hotl 을 쓰지 않는 이유" 를 볼 것 — 써서는 안 되는 이유가 있었다.)

## 우리가 쓸 경로

### 1. 인터페이스는 `hou.ParmTemplate` 으로 짓는다

실측 확인한 `hou.HDADefinition` 메서드 (Houdini 22.0.368):

```
parmTemplateGroup / setParmTemplateGroup
addParmTuple / replaceParmTuple / removeParmTuple / addParmFolder / removeParmFolder
sections / addSection / removeSection / hasSection
extraFileOptions / setExtraFileOption / removeExtraFileOption
setIcon / setDescription / setComment / setVersion
setMinNumInputs / setMaxNumInputs / setMaxNumOutputs
save / copyToHDAFile / updateFromNode / isInstalled / isPreferred / destroy
options / setOptions / tools / userInfo / modificationTime
```

문서 초안에 있던 `installed` 는 없다 — `isInstalled()` 뿐이다.
`setMinNumOutputs` 도 없다(`maxNumOutputs` 만 설정 가능).

`hou.ParmTemplateGroup` 을 만들어 `setParmTemplateGroup()` 으로 넣는다.
DialogScript 문자열을 손으로 만들지 않는다.

```python
group = definition.parmTemplateGroup()
group.append(hou.FloatParmTemplate("radius", "Radius", 1,
                                    default_value=(1.0,),
                                    min=0.0, max=10.0))
definition.setParmTemplateGroup(group)
```

템플릿 생성은 `houdini_mcp_base` 의 `parmtemplate` 헬퍼를 쓴다. base 의
`add_spare_parm` 과 같은 헬퍼를 공유하므로 종류 이름과 에러 메시지가 한 벌이다.

`promote_parm` 은 **내부 노드의 parmTemplate 을 그대로 꺼내 올린다.**
이름·타입·범위·메뉴가 자동으로 따라온다. 문자열 조립이면 이게 안 된다.

### 2. 만들면 인스턴스화해서 검증한다

HDA 를 굽고 끝내지 않는다.

1. 카테고리에 맞는 임시 컨테이너를 만든다 (Sop→geo, Lop→lopnet, Object→/obj ...)
2. 그 안에 인스턴스를 하나 만든다
3. 파라미터를 걸고 쿡해 본다
4. 에러·경고·지오메트리 통계를 읽고, 정의의 인터페이스가 인스턴스에 다
   나타났는지 본다
5. **임시 노드를 지운다** — 실패해도 지운다 (`try/finally`)

이것이 `validate_hda` 의 올바른 형태다. ROP(Driver) 카테고리는 쿡이 곧 렌더라
쿡하지 않고 인스턴스화와 파라미터만 본다.

### 3. `hou.hda` 모듈을 쓴다

실측 확인한 것:

```
hou.hda.installFile / installFiles / uninstallFile / reloadFile / reloadAllFiles
hou.hda.definitionsInFile / loadedFiles
hou.hda.expandToDirectory / collapseFromDirectory     ← 버전 관리에 중요
hou.hda.componentsFromFullNodeTypeName / fullNodeTypeNameFromComponents
hou.hda.safeguardHDAs / setSafeguardHDAs
```

`expandToDirectory` 는 `.hda` 를 정의마다 디렉토리로, 섹션마다 파일로 펼친다.
기존 구현에 이 개념이 없다.

### 4. 네임스페이스와 버전을 제대로 다룬다

`namespace::name::version` 형식이다.
`hou.hda.fullNodeTypeNameFromComponents()` 로 조립하고
`componentsFromFullNodeTypeName()` 로 분해한다. 문자열을 `::` 로 쪼개지 않는다.

---

## 실측 결과 — 초안과 달랐던 것

여기부터는 2026-09-13 에 Houdini 22.0.368 (Apprentice 라이선스) 로 실제
확인한 것이다. 초안의 설명과 다른 부분을 고쳐 둔다.

### `createDigitalAsset` 은 `hou.Node` 가 아니라 `hou.OpNode` 에 있다

`hou.Node` 에는 `canCreateDigitalAsset` 만 있다. 실제 시그니처:

```
OpNode.createDigitalAsset(name=None, hda_file_name=None, description=None,
                          min_num_inputs=0, max_num_inputs=0,
                          compress_contents=False, comment=None, version=None,
                          save_as_embedded=False, ignore_external_references=False,
                          compile_asset=False, change_node_type=True,
                          create_backup=True, install_path=None) -> Node
```

돌려주는 것은 새 타입의 **인스턴스 노드**다(원래 서브넷 자리에 그대로 들어선다).
정의는 거기서 `node.type().definition()` 으로 잡는다.

### 타입 이름의 버전과 정의의 `version()` 은 별개다

`create` 에 `name="ns::asset::1.0"` 을 줘도 `definition.version()` 은 `''` 다.
`version()` / `setVersion()` 은 타입 이름과 무관한 별도 메타데이터이며, 쓰면
`Version` 섹션이 새로 생긴다. 둘이 어긋나면 읽는 쪽이 헷갈리므로
`create_hda` 가 둘을 함께 맞춘다. `hda_info` 는 둘 다 돌려준다.

### 설치되지 않은 정의를 저장하면 섹션이 사라진다

`hou.hda.definitionsInFile()` 로 얻은 정의는 설치돼 있지 않을 수 있다
(`isInstalled() == False`). 그 상태로 `save()` 하면 `CreateScript`,
`InternalFileOptions`, `ExtraFileOptions` 가 **통째로 빠진다** (측정:
5개 섹션 → 2개). 그래서 저장하는 모든 경로가 `isInstalled()` 를 먼저 본다.

### `expandToDirectory` 만으로는 Git 친화가 아니다

이것이 가장 크게 어긋난 부분이다.

| 상태 | 노드 그래프 섹션 | Git 이 보는 것 |
|---|---|---|
| 기본 저장 후 펼침 | `Contents.gz` (gzip) | 완전한 바이너리 |
| `setCompressContents(False)` 후 펼침 | `Contents` (아스키 + NUL 프레이밍) | 바이너리로 분류하지만 `--text` 로 읽힘 |

기본 저장은 내용물을 압축한다. 펼쳐도 `Contents.gz` 는 gzip 덩어리라 diff 가
전혀 안 된다 — 정작 노드 그래프가 들어 있는 파일이 그것이다.
`HDAOptions.setCompressContents(False)` 로 다시 저장하면 `Contents` 가 되어
내용이 아스키로 읽히지만, 블록 구분용 NUL 바이트가 섞여 있어 Git 은 여전히
바이너리로 분류한다.

**그래도 펼치는 값어치는 충분하다.** 리뷰에서 실제로 봐야 하는 것 —
파라미터 인터페이스(`DialogScript`), 콜백 스크립트(`PythonModule` 등),
`CreateScript` — 은 펼치면 완전한 텍스트다. 측정한 예시(파라미터 하나 올린 SOP
에셋)에서 11개 파일 중 9개가 순수 텍스트였다.

그래서 `expand_hda` 는 파일마다 `kind` 를 붙여 돌려준다 — `text`(그대로 diff),
`framed`(아스키지만 NUL 프레이밍), `binary`(읽히지 않음). `opaque` 가 비어
있으면 전부 눈으로 볼 수 있다는 뜻이다.

`collapseFromDirectory` 왕복은 손실이 없었다 — 정의·섹션·파라미터가 모두 살아
돌아왔고, 접은 뒤 인스턴스화해 쿡까지 성공했다.

### hotl 을 쓰지 않는 이유

`$HFS/bin/hotl` 은 있고 플래그도 초안대로다 (`-x`/`-X` 펼치기, `-t` VCS 친화
펼치기, `-c`/`-C`/`-l` 접기, `-m`/`-M` 병합). 그런데 **비상업용 라이선스에서
내용물 변환이 조용히 실패한다.**

```
$ hotl -t <dir> asset.hda
Cannot convert non-commercial HDAs
$ hotl -X <dir> asset.hda
Opened .../Contents.contents
ERROR?? 0 blocks
```

둘 다 종료 코드는 0 이고, 만들어진 `Contents.mime` / `Contents.contents` 는
**0 바이트**다. 접어서 되돌리면 노드 그래프가 사라진다. 데이터를 잃는 경로를
툴로 노출할 수 없으므로 외부 프로세스를 부르지 않고 HOM 안에서만 처리한다.
`-M` 병합이 하는 일은 `HDADefinition.copyToHDAFile` 이 같은 파일에 반복
호출하는 것으로 대신한다(`save_as_hda`).

### `hou.nodeType()` 은 경로 문자열을 안 받는다

`hou.nodeType("Sop/ns::asset::1.0")` 은 `None` 을 준다. 카테고리 객체가
필요하다: `hou.nodeType(hou.sopNodeTypeCategory(), "ns::asset::1.0")`.
`_common.resolve_node_type` 이 `hou.nodeTypeCategories()` 로 처리한다.

### 해제하면 인스턴스가 깨진다

인스턴스가 살아 있는 상태에서 `hou.hda.uninstallFile` 을 부르면 그 노드들이
"Unable to find dialog script" 상태가 된다. 그래서 `uninstall_hda` 는 먼저
인스턴스를 세어 있으면 경로를 알려 주고 거부한다 (`force=True` 로 넘길 수 있다).

### `matchesCurrentDefinition()` 은 신뢰할 수 없다

hython 에서 구운 직후에도, `updateFromNode` 직후에도 `False` 를 준다.
"동기화가 필요한가" 를 이걸로 판단하지 않는다. 그래서 `sync_hda_instance` 류
툴을 만들지 않았다.

---

## 구현한 툴 (19개)

| 모듈 | 툴 |
|---|---|
| `create` | `create_hda`, `save_as_hda` |
| `interface` | `hda_interface`, `add_hda_parm`, `promote_parm`, `remove_hda_parm`, `reorder_hda_parms` |
| `sections` | `hda_sections`, `get_hda_section`, `set_hda_section`, `remove_hda_section` |
| `manage` | `install_hda`, `uninstall_hda`, `reload_hda`, `list_installed_hdas`, `hda_info` |
| `vcs` | `expand_hda`, `collapse_hda` |
| `check` | `validate_hda` |

초안의 `list_sections` / `get_section` / `set_section` 은 `hda_` 접두사를 붙였다.
레지스트리가 전역 이름공간이라 `list_sections` 같은 이름은 다른 팩과 부딪히기
쉽고, 무엇의 섹션인지도 드러나지 않는다. `remove_hda_section` 을 더해 짝을
맞췄다.

`publish_hda_library` 는 만들지 않는다. 스튜디오 경로 규칙에 묶여 있다
(README 의 "범위 밖" 참고). 라이브러리를 한 파일에 모으는 일 자체는
`save_as_hda` 를 같은 `hda_file` 로 반복 호출하면 된다.

### `houdini_mcp_base` 의 `parmedit` 과의 경계

|  | base 의 `add_spare_parm` | 여기의 `add_hda_parm` |
|---|---|---|
| 대상 | 노드 인스턴스 하나 | HDA 정의 |
| 범위 | 그 노드에만 남는다 | 그 타입의 모든 인스턴스 |
| 저장 | hip 파일 | .hda 파일 |

`link_parms`(base)는 아무 파라미터 둘을 잇는 범용 툴이고, `promote_parm`(여기)은
내부 템플릿을 인터페이스로 올리면서 링크까지 한 번에 하는 HDA 전용 경로다.

## 검증

아래 시나리오를 실제로 돌려 통과했다.

```
서브넷 만들기 → create_hda → 설치됨 확인
→ promote_parm 으로 내부 파라미터 올리기 → hda_interface 에 보이는가
→ add_hda_parm / reorder_hda_parms / remove_hda_parm
→ set_hda_section(PythonModule) → get_hda_section 으로 되읽기
→ validate_hda → 인스턴스화 + 쿡 성공, 임시 노드 정리 확인
→ expand_hda → 디렉토리 생김 → collapse_hda → 다시 로드되고 쿡되는가
```

추가로 확인한 것:

- 일부러 깨뜨린 에셋(입력 없는 blast)을 `validate_hda` 가 잡는다 —
  `ok: false`, `errors: ["Not enough sources specified."]`.
- 검증이 실패해도 임시 노드가 남지 않는다.
- Sop 뿐 아니라 Object, Lop 카테고리 에셋도 인스턴스화·쿡된다.
