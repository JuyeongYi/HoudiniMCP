# houdini_mcp_io — 임포트·익스포트·의존성

> 먼저 [README.md](README.md) 를 읽는다.

## 무엇을 담나

씬 밖으로 내보내고 안으로 들이는 것, 그리고 **씬이 무엇에 의존하는지** 아는 것.

기존 구현이 가진 것: dcc interchange 6 (`export_usd`, `export_alembic`,
`export_fbx`, `export_geometry`, `import_geometry`, `probe_file`),
dcc export-preset 4, fx `import_file` / `export_file`, dcc pipeline 의
`collect_dependencies`.

## 기존 구현이 한 방식과 그 한계

- **ROP 를 만들고 렌더 버튼을 누르는 래퍼다.** 나가는 파일이 실제로 맞는지
  확인하지 않는다.
- **의존성 수집이 문자열 스캔이다.** 파라미터를 훑어 `.exr` 로 끝나는 것을
  찾는 식이다. 표현식·변수·UDIM 이 들어가면 틀린다.

## 우리가 쓸 경로

### 1. 의존성은 `hou.fileReferences()` 로 (실측 확인: 있다)

Houdini 가 **자기가 참조하는 파일을 안다.** 파라미터를 스캔하지 않는다.

```python
for parm, path in hou.fileReferences():
    # parm 은 None 일 수 있다 (씬 자체 참조)
    node = parm.node() if parm else None
```

여기에 얹는다:

- `hou.text.expandString()` 으로 변수를 푼다 (`$HIP`, `$JOB`, `$F`)
- UDIM/시퀀스는 `pathlib.Path.glob` 으로 **실제로 몇 장 있는지** 센다
- 각 파일의 존재 여부·크기·수정 시각을 확인한다
- **없는 파일을 목록으로 준다** — 이게 `validate_scene` 의 핵심이다

`collect_dependencies` 는 파일을 한 디렉토리로 모으는 것까지 한다.
`shutil.copy2` 와 `pathlib` 로, 경로 구분자 하드코딩 없이.

### 2. 내보낸 것을 검증한다

내보내고 끝내지 않는다. 파일 종류마다 다시 읽어서 확인한다.

| 포맷 | 검증 경로 |
|---|---|
| USD | `pxr.Usd.Stage.Open()` → 프림 수, 계층, 바운딩박스 |
| Alembic | 파이썬 바인딩은 **없다**(실측 확인). `abcecho` / `abcinfo` 가 `$HFS/bin` 에 있는지 확인해 쓴다. 없으면 Alembic SOP 로 다시 읽어 대조 |
| bgeo/obj/ply | `hou.Geometry.loadFromFile()` 또는 File SOP 로 다시 읽어 점·프림 수 대조 |
| FBX | Houdini 의 FBX 임포터로 다시 읽어 대조 |
| 이미지 | `OpenImageIO` (2.5.18.0 실측 확인) |

"내보냈는데 비어 있었다"를 그 자리에서 잡는다.

### 3. `probe_file` 은 진짜로 파일을 연다

경로와 확장자로 추측하지 않는다. 실제로 열어서 무엇이 들었는지 돌려준다 —
USD 면 프림 수와 up axis, 이미지면 해상도와 채널, 지오메트리면 점·프림 수와
어트리뷰트 목록. 임포트 전에 이걸 부르면 쓸데없는 임포트를 안 한다.

### 4. 경로는 전부 `pathlib`

이 팩은 경로를 가장 많이 다룬다. `CLAUDE.md` 의 멀티플랫폼 규칙이 특히 중요하다.
`os.sep` / `os.pathsep` / `Path.home()` / `tempfile`. 문자열 결합 금지.

## 툴 초안

| 모듈 | 툴 |
|---|---|
| `export` | `export_geometry` (bgeo/obj/ply/stl), `export_usd`, `export_alembic`, `export_fbx` — 전부 **내보낸 뒤 다시 읽어 검증** |
| `import` | `import_geometry`, `import_usd`, `probe_file` |
| `deps` | `list_dependencies` (`fileReferences` 기반 + 존재 여부), `missing_files`, `collect_dependencies` (한 곳으로 모으기), `remap_paths` |
| `check` | `validate_scene` — 없는 파일, 절대 경로(이식 불가), `$HIP` 밖 참조 |

`save_export_preset` 계열은 만들지 않는다. 프리셋 파일 포맷을 자체로 만드는
것은 README 제1원칙에 어긋난다. 필요하면 ROP 프리셋(Houdini 기본)을 쓴다.

## 먼저 확인할 것

1. `hou.fileReferences()` 의 정확한 반환 형태와 인자 (`include_all_refs` 등)
2. `$HFS/bin` 에 `abcecho` / `abcinfo` 가 있는지
3. `hou.Geometry.loadFromFile()` / `saveToFile()` 시그니처
4. 22.0 의 USD ROP 이름과 필수 파라미터 (`usd_rop`? `usdexport`?)
5. `hou.hipFile.collisionFreeName` 같은 헬퍼가 있는지

## 검증

```
box → export_geometry(.bgeo.sc) → 다시 읽어 점 8개 확인
→ 텍스처 참조 걸기 → list_dependencies 에 나오는가
→ 파일 지우기 → missing_files 가 잡는가
→ collect_dependencies → 새 디렉토리에 모였는가
```
