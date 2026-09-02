# clear-python-catch.ps1
# Python バイトコードキャッシュ (__pycache__ / *.pyc / *.pyo) を再帰的に削除する。
# Windows PowerShell 5.1 / PowerShell 7+ 対応。
#
# 使い方:
#   pwsh -File tools\hve-app-cash\clear-python-catch.ps1            # リポジトリルートから実行
#   pwsh -File tools\hve-app-cash\clear-python-catch.ps1 -Path .    # 明示指定
#   pwsh -File tools\hve-app-cash\clear-python-catch.ps1 -DryRun    # 削除候補のみ表示

[CmdletBinding()]
param(
    [string]$Path = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Error "Path が見つかりません: $Path"
    exit 1
}

Write-Host "[clear-python-catch] target: $Path" -ForegroundColor Cyan
if ($DryRun) { Write-Host "[clear-python-catch] DryRun モード (削除はしません)" -ForegroundColor Yellow }

$dirs = Get-ChildItem -LiteralPath $Path -Include "__pycache__" -Recurse -Force -Directory -ErrorAction SilentlyContinue
$allFiles = Get-ChildItem -LiteralPath $Path -Include "*.pyc", "*.pyo" -Recurse -Force -File -ErrorAction SilentlyContinue
# __pycache__ 配下のファイルはディレクトリごと消えるので個別削除対象から除外する。
$files = $allFiles | Where-Object { $_.FullName -notmatch "\\__pycache__\\" }

Write-Host ("[clear-python-catch] __pycache__ ディレクトリ: {0} 件" -f $dirs.Count)
Write-Host ("[clear-python-catch] *.pyc / *.pyo ファイル   : {0} 件 (__pycache__ 配下を除く)" -f $files.Count)

if ($DryRun) {
    $dirs  | ForEach-Object { Write-Host "DIR  $($_.FullName)" }
    $files | ForEach-Object { Write-Host "FILE $($_.FullName)" }
    exit 0
}

$removed = 0
foreach ($d in $dirs) {
    if (-not (Test-Path -LiteralPath $d.FullName)) { continue }
    try { Remove-Item -LiteralPath $d.FullName -Recurse -Force; $removed++ }
    catch { Write-Warning "削除失敗: $($d.FullName) : $_" }
}
foreach ($f in $files) {
    if (-not (Test-Path -LiteralPath $f.FullName)) { continue }
    try { Remove-Item -LiteralPath $f.FullName -Force; $removed++ }
    catch { Write-Warning "削除失敗: $($f.FullName) : $_" }
}

Write-Host ("[clear-python-catch] 完了: {0} 項目削除" -f $removed) -ForegroundColor Green
