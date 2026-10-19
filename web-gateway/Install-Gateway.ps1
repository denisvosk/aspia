# Run from an elevated PowerShell after extracting outside C:\Web.
param(
    [string]$PublicOrigin = 'https://192.0.2.1',
    [string]$RouterAddress = '192.0.2.1',
    [int]$RouterPort = 8060,
    [string]$AdminUser = 'admin',
    [string]$Nssm = 'C:\chat_ZPP_bot\nssm.exe'
)
$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as administrator.' }
$root = [IO.Path]::GetFullPath($PSScriptRoot)
if ($root.StartsWith('C:\Web\', [StringComparison]::OrdinalIgnoreCase) -or $root -eq 'C:\Web') {
    throw 'Extract to C:\AspiaWebGateway, outside the Caddy file-server directory C:\Web.'
}
if (Get-Service AspiaWebGateway -ErrorAction SilentlyContinue) { throw 'AspiaWebGateway already exists. See README for updating without replacing accounts.' }
if (!(Test-Path $Nssm)) { throw "NSSM not found at $Nssm. Pass -Nssm with your existing NSSM path." }
foreach ($name in @('node.exe','aspia_web_bridge.exe','server.mjs','config.example.json','PACKAGE_SHA256.json')) {
    if (!(Test-Path (Join-Path $root $name))) { throw "Missing package file: $name" }
}
# Catch incomplete/corrupted extraction before starting a service.
$manifest = Get-Content (Join-Path $root 'PACKAGE_SHA256.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.files) {
    $file = Join-Path $root $entry.path
    if (!(Test-Path $file) -or (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "Package checksum mismatch: $($entry.path)" }
}
if (Get-NetTCPConnection -LocalPort 8085 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8085 is occupied. Resolve the conflict before installation.' }
function Run-Native([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$exe failed: $LASTEXITCODE" }
}
$configFile = Join-Path $root 'config.json'
if (!(Test-Path $configFile)) {
    $config = Get-Content (Join-Path $root 'config.example.json') -Raw | ConvertFrom-Json
    $config.publicOrigin = $PublicOrigin
    $config.router.address = $RouterAddress
    $config.router.port = $RouterPort
    [IO.File]::WriteAllText($configFile, ($config | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
}
New-Item -ItemType Directory -Force (Join-Path $root 'private'),(Join-Path $root 'logs') | Out-Null
# LocalService reads program/config/accounts, writes only the bounded audit log.
Run-Native 'icacls.exe' @($root,'/inheritance:r','/grant:r','*S-1-5-32-544:(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-19:(OI)(CI)RX','/T','/Q')
Run-Native 'icacls.exe' @((Join-Path $root 'logs'),'/grant:r','*S-1-5-19:(OI)(CI)M','/T','/Q')
if (!(Test-Path (Join-Path $root 'private\users.json'))) {
    Run-Native (Join-Path $root 'node.exe') @((Join-Path $root 'users.mjs'),'add',$AdminUser,'admin')
}
Run-Native (Join-Path $root 'aspia_web_bridge.exe') @('--self-test')
Run-Native $Nssm @('install','AspiaWebGateway',(Join-Path $root 'node.exe'))
try {
    Run-Native $Nssm @('set','AspiaWebGateway','AppDirectory',$root)
    Run-Native $Nssm @('set','AspiaWebGateway','AppParameters',('"' + (Join-Path $root 'server.mjs') + '"'))
    Run-Native $Nssm @('set','AspiaWebGateway','ObjectName','NT AUTHORITY\LocalService')
    Run-Native $Nssm @('set','AspiaWebGateway','Start','SERVICE_AUTO_START')
    Run-Native $Nssm @('set','AspiaWebGateway','AppKillProcessTree','1')
    Run-Native $Nssm @('set','AspiaWebGateway','AppRestartDelay','5000')
    Run-Native $Nssm @('set','AspiaWebGateway','AppStdout','NUL')
    Run-Native $Nssm @('set','AspiaWebGateway','AppStderr','NUL')
    Run-Native $Nssm @('start','AspiaWebGateway')
} catch { Write-Warning 'Installation incomplete. Inspect the AspiaWebGateway service before retrying.'; throw }
Write-Host 'Service installed. Add Caddy.fragment inside the existing IP site block, validate, then reload Caddy.'
Write-Host "URL: $PublicOrigin/remote/"
