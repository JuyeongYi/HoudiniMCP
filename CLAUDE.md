# HoudiniMCP 소스 작성 규칙

## 멀티플랫폼

이 프로젝트는 **Windows / Linux / macOS 를 모두 지원한다.** 개발은 Windows 에서
하지만, 플랫폼에 묶인 코드를 쓰지 않는다.

### 경로와 구분자는 하드코딩하지 않는다

경로 문자열을 손으로 조립하지 말고 표준 라이브러리에서 얻어온다.

| 필요한 것 | 쓸 것 | 쓰지 말 것 |
|---|---|---|
| 경로 결합·조작 | `pathlib.Path` | `"a" + "\\" + "b"`, `"a/b"` 문자열 |
| 경로 구분자 | `os.sep` | `"\\"`, `"/"` |
| PATH 류 목록 구분자 | `os.pathsep` | `";"`, `":"` |
| 줄바꿈 | `os.linesep` (파일 출력 시) | `"\r\n"` |
| 임시 디렉토리 | `tempfile` | `"C:\\Temp"`, `"/tmp"` |
| 사용자 홈 | `Path.home()` | `"C:\\Users\\..."` |

`HOUDINI_PATH` 나 `HOUDINI_PACKAGE_DIR` 처럼 여러 경로를 담는 환경변수를 가를
때는 반드시 `os.pathsep` 을 쓴다. Windows 는 `;`, 나머지는 `:` 다.

```python
# 나쁘다
for entry in hou.text.expandString("$HOUDINI_PATH").split(";"):

# 좋다
for entry in hou.text.expandString("$HOUDINI_PATH").split(os.pathsep):
```

경로의 마지막 요소를 꺼낼 때도 문자열을 자르지 않는다.

```python
name = path.split("/")[-1]   # 나쁘다
name = Path(path).name       # 좋다
```

### 플랫폼 분기는 명시적으로

분기가 정말 필요하면 `sys.platform` 으로 드러내고 이유를 주석으로 남긴다.
암묵적으로 한 플랫폼을 가정하지 않는다.

```python
if sys.platform == "win32":
    return asyncio.ProactorEventLoop()
return asyncio.SelectorEventLoop()
```

### 예외: Houdini 패키지 JSON

Houdini 패키지 JSON(`*.json`) 의 `hpath` / `env` 값은 **모든 플랫폼에서 슬래시**를
쓴다. Houdini 자체 규약이므로 여기서만 `str(path).replace(os.sep, "/")` 로 바꿔
넣고, 그 이유를 주석에 남긴다.

### Houdini 파이썬 버전

`python3.13libs` 디렉토리 이름은 Houdini 가 쓰는 파이썬 버전에 묶인다.
코드에서 이 이름이 필요하면 설치본에서 유도한다(`tests/package_order/harness.py`
의 `python_tag()` 참고). 하드코딩하면 Houdini 가 파이썬을 올릴 때 조용히 깨진다.

---

## 그 밖의 규칙

전역 규칙(파일 크기 경계, 코드 스멜 감지, 주기적 리팩토링)은 사용자 전역
`CLAUDE.md` 를 따른다.

설계 결정과 그 근거는 `docs/design/decisions.md` 에 있다. 구조를 바꾸기 전에
먼저 읽는다 — 대부분 실측으로 확인한 Houdini 동작에 기대고 있고,
`tests/package_order/` 의 회귀 테스트가 그것을 고정하고 있다.
