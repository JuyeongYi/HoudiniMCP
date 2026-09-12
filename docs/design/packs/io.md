# houdini_mcp_io — 임포트·익스포트·의존성

> 먼저 [README.md](README.md) 를 읽는다.
>
> **구현 완료.** 아래는 Houdini 22.0.368 에서 실측으로 확인한 내용이다. 초안과
> 다른 곳은 실측이 이겼다.

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

---

## 실측 — 초안이 틀렸던 것

### 1. `saveToFile` 은 `.usd` / `.abc` / `.fbx` 에 **거짓말을 한다**

초안은 "포맷마다 다시 읽어 검증한다"였다. 실제 문제는 더 앞에 있었다.

```python
box.geometry().saveToFile("box.usd")   # 예외 없음. 349 바이트 파일이 생긴다.
```

```
$ head -1 box.usd
PGEOMETRY V5
```

`.usd`, `.usda`, `.usdc`, `.abc`, `.fbx`, `.gltf`, `.glb` 를 전부 같은 349 바이트
**ASCII `.geo`** 로 쓴다. 확장자만 바뀐 가짜 파일이다. 더 나쁜 것은
`loadFromFile` 이 내용을 스니핑해서 그 파일을 멀쩡히 읽는다는 점이다 — **Houdini
왕복 검사로는 이 거짓말이 안 잡힌다.** `pxr.Usd.Stage.Open()` 으로 열어야
`Failed to open layer` 가 나온다.

그래서 `write_geometry` 는 그 확장자들을 **거부하고** 전용 툴로 보낸다.
`saveToFile` 이 실제로 그 포맷을 쓰는 확장자만 받는다:
`.bgeo.sc` `.bgeo` `.geo` `.obj` `.ply` `.stl` `.vdb`.

> `houdini_mcp_sop` 의 `export_geometry` 는 `.abc` / `.usd` / `.fbx` 를 허용
> 목록에 넣고 있다. 그쪽을 고치는 것은 sop 팩 담당의 몫이다.

### 2. `usd_rop.render()` 는 **아무 파일도 쓰지 않는다**

에러도, 경고도, `node.errors()` 도 비어 있는데 파일이 생기지 않는다
(`render()`, `parm("execute").pressButton()` 둘 다). Apprentice 라이선스에서
확인했다.

대신 LOP 스테이지를 `pxr` 로 직접 받아 쓴다. README 제1원칙("그 도메인의
파이썬 라이브러리를 먼저 찾는다")이 그대로 맞는 경우다.

```python
stage = lop_node.stage()          # -> pxr.Usd.Stage
stage.Export(path)                # 평탄화해서 자립 파일로
stage.GetRootLayer().Export(path) # 루트 레이어만
```

SOP 을 USD 로 내보낼 때는 `/stage` 에 임시 `sopimport` LOP 을 만들어 통과시킨 뒤
지운다. (초안이 물었던 "USD ROP 이름"은 LOP 카테고리의 `usd_rop` 이고,
SOP 카테고리의 `usdexport` 는 ROP 이 아니라 USD 프림 설정 SOP 이다.)

`Usd.Stage.Export()` 는 **스테이지 메타데이터를 저자하지 않는다.** 그냥 두면
`usdchecker` 가 `MissingUpAxisMetadata` / `MissingDefaultPrim` 을 낸다.
`usd_rop` 의 `ensuremetricsset` / `defaultprim` 이 하던 일이므로, 쓴 뒤에 직접
채워 넣는다.

### 3. Apprentice 는 Alembic·FBX 내보내기가 **막혀 있다**

```
Alembic export is only supported in Houdini Core and Houdini FX versions.
FBX export is not supported in Houdini Apprentice.
```

노드를 만들어 놓고 실패하지 않도록 `hou.licenseCategory()` 로 먼저 거른다.
`export_formats` 가 이 설치에서 무엇이 되는지 한 번에 알려 준다.

### 4. `$HFS/bin` 에 있는 것 (전부 확인)

`abcinfo` `abcecho` `abcconvert` `abcstitcher` `gabc` — Alembic 파이썬 바인딩이
없는 자리를 메운다. `abcinfo -o -b` 가 오브젝트 계층과 타입(PolyMesh / Xform /
Camera)을 준다. Houdini 로 `.abc` 를 다시 읽으면 **packed 프림 하나**로 보여서
대조가 되지 않으므로, 이 CLI 가 유일한 실질 검증 경로다.

`usdchecker` `usdcat` `usdtree` `usdzip` `usddiff` — USD 쪽. 검증에는 `pxr` 를
직접 쓰고, `usdchecker` 는 옵션으로 돌린다.

### 5. `hou.fileReferences()` 의 실제 모양

```
fileReferences(project_dir_variable='HIP', include_all_refs=True)
    -> tuple of (hou.Parm, str)
```

- 두 번째 항목은 **미전개** 문자열이다(`parm.unexpandedString()` 과 같다).
- 전개된 경로는 `parm.eval()` 이다.
- `$F4` 는 **현재 프레임으로** 전개되고, `<UDIM>` 은 **전개되지 않는다.**
  그래서 "실제로 몇 장 있나"는 토큰을 `*` 로 바꿔 글롭해야 한다.
- **Houdini 설치($HFS) 안의 파일은 목록에서 통째로 빠진다.** `$HFS/...` 로 쓰든
  절대 경로로 쓰든 마찬가지다. 설치본 샘플을 참조하면 의존성에 안 나온다.
- ROP 의 출력 경로(`sopoutput`, `picture`, `lopoutput` ...)도 함께 들어온다.
  아직 렌더하지 않은 출력을 "없는 파일"로 보고하면 거짓 경보라 `role` 로 가른다.

### 6. 없는 것

`hou.hipFile.collisionFreeName` 은 **없다**(초안이 물었던 것). 대신
`collisionNodesIfMerged` 가 있다. `hou.hipFile.importFBX` 는 있지만 **현재 씬에
노드를 쏟아붓는다** — 검증에 쓸 수 없다.

---

## 우리가 쓰는 경로

| 포맷 | 쓰는 길 | 검증하는 길 |
|---|---|---|
| bgeo/geo/obj/ply/stl/vdb | `hou.Geometry.saveToFile` | `loadFromFile` 재독 후 점·프림·어트리뷰트 대조 |
| USD | `pxr.Usd.Stage.Export` | `Usd.Stage.Open` — 프림 종류별 개수, PointBased 포인트 합계, up axis, default prim. 옵션으로 `usdchecker` |
| Alembic | `rop_alembic` ROP | `$HFS/bin/abcinfo -o -b` |
| FBX | `filmboxfbx` ROP | 파일 시그니처와 크기까지만 (아래 참고) |

손실 포맷(`.obj` `.ply` `.stl` `.vdb`)은 왕복하면 수가 달라지는 것이 정상이므로
`lossy` 로 표시하고 델타를 참고로만 보여 준다. 다만 **어느 포맷이든 빈 파일은
통과가 아니다** — 원본이 비어 있어서 그랬더라도 알려 준다.

FBX 검증이 얕은 것은 의도적이다. FBX SDK 파이썬 바인딩이 번들에 없고, Houdini 로
다시 읽는 유일한 길(`hou.hipFile.importFBX`)이 현재 씬을 더럽힌다. 검증하려고
사용자 씬을 망가뜨리지 않는다.

## 툴

12개. 모듈 하나가 800줄을 넘지 않는다.

| 모듈 | 툴 |
|---|---|
| `export` | `write_geometry`, `export_usd`, `export_alembic`, `export_fbx`, `export_formats` |
| `load` | `probe_file`, `import_geometry`, `import_scene` |
| `deps` | `list_dependencies`, `collect_dependencies`, `remap_paths` |
| `check` | `validate_scene` |

초안과 달라진 이름과 그 이유:

- `export_geometry` → **`write_geometry`**. `houdini_mcp_sop` 이 이미
  `export_geometry` 를 쓰고 있다. 이름이 겹치면 레지스트리가 거절한다.
  `write_cache`(base)와 같은 결의 이름이기도 하다.
- `missing_files` → **없앴다.** `list_dependencies(missing_only=True)` 와 완전히
  같은 일이다. 같은 일을 하는 툴을 둘 두면 모델이 어느 쪽을 부를지 고민한다.
- `import_usd` → **없앴다.** `import_geometry` 가 확장자를 보고 리더를 고른다
  (`.abc` → Alembic SOP, `.usd` → USD Import SOP, 나머지 → File SOP).
  LOP 스테이지로 들이는 것은 `houdini_mcp_lop` 의 일이다.
- **`export_formats` 를 더했다.** 라이선스와 `$HFS/bin` 실측을 합쳐, 이 설치에서
  무엇이 되는지 먼저 알려 준다. Apprentice 에서 Alembic ROP 을 돌려 보고서야
  막힌 것을 아는 왕복을 없앤다.
- **`import_scene` 을 더했다.** `load_scene`(base)은 현재 씬을 버리고 연다.
  에셋을 모아 조립하려면 합치는 길이 따로 필요하다.

`save_export_preset` 계열은 만들지 않는다. 프리셋 파일 포맷을 자체로 만드는
것은 README 제1원칙에 어긋난다. 필요하면 ROP 프리셋(Houdini 기본)을 쓴다.

## 다른 팩과의 경계

- **이미지 텍스처의 내용**(해상도·채널·비트뎁스·컬러스페이스·용도 판정)은
  `houdini_mcp_mat` 의 `texture_info` / `list_textures` 다. 여기서는 이미지도
  **파일 의존성으로는** 다룬다 — 씬을 통째로 옮기려면 텍스처도 모아야 하기
  때문이다. `probe_file` 은 이미지를 만나면 종류만 알려 주고 그쪽으로 보낸다.
- **캐시 노드**(filecache 를 만들고 굽고 상태를 보는 것)는 `houdini_mcp_base` 의
  `write_cache` / `cache_status` 다. 여기는 노드를 남기지 않는 일회성 쓰기다.
- **씬 파일 열기·저장**은 base 의 `save_scene` / `load_scene` 이다. 여기는
  합치기(`import_scene`)만 한다.
- **LOP 스테이지 질의·편집**은 `houdini_mcp_lop` 이다. 여기는 스테이지를 파일로
  내보내는 것까지다.

## 검증

`io.md` 의 시나리오를 그대로 돌렸고, 12개 툴을 전부 실제로 호출했다.

```
box → write_geometry(.bgeo.sc) → 다시 읽어 8점 6프림 확인 ✓
→ 같은 경로에 다시 → overwrite 요구 ✓
→ .usd 로 → 거부하고 export_usd 로 안내 ✓
→ $F4 로 5프레임 → 5개 파일 전부 재독 검증 ✓
→ 포인트만 있는 지오메트리를 .stl 로 → verified=false, empty=true ✓ (일부러 깨뜨림)
→ export_usd → pxr 재독, upAxis/defaultPrim 저자, usdchecker ✓
→ 빈 SOP 을 export_usd → verified=false, empty=true ✓ (일부러 깨뜨림)
→ export_alembic / export_fbx → Apprentice 거절 메시지 ✓
→ 텍스처·없는 캐시 참조 → list_dependencies 가 종류별로 집계 ✓
→ validate_scene → missing / empty_sequence / absolute_path / outside_hip ✓
→ collect_dependencies(dry_run) → 계획 → dry_run=False + relink → 파일 이동·재연결 ✓
→ remap_paths → $HIP 상대로 되돌리기 ✓
```
