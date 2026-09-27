$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetBat = Join-Path $scriptDir "run.bat"
$iconFile  = Join-Path $scriptDir "app_icon.ico"
$desktop   = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "سامانه ثبت پلاک.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $targetBat
$Shortcut.WorkingDirectory = $scriptDir

if (Test-Path $iconFile) {
    $Shortcut.IconLocation = $iconFile
}

$Shortcut.Save()

Write-Host "Desktop shortcut created: $shortcutPath"
