# 打包成 exe（Windows）
#
# 用法：在仓库根目录执行
#     powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#
# 产物：dist\标签排版.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = Join-Path $root "src"

Write-Host "== 1/3 安装依赖 ==" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "== 2/3 自检 ==" -ForegroundColor Cyan
python -m unittest discover -s tests -t .

Write-Host "== 3/3 打包 ==" -ForegroundColor Cyan
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
pyinstaller packaging\label_sheet.spec --noconfirm

Write-Host ""
Write-Host "完成：$root\dist\标签排版.exe" -ForegroundColor Green
Get-ChildItem dist | Format-Table Name, Length, LastWriteTime -AutoSize
