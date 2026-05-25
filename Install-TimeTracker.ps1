# Install-TimeTracker.ps1
# 双击此文件（或右键 -> 用 PowerShell 运行）即可在桌面创建 Time Tracker 快捷方式 + Ctrl+Alt+T 热键
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$indexPath = Join-Path $scriptDir 'index.html'
if (-not (Test-Path $indexPath)) {
    Write-Host "❌ 没找到 index.html，请确认此脚本和 index.html 在同一文件夹" -ForegroundColor Red
    Read-Host "按回车退出"; exit 1
}

$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Time Tracker.lnk'

# 优先用 Edge --app 模式
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $edge)) { $edge = 'C:\Program Files\Microsoft\Edge\Application\msedge.exe' }
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (-not (Test-Path $chrome)) { $chrome = "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" }

$lnk = $ws.CreateShortcut($lnkPath)
if (Test-Path $edge) {
    $lnk.TargetPath = $edge
    $lnk.Arguments  = "--app=file:///$($indexPath -replace '\\','/') --window-size=1100,820"
} elseif (Test-Path $chrome) {
    $lnk.TargetPath = $chrome
    $lnk.Arguments  = "--app=file:///$($indexPath -replace '\\','/') --window-size=1100,820"
} else {
    $lnk.TargetPath = $indexPath
}
$lnk.WorkingDirectory = $scriptDir
$lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,16"
$lnk.Hotkey = 'CTRL+ALT+T'
$lnk.WindowStyle = 1
$lnk.Description = 'Time Tracker - record time per task'
$lnk.Save()

# 同时放到开始菜单（让热键更稳）
$startMenu = [Environment]::GetFolderPath('StartMenu')
Copy-Item $lnkPath (Join-Path $startMenu 'Time Tracker.lnk') -Force

Write-Host ""
Write-Host "✅ 安装完成！" -ForegroundColor Green
Write-Host "   - 桌面图标: Time Tracker"
Write-Host "   - 全局热键: Ctrl+Alt+T"
Write-Host ""
Write-Host "要换热键: 右键桌面图标 -> 属性 -> '快捷键' 框里按你想要的组合"
Write-Host ""
Read-Host "按回车退出"
