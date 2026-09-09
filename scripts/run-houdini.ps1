<#
.SYNOPSIS
    Houdini MCP 개발용 Houdini 실행 스크립트.

.DESCRIPTION
    이 repo 를 Houdini 패키지 디렉토리로 지정한 뒤 Houdini 를 띄운다.
    영구 환경변수에 의존하지 않으므로, 설정을 바꿔가며 시험하거나 MCP 패키지를
    끈 상태로 Houdini 를 쓰고 싶을 때 편하다.

.PARAMETER Port
    MCP 서버 포트. 기본 22926 (= int("HOU", 36)).
    Houdini 를 두 개 이상 띄울 때는 두 번째부터 다른 값을 줘야 한다. 같은 포트면
    나중에 뜬 인스턴스는 서버를 띄우지 않고 경고만 남긴다(first-wins).

.PARAMETER HfsPath
    Houdini 설치 경로. 생략하면 설치된 것 중 최신 버전을 찾는다.

.PARAMETER IsolatePrefs
    사용자 설정을 건드리지 않도록 임시 preference 디렉토리를 쓴다.
    깨끗한 상태에서 재현할 때 유용하다.

.PARAMETER NoTools
    데모 툴 팩 없이 서버 패키지만 로드한다.

.PARAMETER LogDir
    로그 디렉토리. 기본은 $HOUDINI_USER_PREF_DIR/log.
    로그는 houdini_mcp.jsonl 하나에 JSONL 로 쌓인다.
    "off" 를 주면 파일 로깅을 끈다.

.PARAMETER ConsoleLog
    로그를 Houdini 콘솔에도 낸다. 기본은 파일에만 쌓는다 - 켜면 툴을 부를 때마다
    콘솔 창이 떠서 작업을 방해한다.

.PARAMETER Wait
    Houdini 가 종료될 때까지 기다린다.

.PARAMETER DryRun
    실행하지 않고 설정될 환경만 보여준다.

.EXAMPLE
    .\scripts\run-houdini.ps1

.EXAMPLE
    .\scripts\run-houdini.ps1 -Port 22927 -IsolatePrefs
#>
[CmdletBinding()]
param(
    [int]$Port = 22926,
    [string]$HfsPath,
    [switch]$IsolatePrefs,
    [switch]$NoTools,
    [string]$LogDir,
    [switch]$ConsoleLog,
    [switch]$Wait,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Find-Hfs {
    if ($env:HFS -and (Test-Path (Join-Path $env:HFS "bin\houdini.exe"))) {
        return $env:HFS
    }

    # 경로를 하드코딩하지 않는다. ProgramFiles 위치는 시스템마다 다를 수 있다.
    $root = Join-Path $env:ProgramFiles "Side Effects Software"
    if (-not (Test-Path $root)) {
        throw "Houdini 설치 폴더를 찾지 못했습니다: $root. -HfsPath 로 직접 지정하세요."
    }

    $found = Get-ChildItem -Path $root -Directory -Filter "Houdini *" |
        Where-Object { Test-Path (Join-Path $_.FullName "bin\houdini.exe") } |
        Sort-Object {
            # "Houdini 22.0.368" -> 22.0.368 로 정렬한다.
            if ($_.Name -match '(\d+(\.\d+)+)') { [version]$Matches[1] } else { [version]"0.0" }
        }

    if (-not $found) {
        throw "houdini.exe 를 가진 설치를 찾지 못했습니다. -HfsPath 로 직접 지정하세요."
    }
    return $found[-1].FullName
}

if ($HfsPath) {
    if (-not (Test-Path (Join-Path $HfsPath "bin\houdini.exe"))) {
        throw "houdini.exe 가 없습니다: $HfsPath\bin"
    }
    $hfs = $HfsPath
} else {
    $hfs = Find-Hfs
}

$exe = Join-Path $hfs "bin\houdini.exe"

# 패키지 JSON 을 찾을 디렉토리. repo 루트에 houdini_mcp.json 이 있다.
$packageDir = $RepoRoot

if ($NoTools) {
    # 툴 팩 JSON 만 빼려면 서버 JSON 만 담은 임시 디렉토리를 쓴다.
    $tempPkg = Join-Path ([System.IO.Path]::GetTempPath()) ("hmcp_pkg_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Path $tempPkg | Out-Null
    Copy-Item (Join-Path $RepoRoot "houdini_mcp.json") $tempPkg
    $packageDir = $tempPkg
}

$env:HOUDINI_PACKAGE_DIR = $packageDir
$env:HOUDINI_MCP_PORT = "$Port"

if ($IsolatePrefs) {
    $prefRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("hmcp_prefs_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Path $prefRoot | Out-Null
    # __HVER__ 토큰이 없으면 Houdini 가 이 변수를 통째로 무시한다.
    $env:HOUDINI_USER_PREF_DIR = Join-Path $prefRoot "houdini__HVER__"
}

if ($LogDir) {
    $env:HOUDINI_MCP_LOG_DIR = $LogDir
}
if ($ConsoleLog) {
    $env:HOUDINI_MCP_LOG_CONSOLE = "1"
}
Write-Host "Houdini      : $exe"
Write-Host "PACKAGE_DIR  : $env:HOUDINI_PACKAGE_DIR"
Write-Host "MCP_PORT     : $env:HOUDINI_MCP_PORT"
Write-Host "MCP URL      : http://127.0.0.1:$Port/mcp"
if ($IsolatePrefs) { Write-Host "USER_PREF_DIR: $env:HOUDINI_USER_PREF_DIR" }
if ($NoTools)      { Write-Host "TOOLS        : (제외됨)" }
if ($LogDir)       { Write-Host "LOG_DIR      : $env:HOUDINI_MCP_LOG_DIR" }
else               { Write-Host "LOG_DIR      : (기본) <USER_PREF_DIR>/log" }
if ($ConsoleLog)   { Write-Host "LOG_CONSOLE  : 콘솔에도 출력" }

if ($DryRun) {
    Write-Host "`n-DryRun 이므로 실행하지 않습니다."
    return
}

Write-Host ""
if ($Wait) {
    Start-Process -FilePath $exe -Wait -NoNewWindow
} else {
    Start-Process -FilePath $exe
    Write-Host "Houdini 를 띄웠습니다. UI 가 준비되면 MCP 서버가 뜹니다."
    Write-Host "로그는 파일에만 쌓입니다(-ConsoleLog 로 콘솔에도 낼 수 있습니다)."
}
