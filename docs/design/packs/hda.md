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

## 우리가 쓸 경로

### 1. 인터페이스는 `hou.ParmTemplate` 으로 짓는다

실측 확인한 `hou.HDADefinition` 메서드:

```
parmTemplateGroup / setParmTemplateGroup
addParmTuple / replaceParmTuple / removeParmTuple / addParmFolder / removeParmFolder
sections / addSection / removeSection / hasSection
setIcon / setDescription / setComment / setVersion / setMinNumInputs / setMaxNumInputs
save / copyToHDAFile / updateFromNode / installed / isInstalled / isPreferred
options / setOptions / extraFileOptions / tools / userInfo
```

`hou.ParmTemplateGroup` 을 만들어 `setParmTemplateGroup()` 으로 넣는다.
DialogScript 문자열을 손으로 만들지 않는다.

```python
group = definition.parmTemplateGroup()
group.append(hou.FloatParmTemplate("radius", "Radius", 1,
                                    default_value=(1.0,),
                                    min=0.0, max=10.0))
definition.setParmTemplateGroup(group)
```

`promote_hda_parameters` 는 **내부 노드의 parmTemplate 을 그대로 꺼내
올린다.** 이름·타입·범위·메뉴가 자동으로 따라온다. 문자열 조립이면 이게 안 된다.

### 2. 만들면 인스턴스화해서 검증한다

HDA 를 굽고 끝내지 않는다.

1. `installed` 확인
2. 임시 컨테이너에 인스턴스를 하나 만든다
3. 쿡해 본다
4. 파라미터가 다 보이는지, 에러가 없는지 확인
5. **임시 인스턴스를 지운다** (씬을 오염시키지 않는다)

이것이 `validate_hda` 의 올바른 형태다.

### 3. `hou.hda` 모듈을 쓴다

실측 확인한 것:

```
hou.hda.installFile / installFiles / uninstallFile / reloadFile / reloadAllFiles
hou.hda.definitionsInFile / loadedFiles
hou.hda.expandToDirectory / collapseFromDirectory     ← 버전 관리에 중요
hou.hda.componentsFromFullNodeTypeName / fullNodeTypeNameFromComponents
hou.hda.safeguardHDAs / setSafeguardHDAs
```

`expandToDirectory` 는 `.hda` 를 디렉토리로 펼친다. **Git 에 올릴 때 필수**다.
바이너리 `.hda` 는 diff 가 안 된다. 기존 구현에 이 개념이 없다.

`hotl` 실행 파일도 같은 일을 커맨드라인에서 한다.

### 4. 네임스페이스와 버전을 제대로 다룬다

`namespace::name::version` 형식이다.
`hou.hda.fullNodeTypeNameFromComponents()` 로 조립하고
`componentsFromFullNodeTypeName()` 로 분해한다. 문자열을 `::` 로 쪼개지 않는다.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `create` | `create_hda` (서브넷 → HDA. 네임스페이스·버전·아이콘·설명), `save_as_hda` |
| `interface` | `hda_interface` (파라미터 구조 읽기), `add_hda_parm`, `promote_parm` (내부 노드에서 끌어올림), `remove_hda_parm`, `reorder_hda_parms` |
| `sections` | `list_sections`, `get_section`, `set_section` — PythonModule, OnCreated 등 |
| `manage` | `install_hda`, `uninstall_hda`, `reload_hda`, `list_installed_hdas`, `hda_info` |
| `vcs` | `expand_hda` (디렉토리로 펼침), `collapse_hda` — Git 용 |
| `check` | `validate_hda` — 인스턴스화해서 쿡까지. 임시 노드는 반드시 정리 |

`publish_hda_library` 는 만들지 않는다. 스튜디오 경로 규칙에 묶여 있다
(README 의 "범위 밖" 참고).

## 먼저 확인할 것

1. `hou.ParmTemplate` 서브클래스 전체와 각 생성자 인자
2. `definition.save()` 와 `copyToHDAFile()` 의 차이, `create_backup` 옵션
3. `hou.Node.createDigitalAsset()` 의 정확한 시그니처
4. `expandToDirectory` 가 만드는 구조와 `collapseFromDirectory` 왕복이 손실
   없는지
5. `hotl --help`

## 검증

```
서브넷 만들기 → create_hda → 설치됨 확인
→ promote_parm 으로 내부 파라미터 올리기 → hda_interface 에 보이는가
→ validate_hda → 인스턴스화 + 쿡 성공, 임시 노드 정리 확인
→ expand_hda → 디렉토리 생김 → collapse_hda → 다시 로드되는가
```
