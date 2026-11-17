param(
    [Parameter(Mandatory = $true)][string]$Recipient,
    [string]$Python = '',
    [string]$Executable = '',
    [switch]$NoLaunch
)
$ErrorActionPreference = 'Stop'
$directory = $PSScriptRoot
if ($Executable) {
    $Executable = (Resolve-Path -LiteralPath $Executable).Path
    $pythonWindow = $Executable
    $workingDirectory = Split-Path -Parent $Executable
    $guiArguments = ''
    $reportArguments = '--due'
    $configure = Start-Process -FilePath $Executable -ArgumentList @('--configure', ('"' + $Recipient + '"')) -Wait -PassThru
    if ($configure.ExitCode -ne 0) { throw 'Could not save mail configuration.' }
} else {
    if (-not $Python) { $Python = (Get-Command python.exe).Source }
    $Python = (Resolve-Path -LiteralPath $Python).Path
    $pythonFolder = Split-Path -Parent $Python
    $pythonConsole = Join-Path $pythonFolder 'python.exe'
    $pythonWindow = Join-Path $pythonFolder 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonWindow)) { throw 'pythonw.exe was not found.' }
    $workingDirectory = $directory
    $guiArguments = '"' + (Join-Path $directory 'app.py') + '"'
    $reportArguments = '"' + (Join-Path $directory 'report.py') + '" --due'
    & $pythonConsole (Join-Path $directory 'report.py') --configure $Recipient
    if ($LASTEXITCODE -ne 0) { throw 'Could not save mail configuration.' }
}

$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
$definition = $service.NewTask(0)
$definition.RegistrationInfo.Description = 'DayLedger weekday 17:00 Outlook daily time report.'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$definition.Principal.UserId = $identity.User.Value
$definition.Principal.LogonType = 3
$definition.Principal.RunLevel = 0
$settings = $definition.Settings
$settings.Enabled = $true
$settings.Hidden = $false
$settings.StartWhenAvailable = $true
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false
$settings.ExecutionTimeLimit = 'PT5M'
$settings.MultipleInstances = 2
$weekly = $definition.Triggers.Create(3)
$weekly.StartBoundary = (Get-Date -Hour 17 -Minute 0 -Second 0).ToString("yyyy-MM-dd'T'HH:mm:ss")
$weekly.DaysOfWeek = 62
$weekly.WeeksInterval = 1
$weekly.Enabled = $true
$weekly.Repetition.Interval = 'PT15M'
$weekly.Repetition.Duration = 'PT6H'
$logon = $definition.Triggers.Create(9)
$logon.UserId = $identity.User.Value
$logon.Delay = 'PT1M'
$logon.Enabled = $true
$action = $definition.Actions.Create(0)
$action.Path = $pythonWindow
$action.Arguments = $reportArguments
$action.WorkingDirectory = $workingDirectory
$task = $folder.RegisterTaskDefinition('DayLedger-DailySummary', $definition, 6,
                                      $identity.User.Value, $null, 3, $null)
if (-not $task.Enabled) { throw 'Scheduled task was not enabled.' }

$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = [Environment]::GetFolderPath('Programs')
$shell = New-Object -ComObject WScript.Shell
foreach ($location in @($desktop, $startMenu)) {
    $shortcut = $shell.CreateShortcut((Join-Path $location 'DayLedger.lnk'))
    $shortcut.TargetPath = $pythonWindow
    $shortcut.Arguments = $guiArguments
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.Description = 'DayLedger - desktop time ledger and daily Outlook report'
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,20"
    if ($Executable) { $shortcut.IconLocation = "$Executable,0" }
    $shortcut.Save()
}
Push-Location $directory
try {
    if ($Executable) {
        $mark = Start-Process -FilePath $Executable -ArgumentList '--schedule-installed' -Wait -PassThru
        if ($mark.ExitCode -ne 0) { throw 'Could not persist scheduler status.' }
    } else {
        & $pythonConsole (Join-Path $directory 'report.py') --schedule-installed
        if ($LASTEXITCODE -ne 0) { throw 'Could not persist scheduler status.' }
    }
} finally {
    Pop-Location
}
Write-Output ('Installed task: ' + $task.Name)
Write-Output ('Next run: ' + $task.NextRunTime)
Write-Output ('Desktop shortcut: ' + (Join-Path $desktop 'DayLedger.lnk'))
if (-not $NoLaunch) {
    if ($guiArguments) {
        Start-Process -FilePath $pythonWindow -ArgumentList $guiArguments -WorkingDirectory $workingDirectory
    } else {
        Start-Process -FilePath $pythonWindow -WorkingDirectory $workingDirectory
    }
}
