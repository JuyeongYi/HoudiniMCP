# Houdini MCP

English: [README.en.md](README.en.md)

SideFX Houdini **안에서** 도는 [MCP](https://modelcontextprotocol.io) 서버와, 거기에 툴을 공급하는
도메인별 툴 팩 모음이다. Claude Code 같은 MCP 클라이언트가 실행 중인 Houdini 세션에 붙어 씬을
조회하고, 노드를 만들고, 시뮬레이션·렌더·텍스처를 다루고, 결과를 그림으로 확인한다.

- **Houdini 프로세스 안의 서버** — streamable-http `http://127.0.0.1:22926/mcp`. 따로 띄울 서버가 없다.
- **도메인별 툴 팩** — SOP, DOP, LOP, 머티리얼, 렌더, HDA, 리깅, CHOP, VEX, COP 등.
  필요한 팩만 설치할 수 있다.
- **메인 스레드 안전** — `hou` 를 만지는 툴은 자동으로 Houdini 메인 스레드에서 실행된다.
- **Undo 한 번** — 씬을 바꾸는 툴 호출 하나가 Undo 하나로 묶인다.
- **고칠 수 있는 오류** — 툴의 오류 메시지가 그대로 모델에 전달되고, 다음에 무엇을 할지 알려 준다.
- **눈으로 확인** — 뷰포트 캡처, 프레임 시퀀스, COP 이미지 미리보기를 이미지로 돌려준다.

## 요구사항

| 항목 | 버전 |
|---|---|
| Houdini | 22.0 이상 (GUI 세션) |
| Python | Houdini 에 들어 있는 3.13 |
| MCP Python SDK | `mcp>=2.2,<3` (Houdini 의 파이썬에 설치) |
| ffmpeg (선택) | 영상 툴에만 필요. ffmpeg·ffprobe 가 든 bin 디렉토리를 `FFMPEG_BIN_PATH` 로 지정한다. drawtext·libx264 가 든 빌드를 권한다 |

개발과 검증은 Houdini 22.0.368 / Windows 11 에서 했다. 코드는 Windows·Linux·macOS 를 모두
지원하도록 쓴다.

## 설치

1. 저장소를 받는다.

   ```bash
   git clone <this repository> HoudiniMCP
   ```

2. MCP SDK 를 **Houdini 의 파이썬**에 설치한다(시스템 파이썬이 아니다).

   ```bash
   # Windows
   "%HFS%\bin\hython.exe" -m pip install -r requirements.txt
   # Linux / macOS
   "$HFS/bin/hython" -m pip install -r requirements.txt
   ```

3. 저장소의 `packages/` 를 Houdini 패키지 디렉토리에 **더한다**. 기존 값을 덮어쓰면 다른
   플러그인 패키지가 빠지므로 앞에 붙인다. 팩 JSON 은 자기 위치(`$HOUDINI_PACKAGE_PATH`)에서
   한 단계 위의 팩 디렉토리를 찾으므로, JSON 파일만 다른 곳으로 복사하지 않는다.

   ```bash
   # Windows (PowerShell) — 개발용 실행 스크립트가 이 설정을 대신한다
   .\scripts\run-houdini.ps1
   # Linux / macOS
   HOUDINI_PACKAGE_DIR="/path/to/HoudiniMCP/packages${HOUDINI_PACKAGE_DIR:+:$HOUDINI_PACKAGE_DIR}" houdini
   ```

   필요 없는 팩은 `packages/` 에서 해당 `houdini_mcp_<도메인>.json` 을 지운다.
   `houdini_mcp.json`(서버)은 반드시 있어야 한다.

4. Houdini UI 가 뜨면 서버가 시작된다. 로그는 `$HOUDINI_USER_PREF_DIR/log/houdini_mcp.jsonl`.

## MCP 클라이언트 연결

Claude Code:

```bash
claude mcp add --transport http houdini http://127.0.0.1:22926/mcp
```

또는 프로젝트의 `.mcp.json`:

```json
{
  "mcpServers": {
    "houdini": { "type": "http", "url": "http://127.0.0.1:22926/mcp" }
  }
}
```

Houdini 를 두 개 띄울 때는 두 번째에 다른 포트를 준다(`HOUDINI_MCP_PORT`,
`scripts/run-houdini.ps1 -Port 22927`). 같은 포트면 먼저 뜬 쪽만 서버를 연다.

## 툴 팩

| 팩 | 담는 것 | 툴 목록 |
|---|---|---|
| `houdini_mcp` | 서버와 레지스트리 (툴 없음) | [architecture.md](docs/architecture.md) |
| `houdini_mcp_base` | 컨텍스트를 가리지 않는 조회·편집·파라미터·지오메트리·뷰포트·캐시·씬 | [README](houdini_mcp_base/README.md) |
| `houdini_mcp_sop` | SOP 모델링·어트리뷰트·그룹·UV | [README](houdini_mcp_sop/README.md) |
| `houdini_mcp_lop` | USD 스테이지·레이어·컴포지션·라이트 | [README](houdini_mcp_lop/README.md) |
| `houdini_mcp_mat` | 머티리얼 생성·할당·텍스처·색공간 | [README](houdini_mcp_mat/README.md) |
| `houdini_mcp_hda` | HDA 생성·인터페이스·섹션·버전 관리 | [README](houdini_mcp_hda/README.md) |
| `houdini_mcp_rig` | KineFX 스켈레톤·스킨·APEX 그래프 | [README](houdini_mcp_rig/README.md) |
| `houdini_mcp_dop` | DOP 네트워크 구성·실행·캐시·검사 | [README](houdini_mcp_dop/README.md) |
| `houdini_mcp_dop_rbd` | RBD 조각·시뮬 진단 | [README](houdini_mcp_dop_rbd/README.md) |
| `houdini_mcp_chop` | CHOP 채널·필터·오디오·베이크 | [README](houdini_mcp_chop/README.md) |
| `houdini_mcp_render` | 렌더 설정·검사·실행·결과 이미지 | [README](houdini_mcp_render/README.md) |
| `houdini_mcp_io` | 내보내기(USD·Alembic·FBX)·가져오기 | [README](houdini_mcp_io/README.md) |
| `houdini_mcp_vex` | VEXpression 컴파일 검증·wrangle | [README](houdini_mcp_vex/README.md) |
| `houdini_mcp_cop` | COP(Copernicus) 이미지 확인 | [README](houdini_mcp_cop/README.md) |
| `houdini_mcp_example` | 새 팩을 만드는 최소 예시 | [README](houdini_mcp_example/README.md) |

각 팩 README 는 `scripts/gen_pack_readmes.py` 가 코드에서 만든다. 툴 이름·설명·인자는
거기서 본다.

## 문서

| 문서 | 내용 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 서버와 툴 팩 분리 구조, 기동·호출 흐름, 실패 모델 |
| [docs/design/decisions.md](docs/design/decisions.md) | 설계 결정과 실측 근거 |
| [docs/design/packs/README.md](docs/design/packs/README.md) | 팩별 설계 원칙과 인덱스 |
| `CLAUDE.md` | 코드와 툴 작성 규칙 |

## 개발

| 할 일 | 명령 |
|---|---|
| 개발용 Houdini 실행 | `.\scripts\run-houdini.ps1` (`-Port`, `-IsolatePrefs`, `-NoTools`, `-ConsoleLog`) |
| 테스트 (hython 서브프로세스) | `python -m pytest tests -q` |
| 린트 | `ruff check .` |
| 팩 README 생성 | `python scripts/gen_pack_readmes.py` |
| 팩 README·번역이 최신인지 | `python scripts/gen_pack_readmes.py --check` |

새 툴 팩은 `houdini_mcp_example` 을 복사해 시작한다. 절차는
[docs/architecture.md](docs/architecture.md#새-팩-만들기) 에 있다.

뷰포트·렌더처럼 UI 가 필요한 툴은 hython 에서 검증할 수 없다. 툴을 고친 뒤에는 GUI Houdini 에
핫 리로드해 MCP 로 불러 확인한다.
