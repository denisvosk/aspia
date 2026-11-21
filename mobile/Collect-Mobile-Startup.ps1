#requires -Version 5.1
<#
.SYNOPSIS
Collect a bounded startup trace for an installed Aspia+ Mobile APK.
.DESCRIPTION
Uses the package UID, not a transient PID, so an immediate crash is captured.
Stops and starts only org.aspiaplus.client. Does not clear app data or logcat,
uninstall anything, read the address book, or require a debug-signed APK.
#>
[CmdletBinding()]
param(
    [string]$AdbPath,
    [string]$Serial,
    [ValidateRange(1, 45)][int]$Seconds = 15,
    [string]$OutputDirectory = (Join-Path (Get-Location).Path 'Aspia-Diagnostics')
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$Package = 'org.aspiaplus.client'
$Component = 'org.aspiaplus.client/org.aspia.client.ClientActivity'
$DeviceArguments = @()
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-Adb {
    param([string[]]$Arguments, [switch]$AllowFailure)
    # Windows PowerShell 5.1 turns native stderr into ErrorRecord objects.
    # ADB's harmless daemon-start messages must not become terminating errors.
    $SavedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $Lines = @(& $script:AdbExecutable @script:DeviceArguments @Arguments 2>&1 |
            ForEach-Object { $_.ToString() })
        $Code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $SavedPreference }
    $Result = [pscustomobject]@{ ExitCode = $Code; Text = ($Lines -join "`n").TrimEnd() }
    if ($Code -ne 0 -and -not $AllowFailure) {
        throw "ADB failed ($Code): $($Result.Text)"
    }
    return $Result
}

function Save-Text {
    param([string]$Name, [string]$Text)
    [System.IO.File]::WriteAllText((Join-Path $script:SessionDirectory $Name),
        $Text + "`r`n", $script:Utf8)
}

function Get-AppCrashBlocks {
    param([string]$Text)
    # Java crashes are logged by the app. Native tombstones are logged by
    # crash_dump/DEBUG under a different UID, so select their complete blocks
    # only after matching the explicit crashing process name.
    $Blocks = New-Object 'System.Collections.Generic.List[object]'
    $Current = @{}
    $Header = '^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+(?<pid>\d+)\s+\d+\s+[VDIWEFAS]\s+(?<tag>AndroidRuntime|DEBUG)\s*:\s?(?<message>.*)$'
    foreach ($Line in ($Text -split '\r?\n')) {
        if ($Line -notmatch $Header) { continue }
        $Key = $Matches.pid + ':' + $Matches.tag
        $Message = $Matches.message
        if (-not $Current.ContainsKey($Key) -or
            $Message -match '^(FATAL EXCEPTION:|\*\*\* \*\*\*)') {
            $Block = [pscustomobject]@{
                Lines = (New-Object 'System.Collections.Generic.List[string]')
            }
            $Current[$Key] = $Block
            $Blocks.Add($Block)
        }
        $Current[$Key].Lines.Add($Line)
    }
    $ProcessName = [regex]::Escape($script:Package)
    $Target = '(?:Process:|Cmdline:|>>>)\s*' + $ProcessName +
        '(?::[A-Za-z0-9_.-]+)?(?=\s|,|$)'
    $Selected = @($Blocks | Where-Object { ($_.Lines -join "`n") -match $Target } |
        ForEach-Object { $_.Lines -join "`n" })
    return ($Selected -join "`n`n")
}

if ($AdbPath) {
    if (Test-Path -LiteralPath $AdbPath -PathType Container) {
        $AdbPath = Join-Path $AdbPath 'adb.exe'
    }
    $AdbExecutable = (Resolve-Path -LiteralPath $AdbPath).Path
}
else {
    $SdkAdb = if ($env:LOCALAPPDATA) {
        Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
    } else { '' }
    $AdbCommand = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($SdkAdb -and (Test-Path -LiteralPath $SdkAdb -PathType Leaf)) {
        $AdbExecutable = $SdkAdb
    }
    elseif ($AdbCommand) { $AdbExecutable = $AdbCommand.Source }
    else { throw 'ADB not found. Install Android SDK Platform-Tools, or pass -AdbPath C:\path\adb.exe.' }
}

$DevicesText = (Invoke-Adb -Arguments @('devices')).Text
$Devices = @()
foreach ($Line in ($DevicesText -split '\r?\n')) {
    if ($Line -match '^(\S+)\s+(device|unauthorized|offline)\b') {
        $Devices += [pscustomobject]@{ Serial = $Matches[1]; State = $Matches[2] }
    }
}
if ($Serial) {
    $Chosen = @($Devices | Where-Object { $_.Serial -ceq $Serial -and $_.State -eq 'device' })
    if ($Chosen.Count -ne 1) { throw 'Requested device is not authorized/online. Check adb devices and the USB debugging prompt.' }
}
else {
    $Chosen = @($Devices | Where-Object { $_.State -eq 'device' })
    if ($Chosen.Count -ne 1) {
        throw 'Connect exactly one authorized device, or select one with -Serial. Check adb devices and confirm USB debugging on the phone.'
    }
}
$DeviceArguments = @('-s', $Chosen[0].Serial)

$AndroidUser = (Invoke-Adb -Arguments @('shell', 'am', 'get-current-user')).Text.Trim()
if ($AndroidUser -notmatch '^\d+$') { throw 'Cannot determine the current Android user.' }
$PackageList = (Invoke-Adb -Arguments @('shell', 'cmd', 'package', 'list', 'packages',
    '-U', '--user', $AndroidUser, $Package)).Text
$UidMatch = [regex]::Match($PackageList,
    '(?m)^package:' + [regex]::Escape($Package) + '\s+uid:(\d+)\s*$')
if (-not $UidMatch.Success) { throw 'Aspia+ Mobile is not installed for the current Android user.' }
$AppUid = $UidMatch.Groups[1].Value

$SessionDirectory = Join-Path $OutputDirectory ('Aspia-startup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$null = New-Item -ItemType Directory -Path $SessionDirectory
$SessionDirectory = (Resolve-Path -LiteralPath $SessionDirectory).Path
$PackageInfo = (Invoke-Adb -Arguments @('shell', 'dumpsys', 'package', $Package)).Text
$VersionName = [regex]::Match($PackageInfo, '(?m)^\s*versionName=(.*)$').Groups[1].Value.Trim()
$VersionCode = [regex]::Match($PackageInfo, '(?m)^\s*versionCode=(\d+)').Groups[1].Value
$PageSize = (Invoke-Adb -Arguments @('shell', 'getconf', 'PAGESIZE') -AllowFailure).Text.Trim()
if ($PageSize -notmatch '^\d+$') { $PageSize = 'unavailable' }
$Info = [ordered]@{
    Package = $Package
    VersionName = $VersionName
    VersionCode = $VersionCode
    AndroidUser = $AndroidUser
    AppUid = $AppUid
    Manufacturer = (Invoke-Adb -Arguments @('shell', 'getprop', 'ro.product.manufacturer')).Text.Trim()
    Model = (Invoke-Adb -Arguments @('shell', 'getprop', 'ro.product.model')).Text.Trim()
    Android = (Invoke-Adb -Arguments @('shell', 'getprop', 'ro.build.version.release')).Text.Trim()
    Api = (Invoke-Adb -Arguments @('shell', 'getprop', 'ro.build.version.sdk')).Text.Trim()
    Abis = (Invoke-Adb -Arguments @('shell', 'getprop', 'ro.product.cpu.abilist')).Text.Trim()
    PageSize = $PageSize
    CaptureSecondsAfterLaunch = $Seconds
}

# Device time avoids clock/time-zone differences between Windows and Android.
# Round down to the current second to include an immediate startup failure.
$Since = (Invoke-Adb -Arguments @('shell', "date '+%m-%d %H:%M:%S.000'")).Text.Trim()
if ($Since -notmatch '^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$') {
    throw 'Cannot read device time; refusing to collect an unbounded log.'
}
$Info['DeviceLogStart'] = $Since
Write-Host 'Restarting only Aspia+ Mobile. Do not unlock/import a book/connect during this capture.'
$null = Invoke-Adb -Arguments @('shell', 'am', 'force-stop', '--user', $AndroidUser, $Package)
$Launch = Invoke-Adb -Arguments @('shell', 'am', 'start', '--user', $AndroidUser,
    '-W', '-n', $Component) -AllowFailure
Save-Text 'launch.txt' $Launch.Text
$Info['LaunchExitCode'] = $Launch.ExitCode
Write-Host "Capturing startup for $Seconds seconds..."
Start-Sleep -Seconds $Seconds

# UID survives process death. --pid would miss the very failure being diagnosed.
$AppLog = Invoke-Adb -Arguments @('logcat', '-b', 'main', '-b', 'system', '-b', 'crash',
    '-d', '-v', 'threadtime', '--uid', $AppUid, '-T', $Since) -AllowFailure
if ($AppLog.ExitCode -eq 0) { Save-Text 'startup-logcat.txt' $AppLog.Text }
else { Save-Text 'startup-logcat-error.txt' $AppLog.Text }
$Info['UidLogcatExitCode'] = $AppLog.ExitCode

$CrashLog = Invoke-Adb -Arguments @('logcat', '-b', 'crash', '-d', '-v', 'threadtime',
    '-T', $Since) -AllowFailure
if ($CrashLog.ExitCode -eq 0) {
    $SelectedCrash = Get-AppCrashBlocks $CrashLog.Text
    $Info['MatchingCrashBlock'] = -not [string]::IsNullOrWhiteSpace($SelectedCrash)
    if (-not $SelectedCrash) {
        $SelectedCrash = 'No matching Java/native crash block was present in this capture. This is not proof that startup succeeded.'
    }
    Save-Text 'crash.txt' $SelectedCrash
}
else {
    Save-Text 'crash-logcat-error.txt' $CrashLog.Text
    $Info['MatchingCrashBlock'] = $false
}
$Info['CrashLogcatExitCode'] = $CrashLog.ExitCode
$Running = Invoke-Adb -Arguments @('shell', 'pidof', $Package) -AllowFailure
$Info['ProcessPresentAtEnd'] = $Running.ExitCode -eq 0 -and $Running.Text.Trim() -match '^\d+(\s+\d+)*$'
Save-Text 'device-and-app.json' ($Info | ConvertTo-Json -Depth 3)
Write-Host "Saved: $SessionDirectory"
Write-Host 'Send device-and-app.json, launch.txt, startup-logcat.txt, and crash.txt (or the error files).'
Write-Host 'App data and existing device logs were preserved. No files were uploaded.'
