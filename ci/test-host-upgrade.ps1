# Runs only on an isolated GitHub Windows runner. Never uses a production config.
param([Parameter(Mandatory=$true)][string]$NewMsi,
      [ValidateSet('x86','x64')][string]$Arch = 'x86',
      [Parameter(Mandatory=$true)][string]$ExpectedVersion)
$packageArch = if ($Arch -eq 'x64') { 'x86_64' } else { 'x86' }
$expectedHash = if ($Arch -eq 'x64') { '8ba2a5dbb716edfb7bbd72483163111f9efd6e978ae0f81a0769842970331d5d' } else { '969b312fc7d6d178155faed901cb14c08cc5f55fb2746d6315fd2289829b247f' }
$ErrorActionPreference = 'Stop'
# PowerShell accepts mixed separators, but Windows Installer can reject them
# with error 1324/1619. Resolve the preview before installing the old Host.
if (!(Test-Path -LiteralPath $NewMsi -PathType Leaf)) { throw "Preview MSI does not exist: $NewMsi" }
$NewMsi = (Get-Item -LiteralPath $NewMsi).FullName.Replace('/', '\')
$work = Join-Path $env:RUNNER_TEMP 'aspia-upgrade-test'
New-Item -ItemType Directory -Force $work | Out-Null
$old = Join-Path $work "aspia-host-2.7.0-$packageArch.msi"
Invoke-WebRequest "https://github.com/dchapyshev/aspia/releases/download/v2.7.0/aspia-host-2.7.0-$packageArch.msi" -OutFile $old
if ((Get-FileHash $old -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) {
    throw 'Original 2.7.0 MSI checksum mismatch'
}
function Install-TestMsi([string]$path, [string]$name) {
    $path = (Get-Item -LiteralPath $path).FullName.Replace('/', '\')
    $log = Join-Path $work "$name.log"
    Write-Host "Installing $name from $path"
    $p = Start-Process msiexec.exe -ArgumentList @('/i', "`"$path`"", '/qn', '/norestart', '/l*v', "`"$log`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Get-Content $log -Tail 80
        throw "MSI $name failed or requires reboot: $($p.ExitCode)"
    }
    (Get-Service aspia-host-service).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
}
$previousDir = Join-Path $work 'preview20'
New-Item -ItemType Directory -Force $previousDir | Out-Null
$previousName = "aspia-host-2.7.1-$packageArch.msi"
# Preview.18 (release 416788911) was removed. Preview.20 is the retained build;
# these digests were verified against release 416827719 on 2026-11-20.
gh release download 'v2.7.1-clipboard-preview.20' --repo $env:GITHUB_REPOSITORY --pattern $previousName --dir $previousDir --clobber
if ($LASTEXITCODE) { throw 'Could not download the retained preview.20 for upgrade testing' }
$previous = Join-Path $previousDir $previousName
$previousHash = if ($Arch -eq 'x64') { 'ece4cdb9a1b669cce65af3603e23cd852fbf85eb2c3206231114a4cf989637d6' } else { 'bbf5b7052856d8d5fd33853c1a7eb98ad7c651454694912c6a4a09d85bb7bcc0' }
if ((Get-FileHash $previous -Algorithm SHA256).Hash.ToLower() -ne $previousHash) { throw 'Preview.20 MSI checksum mismatch' }
$installed = $old
try {
    Install-TestMsi $old 'install-original'
    Stop-Service aspia-host-service
    $configPath = Join-Path $env:ProgramData 'aspia/host.json'
    $config = @{}
    if (Test-Path $configPath) { $config = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable }
    $config['PreviewUpgradeTest'] = [Guid]::NewGuid().ToString()
    $config['RouterEnabled'] = $false
    $config['RouterAddress'] = '127.0.0.1'
    $config['UpdateServer'] = 'https://updates.invalid.test'
    $config['AutoUpdateEnabled'] = $false
    $config['LastUpdateCheck'] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    New-Item -ItemType Directory -Force (Split-Path $configPath) | Out-Null
    $config | ConvertTo-Json -Depth 30 | Set-Content $configPath -Encoding utf8
    Start-Service aspia-host-service
    $before = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    Install-TestMsi $NewMsi 'upgrade-preview'
    $installed = $NewMsi
    $after = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in $before.Keys) {
        $expected = ConvertTo-Json -InputObject $before[$key] -Depth 30 -Compress
        $actual = ConvertTo-Json -InputObject $after[$key] -Depth 30 -Compress
        if ($expected -ne $actual) { throw "Host setting changed during upgrade: $key" }
    }
    $programFiles = if ($Arch -eq 'x64') { $env:ProgramFiles } else { ${env:ProgramFiles(x86)} }
    $exe = Join-Path $programFiles 'Aspia/Host/aspia_host_service.exe'
    if (!(Test-Path $exe)) { throw 'Upgraded Host service executable missing' }
    if ((Get-Item $exe).VersionInfo.ProductVersion -notlike "$ExpectedVersion.*") { throw "Host service was not upgraded to $ExpectedVersion" }
    "Host $Arch 2.7.0 -> ${ExpectedVersion}: service running and test configuration preserved." | Write-Host
    function Assert-InstalledPayload {
        $builtDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'builds/ninja-multi-vcpkg-ci/Release'
        foreach ($name in 'aspia_host_service.exe','aspia_host.exe','aspia_desktop_agent.exe') {
            $actual = Join-Path (Split-Path $exe) $name
            $expected = Join-Path $builtDir $name
            if ((Get-FileHash $actual).Hash -ne (Get-FileHash $expected).Hash) {
                throw "Installed executable was not replaced by this build: $name"
            }
        }
    }
    Assert-InstalledPayload
    # Also exercise the user's exact situation: replace an existing 2.7.1 preview.
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$installed`"", '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Could not prepare retained-preview upgrade test: $($p.ExitCode)" }
    $installed = $previous
    Install-TestMsi $previous 'install-preview20'
    $before = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    Install-TestMsi $NewMsi 'upgrade-preview20-to-current'
    $installed = $NewMsi
    $after = Get-Content $configPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in $before.Keys) {
        if ((ConvertTo-Json -InputObject $before[$key] -Depth 30 -Compress) -ne
            (ConvertTo-Json -InputObject $after[$key] -Depth 30 -Compress)) {
            throw "Host setting changed during retained-preview upgrade: $key"
        }
    }
    Assert-InstalledPayload
    "Host $Arch preview.20 -> current ${ExpectedVersion}: service running, configuration preserved, installed binary hashes match this build." | Write-Host
    # Exercise the new helper on real Windows after the installed candidate has
    # passed both upgrade paths. Python uses raw binary pipes and the build's
    # actual protoc; PowerShell never decodes/re-encodes protobuf stdout.
    $root = Split-Path $PSScriptRoot -Parent
    $protoc = Join-Path $root "builds/ninja-multi-vcpkg-ci/vcpkg_installed/$Arch-windows-static/tools/protobuf/protoc.exe"
    if (!(Test-Path -LiteralPath $protoc -PathType Leaf)) { throw 'The build protoc executable is missing for the inventory smoke test.' }
    $settingsHash = (Get-FileHash $configPath -Algorithm SHA256).Hash
    python (Join-Path $PSScriptRoot 'test-inventory-worker.py') --service $exe --protoc $protoc --schema (Join-Path $root 'source/proto/inventory.proto')
    if ($LASTEXITCODE) { throw 'Installed Host inventory worker smoke test failed.' }
    if ((Get-FileHash $configPath -Algorithm SHA256).Hash -ne $settingsHash) { throw 'Inventory worker changed Host configuration.' }
    if ((Get-Service aspia-host-service).Status -ne 'Running') { throw 'Host service stopped during the inventory smoke test.' }
} finally {
    $p = Start-Process msiexec.exe -ArgumentList @('/x', "`"$installed`"", '/qn', '/norestart') -Wait -PassThru
    if ($p.ExitCode -notin 0,1605,3010) { Write-Warning "Cleanup MSI exit code: $($p.ExitCode)" }
}
