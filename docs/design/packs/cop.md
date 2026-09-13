# houdini_mcp_cop — COP(Copernicus) 전문

> 먼저 [README.md](README.md) 를 읽는다.
>
> 미리보기(`preview` 모듈)는 구현됐고 나머지는 **설계**다. API 서술은 Houdini 22.0.368 을
> hython 으로 실측한 것이다(2026-09-13). 지금 등록된 툴 목록은 팩 README
> ([houdini_mcp_cop/README.md](../../../houdini_mcp_cop/README.md))를 본다.

## 무엇을 담나

Copernicus(`copnet`) 이미지 네트워크를 **짓고, 결과를 보고, 수치로 확인하고, 파일로 내보내는**
것. 옛 COP2(`cop2net`)는 다루지 않는다.

노드를 만들고 잇고 파라미터를 거는 일은 `houdini_mcp_base` 의 `create_node` /
`connect_nodes` / `set_parms` 로 이미 된다. 이 팩이 따로 있어야 하는 이유는 **COP 의 결과가
노드 그래프가 아니라 이미지**이고, 그 이미지를 모델이 볼 방법이 base 에는 없기 때문이다.

## 계기 — 성 파괴 씬에서 막힌 것

성 씬(2026-09-13)의 석재·지면 텍스처를 COP 으로 만들면서 막힌 순서다. 설계는 이 목록을
하나씩 지우는 방향으로 한다.

| 막힌 것 | 무슨 일이 있었나 | 지금 |
|---|---|---|
| 결과를 볼 수 없다 | 파일로 내보내 외부 도구로 PNG 를 만들어 봤다. 단일 채널 맵은 검게 나와 확인하지 못한 채 재질에 붙였고, 품질 문제가 렌더에서야 드러났다 | `preview` 모듈로 해결 |
| 채널 의미를 모른다 | Mono 높이맵과 ID 맵, 벡터 맵이 같은 방식으로 표시돼 읽을 수 없었다 | `preview` 가 레이어 타입별로 표시 방식을 고른다 |
| 네트워크 구조가 안 보인다 | 어느 출력이 Mono 이고 어느 입력이 RGB 를 받는지 몰라 잘못 이었다가 쿡 에러로 알았다 | 없음 |
| 내보내기가 번거롭다 | `rop_image` 의 해상도·색 변환·출력 이름을 하나씩 걸었고, 저장 안 한 씬의 백그라운드 실행이 모달 대화상자로 막혔다 | 없음 |
| 파일 COP 이 비어 있다 | `file` COP 은 경로가 맞기 전까지 출력 커넥터가 하나도 없어 연결할 곳이 없었다 | 없음 |
| 이음매를 모른다 | 타일링 텍스처의 좌우·상하 경계가 맞는지 렌더 전에는 알 수 없었다 | 없음 |
| 전후 비교 | 노이즈 파라미터를 바꾼 효과를 숫자로 비교할 수 없었다 | 없음 |

## 기존 구현이 한 방식과 그 한계

| 구현 | COP 툴 | 한계 |
|---|---|---|
| fxhoudinimcp `tools/cops.py` | `get_cop_info`, `get_cop_geometry`, `get_cop_layer`, `create_cop_node`, `set_cop_flags`, `list_cop_node_types`, `get_cop_vdb` | 노드 생성·플래그·타입 목록은 범용 툴과 겹친다. 레이어는 "데이터 가져오기" 수준이라 모델이 이미지로 볼 수 없다 |
| dcc-mcp-houdini `houdini-copernicus` | `create_cop_network`, `create_cop_node`, `inspect_cop_network`, `validate_cop_network` | `inspect`/`validate` 가 **쿡하지 않고** 캐시된 에러만 읽는다. 연결의 데이터 타입, 해상도, 결과 이미지는 보지 않는다 |

둘 다 **결과 이미지를 보지 않는다.** COP 은 이미지가 결과인데, 그것을 확인하는 경로가 없다.
제2원칙(툴은 결과를 돌려준다)이 가장 크게 어긋나는 도메인이다.

## 우리가 쓰는 경로

### 레이어는 `hou.ImageLayer` 로 직접 읽는다

`CopNode.layer(output_index)` / `layerAtFrame(frame, output_index)` 는 **필요하면 쿡까지
해서** `hou.ImageLayer` 를 준다. 파일로 내보내지 않고 메모리에서 바로 읽는다.

| 필요한 것 | API | 비고 |
|---|---|---|
| 해상도 | `bufferResolution()` | `(가로, 세로)` |
| 영역 | `dataWindow()`, `displayWindow()` | `hou.BoundingRect`. 데이터 창이 표시 창보다 작거나 클 수 있다 |
| 채널·정밀도 | `channelCount()`, `storageType()` | `imageLayerStorageType.Float32` 등 |
| 의미 타입 | `typeInfo()` | `hou.imageLayerTypeInfo` 값. `constant` 는 `Raw`. 표시 방식을 여기서 고른다(나머지 값 목록은 구현 때 enum 에서 읽는다) |
| 픽셀 전체 | `allBufferElements()` | 바이트. `numpy.frombuffer` 로 `(y, x, c)` |
| 픽셀 하나 | `bufferIndex(x, y)` | 레이어 타입에 맞춰 float 또는 tuple |
| 통계 | `computeAverage(channel)`, `computeMin`, `computeMax` | C++ 쪽 계산. 전체 버퍼를 넘기지 않아도 된다 |
| 좌표 변환 | `textureToBuffer`, `pixelToBuffer`, `worldToBuffer` 등 | 샘플 좌표를 사용자가 쓰는 공간으로 받는다 |

**버퍼의 y=0 은 이미지 아래쪽이다.** 그림으로 만들 때 뒤집어야 한다.

### 출력의 데이터 타입은 노드가 알려 준다

`outputNames()`, `outputDataTypes()`, `inputNames()`, `inputDataTypes()` 가 커넥터마다 타입을
준다. 실측 예:

| 노드 | 입력 | 출력 |
|---|---|---|
| `constant` | - | `constant`: `Mono` |
| `geotolayer` | `geometry`, `size_ref`, `vdb_ref`: `Geometry`, `Metadata`, `MetadataVDB` | `layer`: `Mono` |
| `sopimport` | - | `geometry`: `Geometry` |
| `blocktogeo` | - | `program`: `Geometry` |
| `file` | `size_ref`: `Metadata` | **없음** (쿡 후에도, 파일이 없으면) |

그래서 연결 검증은 쿡하지 않고도 **타입 대조**로 먼저 할 수 있다. 레이어가 아닌 출력은
`geometryAtFrame` / `vdbAtFrame`(NanoVDB)으로 읽는다.

### 내보내기는 `rop_image` 로 한다

`rop_image` 의 실측 파라미터: `coppath`, `copoutput`, `trange`/`f1`/`f2`/`f3`,
`setres`/`res1`/`res2`, `setprecision`/`precision`, `colorconversion`,
`ociocolorspace`, `mkpath`, `execute`, `executebackground`, `savebackground`.

- 백그라운드 실행(`executebackground`)은 **씬이 저장돼 있어야** 한다. 저장 안 된 씬이면
  모달 대화상자가 메인 스레드를 막는다. 툴이 먼저 확인하고, 저장이 필요하다고 알려 준다.
- `f1`/`f2` 에는 기본으로 `$FSTART`/`$FEND` 식이 걸려 있다. 값을 걸기 전에 식을 지운다.
- 데이터 맵(높이·거칠기·노멀)은 색 변환을 끄고(`Raw`) 쓴다. 컬러 맵만 sRGB 로 변환한다.
- **라이선스 워터마크를 우회하지 않는다.** Apprentice/Education 에서는 `rop_image` 결과에
  워터마크가 들어간다. 레이어 버퍼를 OpenImageIO 로 직접 파일에 쓰면 워터마크를 피할 수
  있지만, 그것은 라이선스 제한을 우회하는 일이라 하지 않는다. 버퍼를 직접 읽는 것은
  미리보기와 수치 확인(툴 응답)에만 쓰고, 디스크로 나가는 파일은 전부 `rop_image` 를 거친다.

### 코드 노드

Copernicus 의 `wrangle` 은 VEX 로 픽셀을 다룬다(Volume Wrangle 에 대응). `opencl` 은 OpenCL
커널을 돌린다. VEX 컴파일 검증은 `houdini_mcp_vex` 가 맡으므로 이 팩은 wrangle 을 따로 검증하지
않는다. 다만 COP wrangle 의 바인딩(레이어 이름 ↔ `@` 변수)이 SOP wrangle 과 같은 규칙으로
`vcc` 검증을 통과하는지는 **미확인**이다. 구현할 때 실측한다.

## 모듈과 툴 설계

씬을 바꾸는 툴은 `@undoable`, 노드를 만드는 툴은 `comment` 필수(저장소 규칙).

### `preview` — 구현됨

결과를 그림과 수치로 본다. `path:output` 표기로 출력을 고른다. 세부는 팩 README.

### `network` — 구조와 연결

| 툴 | 하는 일 | 돌려주는 것 |
|---|---|---|
| `cop_network_info(path, frame)` | copnet 한 개를 훑는다 | 노드마다 타입·코멘트·입출력 커넥터 이름과 데이터 타입·연결·레이어 해상도·에러/경고 |
| `validate_cop_network(path, cook)` | 연결을 검사한다 | 데이터 타입 불일치(Mono 출력 → RGB 입력 등), 필수 입력 누락, 입력끼리 해상도 불일치, 표시 노드 없음, 쿡 에러. 지적마다 고치는 법 |
| `cop_type_ports(type_name)` | 만들기 전에 커넥터를 본다 | 임시 copnet 에 노드를 만들어 입출력 이름·데이터 타입을 읽고 지운다. base `node_type_info` 는 파라미터 중심이라 COP 커넥터 타입을 주지 않는다 |

dcc 의 `validate_cop_network` 와 달리 **타입을 대조**하고, 필요하면 쿡해서 실제 에러까지 본다.

### `sample` — 수치로 확인

| 툴 | 하는 일 | 돌려주는 것 |
|---|---|---|
| `cop_sample_pixels(node, points, space, frame)` | 지정 좌표의 값을 읽는다 | `space` = `texture`(0~1) / `pixel` / `world`. 좌표마다 채널 값 |
| `cop_histogram(node, channel, bins, frame)` | 값 분포 | 구간별 개수, 0/1 에 몰린 비율(클리핑), NaN 수 |
| `cop_compare(a, b, frame)` | 두 레이어(또는 한 노드의 두 프레임)를 비교 | 채널별 평균·최대 차이, 차이가 큰 영역의 경계, 차이 그림 한 장 |
| `cop_tile_check(node, frame)` | 타일링 이음매 | 좌·우 / 상·하 경계 열의 평균 차이를 내부 이웃 열 차이와 비교한 비율, 2×2 로 반복한 그림 |

통계는 가능한 한 `computeAverage/Min/Max` 로 C++ 에서 받고, 히스토그램·비교처럼 전체 버퍼가
필요한 것만 numpy 로 한다(제3원칙). 응답에는 요약만 싣는다.

### `io` — 들이기와 내보내기

| 툴 | 하는 일 | 돌려주는 것 |
|---|---|---|
| `cop_import_image(parent, file, comment, name, frame)` | `file` COP 을 만들고 경로를 걸어 쿡한다 | 생긴 출력 커넥터와 레이어(해상도·채널·타입). 파일이 없거나 읽지 못하면 출력이 비어 있다고 알려 준다 |
| `export_cop_layers(node, outputs, file_path, comment, resolution, color, frame_range, background)` | `rop_image` 를 만들거나 재사용해 내보낸다 | 쓴 파일 목록, 파일마다 해상도·채널·통계(OpenImageIO 로 다시 읽음). `background=True` 인데 씬이 저장 안 됐으면 실행하지 않고 알린다 |

`export_cop_layers` 의 `color` 는 `raw` / `srgb` / OCIO 이름. 출력 이름으로 데이터 맵인지 컬러
맵인지 추정해 기본값을 고르되, 추정했다는 사실을 응답에 적는다.

### 경계

| 무엇 | 어디 |
|---|---|
| 노드 생성·연결·파라미터 | `houdini_mcp_base` (`create_node` 등) |
| VEX 컴파일 검증 | `houdini_mcp_vex` |
| 렌더 결과 이미지(디스크의 EXR 등) | `houdini_mcp_render` (`image_info`, `compare_images`) |
| 텍스처 파일을 재질에 붙이기 | `houdini_mcp_mat` (`assign_texture`) |
| COP 네트워크 안의 이미지 | **이 팩** |

render 팩의 이미지 툴은 **디스크 파일**을, 이 팩은 **쿡된 레이어**를 본다. 같은 비교 로직이 두
곳에 생기면 base 로 올린다.

## 구현 순서

1. `network` — `cop_network_info`, `validate_cop_network`, `cop_type_ports`. 연결 실수를 먼저 막는다.
2. `io` — `export_cop_layers`, `cop_import_image`. 성 씬에서 가장 시간을 잡아먹은 곳이다.
3. `sample` — `cop_sample_pixels`, `cop_histogram`, `cop_tile_check`, `cop_compare`.

각 단계는 GUI Houdini 에 핫 리로드해 MCP 로 불러 확인한다. 내보내기는 Apprentice 에서
워터마크가 들어간 파일이 정상 결과다.

## 실측 기록 (Houdini 22.0.368)

| 확인한 것 | 결과 |
|---|---|
| `CopNode.layer()` 가 쿡하는가 | 한다. 쿡되지 않았으면 쿡해서 준다 |
| `constant` 기본 레이어 | 1024×1024, `Float32`, `typeInfo=Raw`, `dataWindow=[0,0,1024,1024]`, 평균 1.0 |
| 경로 없는 `file` COP 의 출력 | 쿡 후에도 `outputNames()` 가 빈 튜플 |
| 버퍼 y 방향 | y=0 이 이미지 아래 |
| 노이즈 계열 노드 이름 | `fractalnoise`, `worleynoise`, `cellularnoise`, `curlnoise`, `phasornoise` 등. `noise` 라는 타입은 없다 |
| 레이어 쓰기 | `ImageLayer.setAllBufferElements(values, length)` 가 있다. 이 팩은 쓰지 않는다(위 워터마크 절) |
| 이미지 저장 함수 | `hou.saveImageDataToFile` 가 있다. 같은 이유로 COP 결과 내보내기에 쓰지 않는다 |
| OpenImageIO 기본 글꼴 | 한글 글리프가 없다. 미리보기 라벨은 ASCII 로 쓴다 |
